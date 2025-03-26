#!/usr/bin/env python3
import sqlite3
import os
from pathlib import Path

def check_db(db_path):
    """데이터베이스의 메시지 수 확인"""
    try:
        print(f"데이터베이스 파일 확인: {db_path}")
        
        if not os.path.exists(db_path):
            print(f"❌ 파일이 존재하지 않습니다: {db_path}")
            return
            
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 메시지 테이블 존재 여부 확인
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='discord_messages'")
        if not cursor.fetchone():
            print(f"❌ discord_messages 테이블이 존재하지 않습니다: {db_path}")
            conn.close()
            return
            
        # 메시지 수 확인
        cursor.execute("SELECT COUNT(*) FROM discord_messages")
        count = cursor.fetchone()[0]
        print(f"✅ 메시지 수: {count}")
        
        # 메타데이터 확인
        cursor.execute("SELECT * FROM collection_metadata WHERE key LIKE 'last_collected_guild_%'")
        metadata = cursor.fetchall()
        if metadata:
            print("📅 서버별 마지막 수집 시간:")
            for meta in metadata:
                print(f"  - {meta[0]}: {meta[1]} (업데이트: {meta[2]})")
        else:
            print("❌ 서버별 수집 메타데이터 없음")
            
        conn.close()
    except Exception as e:
        print(f"❌ 오류 발생: {str(e)}")

def main():
    # DB 폴더 확인
    db_dir = Path("db")
    if not db_dir.exists():
        print(f"❌ DB 폴더가 존재하지 않습니다: {db_dir.absolute()}")
        return
        
    print(f"📁 DB 폴더 경로: {db_dir.absolute()}")
    
    # 모든 서버 데이터베이스 파일 확인
    guild_dbs = list(db_dir.glob("discord_messages_guild_*.db"))
    
    if not guild_dbs:
        print("❌ 서버 데이터베이스 파일이 없습니다.")
        return
        
    print(f"🔍 서버 데이터베이스 파일 수: {len(guild_dbs)}")
    
    # 각 데이터베이스 파일 확인
    for db_file in guild_dbs:
        server_id = db_file.name.replace("discord_messages_guild_", "").replace(".db", "")
        print(f"\n📊 서버 ID {server_id} 정보:")
        check_db(db_file)

if __name__ == "__main__":
    main() 