import asyncio
import os
import sys
from datetime import datetime

# 프로젝트 경로 추가
sys.path.append('.')

from peanut.db.database import get_db_manager, DiscordMessage, CollectionMetadata
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
        bot_ids = ["1320403457043333232", "1075414851939213343", "1320659627142156318"]
        bot_count_query = select(func.count()).select_from(DiscordMessage).where(
            DiscordMessage.author_id.in_(bot_ids)
        )
        result = await session.execute(bot_count_query)
        bot_count = result.scalar()
        
        print(f"봇 ID({','.join(bot_ids)})를 가진 메시지 수: {bot_count}")
        
        if bot_count > 0:
            print("주의: 데이터베이스에 봇 메시지가 아직 남아있습니다!")
        else:
            print("성공: 데이터베이스에서 봇 메시지가 모두 제거되었습니다!")
        
        # 수집 메타데이터 확인
        print("\n수집 메타데이터 정보:")
        print("-" * 50)
        
        metadata_query = select(CollectionMetadata)
        result = await session.execute(metadata_query)
        metadata_records = result.scalars().all()
        
        if metadata_records:
            for record in metadata_records:
                print(f"키: {record.key}")
                print(f"값: {record.value}")
                print(f"업데이트 시간: {record.updated_at}")
                print("-" * 30)
                
                # 마지막 수집 시간을 날짜로 변환하여 표시
                if record.key == 'last_collection_time':
                    try:
                        last_time = datetime.strptime(record.value, '%Y-%m-%d %H:%M:%S')
                        now = datetime.utcnow()
                        diff = now - last_time
                        print(f"마지막 수집 이후 경과 시간: {diff.total_seconds() / 60:.1f}분 ({diff.total_seconds() / 3600:.1f}시간)")
                    except ValueError:
                        print("날짜 형식 오류")
        else:
            print("메타데이터 레코드가 없습니다.")
        
        # 채널별 마지막 수집 시간 확인
        channel_meta_query = select(CollectionMetadata).where(
            CollectionMetadata.key.like('last_collected_channel_%')
        )
        result = await session.execute(channel_meta_query)
        channel_metadata = result.scalars().all()
        
        if channel_metadata:
            print("\n채널별 마지막 수집 시간:")
            print("-" * 50)
            for record in channel_metadata:
                channel_id = record.key.replace('last_collected_channel_', '')
                print(f"채널 ID: {channel_id}")
                print(f"마지막 수집 시간: {record.value}")
                print(f"업데이트 시간: {record.updated_at}")
                print("-" * 30)
        
        # 서버별 마지막 수집 시간 확인
        guild_meta_query = select(CollectionMetadata).where(
            CollectionMetadata.key.like('last_collected_guild_%')
        )
        result = await session.execute(guild_meta_query)
        guild_metadata = result.scalars().all()
        
        if guild_metadata:
            print("\n서버별 마지막 수집 시간:")
            print("-" * 50)
            for record in guild_metadata:
                guild_id = record.key.replace('last_collected_guild_', '')
                print(f"서버 ID: {guild_id}")
                print(f"마지막 수집 시간: {record.value}")
                print(f"업데이트 시간: {record.updated_at}")
                print("-" * 30)
        
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