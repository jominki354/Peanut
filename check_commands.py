import os
import sys
import asyncio
import logging
import discord
from pathlib import Path

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

async def check_commands():
    """Discord 서버에 등록된 명령어를 확인하는 비동기 함수"""
    try:
        # peanut 패키지의 설정 가져오기
        from peanut.utils.config import get_config
        
        # 설정 로드
        config = get_config()
        
        # 토큰 확인
        token = config.get('DISCORD_TOKEN')
        if not token:
            logger.error("DISCORD_TOKEN이 설정되지 않았습니다. .env 파일을 확인하세요.")
            return
        
        # 허용된 서버 ID 목록 가져오기
        allowed_guild_ids_str = config.get('ALLOWED_GUILD_IDS', '')
        allowed_guild_ids = set()
        
        if allowed_guild_ids_str:
            try:
                allowed_guild_ids = {int(guild_id.strip()) for guild_id in allowed_guild_ids_str.split(',') if guild_id.strip()}
                logger.info(f"허용된 서버 ID 목록: {allowed_guild_ids}")
            except ValueError as e:
                logger.error(f"ALLOWED_GUILD_IDS 파싱 중 오류 발생: {str(e)}")
        
        # 봇 클라이언트 생성
        intents = discord.Intents.default()
        intents.message_content = True
        client = discord.Client(intents=intents)
        
        # Discord API와 연결
        await client.login(token)
        
        # 각 서버의 명령어 확인
        for guild_id in allowed_guild_ids:
            try:
                # 서버별 등록된 명령어 확인
                commands = await client.http.get_guild_commands(client.user.id, guild_id)
                
                if commands:
                    logger.info(f"서버 ID {guild_id}에 등록된 명령어 수: {len(commands)}")
                    for cmd in commands:
                        cmd_name = cmd.get('name', '알 수 없음')
                        cmd_description = cmd.get('description', '설명 없음')
                        logger.info(f"명령어: /{cmd_name} - {cmd_description}")
                else:
                    logger.warning(f"서버 ID {guild_id}에 등록된 명령어가 없습니다.")
            except Exception as e:
                logger.error(f"서버 ID {guild_id}의 명령어 확인 중 오류 발생: {str(e)}")
        
        # 글로벌 명령어 확인
        try:
            global_commands = await client.http.get_global_commands(client.user.id)
            
            if global_commands:
                logger.info(f"글로벌 명령어 수: {len(global_commands)}")
                for cmd in global_commands:
                    cmd_name = cmd.get('name', '알 수 없음')
                    cmd_description = cmd.get('description', '설명 없음')
                    logger.info(f"글로벌 명령어: /{cmd_name} - {cmd_description}")
            else:
                logger.warning("글로벌 명령어가 없습니다.")
        except Exception as e:
            logger.error(f"글로벌 명령어 확인 중 오류 발생: {str(e)}")
        
        # 봇 연결 종료
        await client.close()
        
    except ModuleNotFoundError as e:
        logger.error(f"필요한 모듈을 찾을 수 없습니다: {str(e)}")
        logger.error("스크립트는 'peanut' 디렉토리와 같은 위치에서 실행해야 합니다.")
    except Exception as e:
        logger.error(f"명령어 확인 중 오류 발생: {str(e)}", exc_info=True)

def main():
    """메인 실행 함수"""
    try:
        # 비동기 함수 실행
        asyncio.run(check_commands())
    except KeyboardInterrupt:
        logger.info("사용자에 의해 프로그램이 중단되었습니다.")
    except Exception as e:
        logger.error(f"프로그램 실행 중 오류 발생: {str(e)}", exc_info=True)
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main()) 