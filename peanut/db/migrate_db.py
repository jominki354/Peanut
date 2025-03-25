#!/usr/bin/env python3
"""
데이터베이스 마이그레이션 스크립트
기존 데이터베이스 스키마를 업데이트하고 필요한 필드를 추가합니다.
"""

import logging
import os
import sys
from pathlib import Path
from sqlalchemy import create_engine, inspect, text

# 프로젝트 경로 설정
project_path = Path(__file__).parent.parent.parent
sys.path.append(str(project_path))

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

def get_database_path():
    """데이터베이스 경로 반환"""
    try:
        # 설정 가져오기
        from peanut.utils.config import get_config
        config = get_config()
        
        if "DB_PATH" in config:
            db_path = config["DB_PATH"]
            logger.info(f"환경 변수에서 DB 경로를 읽었습니다: {db_path}")
            return db_path
        
        # 기본 경로 사용
        default_path = Path(__file__).parent / "discord_messages.db"
        logger.info(f"기본 DB 경로를 사용합니다: {default_path}")
        return str(default_path)
    except Exception as e:
        logger.error(f"DB 경로를 가져오는 중 오류 발생: {e}")
        # 기본 경로 사용
        default_path = Path(__file__).parent / "discord_messages.db"
        logger.info(f"오류로 인해 기본 DB 경로를 사용합니다: {default_path}")
        return str(default_path)

def migrate_database():
    """데이터베이스 마이그레이션 실행"""
    try:
        # 데이터베이스 연결
        db_path = get_database_path()
        engine = create_engine(f'sqlite:///{db_path}')
        conn = engine.connect()
        
        # 데이터베이스 인스펙션
        inspector = inspect(engine)
        
        # DiscordMessage 테이블 확인
        if 'discord_messages' in inspector.get_table_names():
            columns = [column['name'] for column in inspector.get_columns('discord_messages')]
            
            # 새 필드들 추가
            new_columns = {
                'message_url': 'VARCHAR(256)',
                'topics': 'TEXT',
                'message_type': 'VARCHAR(50)',
                'content_structure': 'TEXT',
                'markdown_used': 'TEXT',
                'channel_name': 'VARCHAR(100)',
                'guild_name': 'VARCHAR(100)',
                'sections': 'TEXT'  # 섹션 정보 저장 필드 추가
            }
            
            for column_name, column_type in new_columns.items():
                if column_name not in columns:
                    try:
                        logger.info(f"'{column_name}' 컬럼 추가 중...")
                        conn.execute(text(f"ALTER TABLE discord_messages ADD COLUMN {column_name} {column_type}"))
                        logger.info(f"'{column_name}' 컬럼이 성공적으로 추가되었습니다.")
                    except Exception as e:
                        logger.error(f"컬럼 추가 중 오류 발생: {e}")
        
        # CollectionMetadata 테이블 확인 및 생성
        if 'collection_metadata' not in inspector.get_table_names():
            try:
                logger.info("'collection_metadata' 테이블 생성 중...")
                conn.execute(text("""
                CREATE TABLE collection_metadata (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key VARCHAR(100) NOT NULL UNIQUE,
                    value TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """))
                logger.info("'collection_metadata' 테이블이 성공적으로 생성되었습니다.")
            except Exception as e:
                logger.error(f"테이블 생성 중 오류 발생: {e}")
        
        conn.close()
        logger.info("데이터베이스 마이그레이션이 완료되었습니다.")
    except Exception as e:
        logger.error(f"마이그레이션 중 오류 발생: {e}")

if __name__ == "__main__":
    # 마이그레이션 실행
    logger.info("데이터베이스 마이그레이션 시작...")
    migrate_database()
    
    # 완료 메시지 출력
    logger.info("마이그레이션 스크립트가 완료되었습니다.") 