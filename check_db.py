import asyncio
import os
import sys

# 프로젝트 경로 추가
sys.path.append('.')

from peanut.db.database import get_db_manager, DiscordMessage
from sqlalchemy import select, func, text

async def check_database():
    """데이터베이스의 메시지 정보를 확인합니다."""
    # 데이터베이스 매니저 초기화
    db_manager = get_db_manager()
    
    async with db_manager.AsyncSessionLocal() as session:
        # 전체 메시지 수 확인
        total_count_query = select(func.count()).select_from(DiscordMessage)
        result = await session.execute(total_count_query)
        total_count = result.scalar()
        
        print(f"데이터베이스의 전체 메시지 수: {total_count}")
        
        # 봇 ID를 가진 메시지 수 확인
        bot_id = os.environ.get('BOT_ID', '1320403457043333232')
        bot_count_query = select(func.count()).select_from(DiscordMessage).where(
            DiscordMessage.author_id == bot_id
        )
        result = await session.execute(bot_count_query)
        bot_count = result.scalar()
        
        print(f"봇 ID({bot_id})를 가진 메시지 수: {bot_count}")
        
        if bot_count > 0:
            print("주의: 데이터베이스에 봇 메시지가 아직 남아있습니다!")
        else:
            print("성공: 데이터베이스에서 봇 메시지가 모두 제거되었습니다!")
        
        # 작성자별 메시지 수 확인
        author_query = text("""
            SELECT author_id, author_name, COUNT(*) as message_count
            FROM discord_messages
            GROUP BY author_id, author_name
            ORDER BY message_count DESC
            LIMIT 10
        """)
        
        result = await session.execute(author_query)
        authors = result.fetchall()
        
        print("\n작성자별 메시지 수 (상위 10명):")
        print("-" * 50)
        for author_id, author_name, count in authors:
            print(f"{author_name} ({author_id}): {count}개")

if __name__ == "__main__":
    asyncio.run(check_database()) 