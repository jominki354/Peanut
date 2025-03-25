import os
import sys
import sqlite3
import logging
import shutil
from pathlib import Path

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('db_migration')

def get_table_structure(cursor, table_name):
    """테이블 구조를 가져오는 함수"""
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = cursor.fetchall()
    column_names = [column[1] for column in columns]
    return column_names

def migrate_to_guild_specific_dbs():
    """
    기존 단일 DB 파일에서 서버별 DB 파일로 데이터를 마이그레이션합니다.
    """
    # 기존 DB 파일 경로
    db_dir = Path(__file__).parent
    legacy_db_path = db_dir / "discord_messages.db"
    
    # 기존 DB 파일이 존재하는지 확인
    if not legacy_db_path.exists():
        logger.error(f"기존 DB 파일이 존재하지 않습니다: {legacy_db_path}")
        return False
    
    # 백업 생성
    backup_path = legacy_db_path.with_suffix(".db.migration_backup")
    shutil.copy2(legacy_db_path, backup_path)
    logger.info(f"기존 DB 파일 백업 생성: {backup_path}")
    
    try:
        # 기존 DB 연결
        legacy_conn = sqlite3.connect(legacy_db_path)
        legacy_cursor = legacy_conn.cursor()
        
        # 테이블 목록 가져오기
        legacy_cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = legacy_cursor.fetchall()
        table_names = [table[0] for table in tables]
        logger.info(f"기존 DB의 테이블 목록: {table_names}")
        
        # discord_messages 테이블 구조 확인
        discord_messages_columns = get_table_structure(legacy_cursor, "discord_messages")
        logger.info(f"discord_messages 테이블 컬럼: {discord_messages_columns}")
        
        # collection_metadata 테이블 구조 확인
        has_metadata_table = 'collection_metadata' in table_names
        metadata_columns = None
        if has_metadata_table:
            metadata_columns = get_table_structure(legacy_cursor, "collection_metadata")
            logger.info(f"collection_metadata 테이블 컬럼: {metadata_columns}")
        
        # 서버 ID가 있는지 확인 (guild_id 또는 guild_name 컬럼 확인)
        server_id_column = None
        if 'guild_id' in discord_messages_columns:
            server_id_column = 'guild_id'
        elif 'guild_name' in discord_messages_columns:
            server_id_column = 'guild_name'
            
        if not server_id_column:
            logger.error("서버 ID 관련 컬럼(guild_id 또는 guild_name)을 찾을 수 없습니다.")
            return False
        
        # 서버 ID 목록 가져오기
        legacy_cursor.execute(f"SELECT DISTINCT {server_id_column} FROM discord_messages WHERE {server_id_column} IS NOT NULL")
        server_ids = [row[0] for row in legacy_cursor.fetchall()]
        
        if not server_ids:
            logger.warning("서버 ID가 있는 메시지가 없습니다. 마이그레이션이 필요하지 않을 수 있습니다.")
            return False
        
        logger.info(f"발견된 서버 ID: {server_ids}")
        
        # 테이블 스키마 가져오기
        legacy_cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='discord_messages'")
        messages_schema_row = legacy_cursor.fetchone()
        if not messages_schema_row:
            logger.error("discord_messages 테이블 스키마를 가져올 수 없습니다.")
            return False
        messages_schema_sql = messages_schema_row[0]
        
        metadata_schema_sql = None
        if has_metadata_table:
            legacy_cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='collection_metadata'")
            metadata_schema_row = legacy_cursor.fetchone()
            if metadata_schema_row:
                metadata_schema_sql = metadata_schema_row[0]
            else:
                logger.warning("collection_metadata 테이블 스키마를 가져올 수 없습니다.")
        
        # 각 서버별로 새 DB 파일 생성 및 데이터 마이그레이션
        for server_id in server_ids:
            # 새 DB 파일 경로
            new_db_path = db_dir / f"discord_messages_guild_{server_id}.db"
            
            # 이미 존재하는 경우 백업 생성 후 삭제
            if new_db_path.exists():
                guild_backup_path = new_db_path.with_suffix(".db.backup")
                shutil.copy2(new_db_path, guild_backup_path)
                logger.info(f"기존 서버별 DB 파일 백업 생성: {guild_backup_path}")
                os.remove(new_db_path)  # 기존 파일 삭제
                logger.info(f"기존 서버별 DB 파일 삭제: {new_db_path}")
            
            # 새 DB 연결
            new_conn = sqlite3.connect(new_db_path)
            new_cursor = new_conn.cursor()
            
            # 기존 DB와 동일한 스키마로 테이블 생성
            # discord_messages 테이블 생성
            new_cursor.execute(messages_schema_sql)
            logger.info("discord_messages 테이블 생성 완료")
            
            # collection_metadata 테이블 생성 (있는 경우)
            if metadata_schema_sql:
                new_cursor.execute(metadata_schema_sql)
                logger.info("collection_metadata 테이블 생성 완료")
            
            # 해당 서버의 메시지 데이터 복사
            columns_str = ', '.join(discord_messages_columns)
            placeholders = ', '.join(['?' for _ in range(len(discord_messages_columns))])
            
            legacy_cursor.execute(f"SELECT {columns_str} FROM discord_messages WHERE {server_id_column} = ?", (server_id,))
            messages = legacy_cursor.fetchall()
            logger.info(f"서버 {server_id}에서 {len(messages)}개의 메시지를 마이그레이션합니다.")
            
            # 새 DB에 데이터 삽입
            if messages:
                insert_query = f"INSERT OR REPLACE INTO discord_messages ({columns_str}) VALUES ({placeholders})"
                new_cursor.executemany(insert_query, messages)
                logger.info(f"메시지 데이터 {len(messages)}개 삽입 완료")
            
            # 해당 서버의 메타데이터 복사 (있는 경우)
            if has_metadata_table and metadata_columns and server_id_column in metadata_columns:
                metadata_columns_str = ', '.join(metadata_columns)
                metadata_placeholders = ', '.join(['?' for _ in range(len(metadata_columns))])
                
                legacy_cursor.execute(f"SELECT {metadata_columns_str} FROM collection_metadata WHERE {server_id_column} = ?", (server_id,))
                metadata = legacy_cursor.fetchall()
                logger.info(f"서버 {server_id}에서 {len(metadata)}개의 메타데이터 항목을 마이그레이션합니다.")
                
                if metadata:
                    # 새 DB에 메타데이터 삽입
                    metadata_insert_query = f"INSERT OR REPLACE INTO collection_metadata ({metadata_columns_str}) VALUES ({metadata_placeholders})"
                    new_cursor.executemany(metadata_insert_query, metadata)
                    logger.info(f"메타데이터 {len(metadata)}개 삽입 완료")
            
            # 변경사항 저장 및 연결 종료
            new_conn.commit()
            new_conn.close()
            
            logger.info(f"서버 {server_id}의 데이터 마이그레이션 완료: {new_db_path}")
        
        # 기존 DB 연결 종료
        legacy_conn.close()
        logger.info("모든 서버 데이터 마이그레이션 완료")
        
        return True
        
    except Exception as e:
        logger.error(f"마이그레이션 중 오류 발생: {str(e)}", exc_info=True)
        return False

if __name__ == "__main__":
    logger.info("기존 DB에서 서버별 DB로 마이그레이션을 시작합니다...")
    success = migrate_to_guild_specific_dbs()
    
    if success:
        logger.info("마이그레이션이 성공적으로 완료되었습니다.")
        sys.exit(0)
    else:
        logger.error("마이그레이션 중 오류가 발생했습니다.")
        sys.exit(1) 