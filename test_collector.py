#!/usr/bin/env python3
"""
메시지 수집 테스트 스크립트
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

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

async def test_collect_messages():
    """모든 서버에서 메시지를 수집하는 테스트 함수"""
    from peanut.utils.collector import MessageCollector
    from peanut.bot import PeanutBot
    
    logger.info("메시지 수집 테스트 시작...")
    
    # 봇 인스턴스 생성
    bot = PeanutBot()
    
    # 수집기 생성
    collector = MessageCollector(bot)
    
    # 특정 채널에서 메시지 수집 (예시)
    result = await collector.collect_all_guilds()
    
    logger.info(f"메시지 수집 완료: {result}개 메시지 수집됨")
    return result

if __name__ == "__main__":
    logger.info("테스트 스크립트 시작...")
    
    # Windows에서는 특별한 이벤트 루프 정책 설정
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    # 비동기 함수 실행
    result = asyncio.run(test_collect_messages())
    
    logger.info(f"테스트 완료: {result}개 메시지 수집됨") 