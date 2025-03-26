import os
import sys
import asyncio
import logging
from pathlib import Path
import discord

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

# 현재 디렉토리를 Python 경로에 추가 (상대 임포트를 위함)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

async def reset_commands():
    """모든 서버의 봇 명령어를 초기화하고 다시 등록하는 비동기 함수"""
    try:
        # peanut 패키지의 봇 모듈 가져오기
        from peanut.bot import PeanutBot
        from peanut.utils.config import get_config
        
        # 설정 로드
        config = get_config()
        allowed_guild_ids_str = config.get('ALLOWED_GUILD_IDS', '')
        allowed_guild_ids = set()
        
        if allowed_guild_ids_str:
            try:
                allowed_guild_ids = {int(guild_id.strip()) for guild_id in allowed_guild_ids_str.split(',') if guild_id.strip()}
                logger.info(f"허용된 서버 ID 목록: {allowed_guild_ids}")
            except ValueError as e:
                logger.error(f"ALLOWED_GUILD_IDS 파싱 중 오류 발생: {str(e)}")
        
        # 토큰 확인
        if not config.get('DISCORD_TOKEN'):
            logger.error("DISCORD_TOKEN이 설정되지 않았습니다. .env 파일을 확인하세요.")
            return
        
        # 봇 인스턴스 생성
        bot = PeanutBot()
        
        # 서버 목록 확인
        if not allowed_guild_ids:
            logger.error("허용된 서버 ID가 없습니다. .env 파일의 ALLOWED_GUILD_IDS를 확인하세요.")
            return
        
        # 봇 로그인
        logger.info("Discord에 로그인 중...")
        await bot.login(config.get('DISCORD_TOKEN'))
        
        # 명령어 초기화
        logger.info("모든 서버의 명령어를 초기화합니다...")
        
        # 각 서버별 명령어 초기화
        for guild_id in allowed_guild_ids:
            try:
                # API 직접 호출로 서버 명령어 초기화
                await bot.http.bulk_upsert_guild_commands(bot.user.id, guild_id, [])
                logger.info(f"서버 ID {guild_id}의 모든 명령어를 초기화했습니다.")
            except Exception as e:
                logger.error(f"서버 {guild_id} 명령어 초기화 오류: {str(e)}")
        
        # 대기 시간 추가
        logger.info("잠시 대기 중...")
        await asyncio.sleep(2)
        
        # 작업을 위해 connect 없이 클라이언트 준비
        logger.info("명령어 등록을 위한 준비 중...")
        await bot._async_setup_hook()
        
        # Cog 설정 (질문 명령어 등록을 위해)
        await bot.setup_cogs()
        
        # 각 서버별 명령어 등록
        for guild_id in allowed_guild_ids:
            try:
                guild = bot.get_guild(guild_id)
                if guild:
                    # 서버별 명령어 동기화
                    synced = await bot.tree.sync(guild=guild)
                    logger.info(f"서버 ID {guild_id}에 {len(synced)}개의 슬래시 명령어를 동기화했습니다.")
                    for cmd in synced:
                        logger.info(f"등록된 명령어: {cmd.name}")
                else:
                    # get_guild는 캐시에 있는 것만 반환하므로, 직접 등록 시도
                    try:
                        await bot.tree.sync(guild=discord.Object(id=guild_id))
                        logger.info(f"서버 ID {guild_id}에 명령어를 동기화했습니다.")
                    except Exception as e:
                        logger.error(f"서버 ID {guild_id}에 명령어 동기화 실패: {str(e)}")
            except Exception as e:
                logger.error(f"서버 {guild_id} 명령어 동기화 오류: {str(e)}")
        
        # 전역 명령어 동기화 (필요한 경우)
        # global_commands = await bot.tree.sync()
        # logger.info(f"글로벌 명령어 {len(global_commands)}개를 동기화했습니다.")
        
        logger.info("명령어 초기화 및 재등록 작업이 완료되었습니다.")
        
        # 봇 연결 종료
        await bot.close()
        
    except ModuleNotFoundError as e:
        logger.error(f"필요한 모듈을 찾을 수 없습니다: {str(e)}")
        logger.error("스크립트는 'peanut' 디렉토리와 같은 위치에서 실행해야 합니다.")
    except Exception as e:
        logger.error(f"명령어 초기화 및 재등록 중 오류 발생: {str(e)}", exc_info=True)

def main():
    """메인 실행 함수"""
    try:
        # 비동기 함수 실행
        asyncio.run(reset_commands())
    except KeyboardInterrupt:
        logger.info("사용자에 의해 프로그램이 중단되었습니다.")
    except Exception as e:
        logger.error(f"프로그램 실행 중 오류 발생: {str(e)}", exc_info=True)
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main()) 