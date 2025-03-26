import os
import sys
import asyncio
import logging
import json
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

async def create_guild_commands():
    """직접 Discord API를 호출하여 서버별 명령어를 생성하는 비동기 함수"""
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
                return
        
        if not allowed_guild_ids:
            logger.error("허용된 서버 ID가 없습니다.")
            return
        
        # 클라이언트 생성 및 로그인
        intents = discord.Intents.default()
        client = discord.Client(intents=intents)
        await client.login(token)
        
        logger.info(f"봇 ID: {client.user.id}")
        logger.info("Discord에 로그인했습니다.")
        
        # 1. 글로벌 명령어 초기화
        logger.info("글로벌 명령어 초기화 중...")
        await client.http.bulk_upsert_global_commands(client.user.id, [])
        logger.info("글로벌 명령어를 초기화했습니다.")
        
        # 2. 각 서버별 명령어 생성
        # 질문 명령어 정의
        question_command = {
            "name": "질문",
            "description": "당근파일럿 서버의 채팅데이터를 기반으로 질문에 답변합니다",
            "type": 1,  # 1 = CHAT_INPUT
            "options": [
                {
                    "name": "질문",
                    "description": "궁금한 내용을 질문해주세요",
                    "type": 3,  # 3 = STRING
                    "required": True
                }
            ]
        }
        
        for guild_id in allowed_guild_ids:
            try:
                logger.info(f"서버 ID {guild_id}의 모든 명령어 초기화 중...")
                # 서버의 모든 명령어 초기화
                await client.http.bulk_upsert_guild_commands(client.user.id, guild_id, [])
                logger.info(f"서버 ID {guild_id}의 모든 명령어를 초기화했습니다.")
                
                # 질문 명령어 등록
                logger.info(f"서버 ID {guild_id}에 질문 명령어 등록 중...")
                command_list = [question_command]
                
                # 서버에 명령어 등록
                await client.http.bulk_upsert_guild_commands(client.user.id, guild_id, command_list)
                logger.info(f"서버 ID {guild_id}에 {len(command_list)}개의 명령어를 등록했습니다.")
            except Exception as e:
                logger.error(f"서버 ID {guild_id} 명령어 등록 중 오류 발생: {str(e)}")
        
        # 3. 명령어 등록 확인
        logger.info("등록된 명령어 확인 중...")
        
        # 글로벌 명령어 확인
        try:
            global_commands = await client.http.get_global_commands(client.user.id)
            if global_commands:
                logger.warning(f"글로벌 명령어가 {len(global_commands)}개 남아있습니다.")
                for cmd in global_commands:
                    logger.warning(f"남아있는 글로벌 명령어: /{cmd.get('name', '알 수 없음')}")
            else:
                logger.info("글로벌 명령어가 없습니다. (정상)")
        except Exception as e:
            logger.error(f"글로벌 명령어 확인 중 오류 발생: {str(e)}")
        
        # 서버별 명령어 확인
        for guild_id in allowed_guild_ids:
            try:
                guild_commands = await client.http.get_guild_commands(client.user.id, guild_id)
                if guild_commands:
                    logger.info(f"서버 ID {guild_id}에 등록된 명령어 수: {len(guild_commands)}")
                    for cmd in guild_commands:
                        logger.info(f"서버 명령어: /{cmd.get('name', '알 수 없음')} - {cmd.get('description', '설명 없음')}")
                else:
                    logger.warning(f"서버 ID {guild_id}에 등록된 명령어가 없습니다.")
            except Exception as e:
                logger.error(f"서버 ID {guild_id}의 명령어 확인 중 오류 발생: {str(e)}")
        
        # 봇 연결 종료
        await client.close()
        logger.info("작업이 완료되었습니다.")
        
    except ModuleNotFoundError as e:
        logger.error(f"필요한 모듈을 찾을 수 없습니다: {str(e)}")
        logger.error("스크립트는 'peanut' 디렉토리와 같은 위치에서 실행해야 합니다.")
    except Exception as e:
        logger.error(f"명령어 생성 중 오류 발생: {str(e)}", exc_info=True)

def main():
    """메인 실행 함수"""
    try:
        # 비동기 함수 실행
        asyncio.run(create_guild_commands())
    except KeyboardInterrupt:
        logger.info("사용자에 의해 프로그램이 중단되었습니다.")
    except Exception as e:
        logger.error(f"프로그램 실행 중 오류 발생: {str(e)}", exc_info=True)
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main()) 