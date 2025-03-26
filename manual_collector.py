#!/usr/bin/env python3
"""
Discord 메시지 수동 수집 스크립트
"""

import asyncio
import logging
import os
import sys
from pathlib import Path
import discord
from datetime import datetime, timedelta

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# 프로젝트 경로 설정
project_path = Path(__file__).parent
sys.path.append(str(project_path))

class ManualCollectorBot(discord.Client):
    """메시지 수집용 봇 클래스"""
    
    def __init__(self, target_guild_id, *args, **kwargs):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(intents=intents, *args, **kwargs)
        self.target_guild_id = int(target_guild_id)
        self.ready_to_collect = asyncio.Event()
        
    async def on_ready(self):
        """봇이 준비되었을 때 호출되는 이벤트"""
        logger.info(f"{self.user.name}({self.user.id})로 로그인했습니다.")
        
        # 타겟 서버 확인
        target_guild = self.get_guild(self.target_guild_id)
        if target_guild:
            logger.info(f"서버 '{target_guild.name}'({target_guild.id})를 발견했습니다.")
            self.ready_to_collect.set()
        else:
            logger.error(f"서버 ID {self.target_guild_id}를 찾을 수 없습니다.")

async def collect_specific_guild(guild_id):
    """특정 서버의 메시지를 수집하는 함수"""
    from peanut.utils.collector import MessageCollector
    from peanut.bot import PeanutBot
    from peanut.utils.config import get_config
    from peanut.db.database import get_db_manager
    
    logger.info(f"서버 ID {guild_id}의 메시지 수집 시작...")
    
    # 봇 설정 로드
    config = get_config()
    
    # 봇 인스턴스 생성 (직접 디스코드에 연결하기 위해 만든 클래스 사용)
    bot = ManualCollectorBot(guild_id)
    
    # 봇 연결 및 실행
    try:
        # 비동기로 봇 실행
        bot_task = asyncio.create_task(bot.start(config['DISCORD_TOKEN']))
        
        # 봇이 준비될 때까지 대기
        await bot.ready_to_collect.wait()
        
        # 타겟 서버 가져오기
        guild = bot.get_guild(int(guild_id))
        if not guild:
            logger.error(f"서버 ID {guild_id}를 찾을 수 없습니다.")
            bot.close()
            return None
        
        logger.info(f"서버 '{guild.name}'({guild.id})의 메시지 수집 시작...")
        
        # 수집할 채널 목록 가져오기
        text_channels = [c for c in guild.channels if isinstance(c, discord.TextChannel)]
        logger.info(f"수집 대상 채널 수: {len(text_channels)}")
        
        # 데이터베이스 매니저 초기화
        db_manager = get_db_manager(guild_id=guild.id)
        
        # 메시지 수집
        total_collected = 0
        
        for channel in text_channels:
            logger.info(f"채널 '{channel.name}'({channel.id})의 메시지 수집 중...")
            
            # 이전에 수집한 메시지 이후부터 수집 (없으면 전체 수집)
            message_count = 0
            
            # 메시지 히스토리 조회
            try:
                async for message in channel.history(limit=1000):
                    # 메시지 저장
                    message_data = {
                        'message_id': str(message.id),
                        'channel_id': str(channel.id),
                        'guild_id': str(guild.id),
                        'channel_name': channel.name,
                        'guild_name': guild.name,
                        'author_id': str(message.author.id),
                        'author_name': message.author.name,
                        'content': message.content,
                        'created_at': message.created_at,
                        'attachments_count': len(message.attachments),
                        'collected_at': datetime.now(),
                    }
                    
                    # 데이터베이스에 저장
                    await db_manager.save_messages([message_data])
                    message_count += 1
                    
                    # 100개 메시지마다 진행 상황 출력
                    if message_count % 100 == 0:
                        logger.info(f"채널 '{channel.name}'에서 {message_count}개 메시지 수집 중...")
                
                logger.info(f"채널 '{channel.name}'에서 {message_count}개 메시지 수집 완료")
                total_collected += message_count
                
            except discord.Forbidden:
                logger.warning(f"채널 '{channel.name}'에 접근 권한이 없습니다.")
            except Exception as e:
                logger.error(f"채널 '{channel.name}' 메시지 수집 중 오류: {str(e)}")
        
        logger.info(f"서버 '{guild.name}'({guild.id})의 메시지 수집 완료: {total_collected}개 메시지")
        
        # 메시지 수집이 완료되면 봇 종료
        await bot.close()
        return total_collected
    
    except Exception as e:
        logger.error(f"메시지 수집 중 오류 발생: {str(e)}", exc_info=True)
        if not bot.is_closed():
            await bot.close()
        return None

def main():
    """스크립트 메인 함수"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Discord 메시지 수동 수집')
    parser.add_argument('--guild-id', type=str, required=True, 
                        help='수집할 서버(길드) ID')
    
    args = parser.parse_args()
    
    if not args.guild_id:
        logger.error("서버 ID가 필요합니다. --guild-id 옵션을 사용하세요.")
        return
    
    # 이벤트 루프 가져오기
    loop = asyncio.get_event_loop()
    
    try:
        result = loop.run_until_complete(collect_specific_guild(args.guild_id))
        logger.info(f"수집 완료: {result}개 메시지")
    except Exception as e:
        logger.error(f"오류 발생: {str(e)}", exc_info=True)
    finally:
        loop.close()

if __name__ == "__main__":
    main() 