import os
import logging
from pathlib import Path
from dotenv import load_dotenv

# 로깅 설정
logger = logging.getLogger('discord.config')

# 프로젝트 루트 디렉토리 찾기
def find_root_dir():
    """프로젝트 루트 디렉토리 찾기"""
    current_dir = Path(__file__).resolve().parent.parent
    return current_dir

# 환경 변수 로드
def load_env():
    """환경 변수 로드"""
    root_dir = find_root_dir()
    env_path = root_dir / '.env'
    
    if env_path.exists():
        load_dotenv(env_path)
        logger.info(f".env 파일이 로드되었습니다: {env_path}")
    else:
        logger.warning(f".env 파일을 찾을 수 없습니다: {env_path}")

# 설정 가져오기
def get_config():
    """환경 설정 가져오기"""
    # 환경 변수 로드
    load_env()
    
    # 기본 설정
    config = {
        'DISCORD_TOKEN': os.getenv('DISCORD_TOKEN'),
        'DATABASE_PATH': os.getenv('DATABASE_PATH', 'db/discord_messages.db'),
        'COLLECTION_INTERVAL': int(os.getenv('COLLECTION_INTERVAL', 3 * 60 * 60)),  # 기본 3시간 (초 단위)
        'MAX_MESSAGES_PER_FETCH': int(os.getenv('MAX_MESSAGES_PER_FETCH', 1000)),   # 한 번에 가져올 최대 메시지 수
        'LOG_LEVEL': os.getenv('LOG_LEVEL', 'INFO'),
        'ALLOWED_GUILD_IDS': os.getenv('ALLOWED_GUILD_IDS', ''),
        
        # LLM 관련 설정
        'LLM_API_URL': os.getenv('LLM_API_URL', 'http://localhost:1234/v1/chat/completions'),
        'BOT_ID': os.getenv('BOT_ID')
    }
    
    # 토큰 검증
    if not config['DISCORD_TOKEN']:
        logger.error("DISCORD_TOKEN이 설정되지 않았습니다. .env 파일을 확인하세요.")
    
    return config 