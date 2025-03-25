import os
import logging
import sys
import colorama
from pathlib import Path
from logging.handlers import RotatingFileHandler
from datetime import datetime

# 색상 초기화
colorama.init()

# 로그 색상 정의
class ColoredFormatter(logging.Formatter):
    """컬러 포맷 로깅 클래스"""
    
    # 로그 레벨별 색상 정의
    COLORS = {
        'DEBUG': colorama.Fore.CYAN,
        'INFO': colorama.Fore.GREEN,
        'WARNING': colorama.Fore.YELLOW,
        'ERROR': colorama.Fore.RED,
        'CRITICAL': colorama.Fore.MAGENTA + colorama.Style.BRIGHT,
    }
    
    def format(self, record):
        # 로그 레벨에 따른 색상 적용
        levelname = record.levelname
        if levelname in self.COLORS:
            record.levelname = f"{self.COLORS[levelname]}{levelname}{colorama.Style.RESET_ALL}"
            # 이모지 추가 (로그 레벨별)
            if record.levelno == logging.DEBUG:
                record.emoji = "🔍"
            elif record.levelno == logging.INFO:
                record.emoji = "ℹ️"
            elif record.levelno == logging.WARNING:
                record.emoji = "⚠️"
            elif record.levelno == logging.ERROR:
                record.emoji = "❌"
            elif record.levelno == logging.CRITICAL:
                record.emoji = "🔥"
        else:
            record.emoji = "  "
            
        # 메시지 본문에도 색상을 적용할 수 있음
        # 특정 패턴에 색상 추가 (예: 시간, URL 등)
        return super().format(record)

def setup_logger():
    """로그 설정"""
    # 로그 포맷 설정 (개선)
    date_format = "%Y-%m-%d %H:%M:%S"
    
    # 파일용 로그 포맷 (컬러 없음)
    file_log_format = "%(asctime)s [%(name)s] %(levelname)-8s %(message)s"
    file_formatter = logging.Formatter(file_log_format, date_format)
    
    # 콘솔용 로그 포맷 (컬러, 이모지 포함)
    console_log_format = "%(asctime)s %(emoji)s [%(name)s] %(levelname)-8s %(message)s"
    console_formatter = ColoredFormatter(console_log_format, date_format)
    
    # 로그 레벨 설정
    logger = logging.getLogger("discord")
    logger.setLevel(logging.INFO)
    
    # 로그 디렉토리 생성
    log_dir = "peanut/logs"
    os.makedirs(log_dir, exist_ok=True)
    
    # 날짜별 로그 파일 이름 생성
    current_date = datetime.now().strftime("%Y-%m-%d")
    log_filename = f"{log_dir}/discord_bot_{current_date}.log"
    
    # 파일 핸들러 설정 (RotatingFileHandler로 크기 제한)
    file_handler = RotatingFileHandler(
        log_filename, 
        encoding="utf-8",
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5
    )
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)
    
    # 표준 출력 핸들러 추가 (컬러 적용)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    # 주요 로그 레벨 설정
    logging.getLogger("discord.http").setLevel(logging.INFO)
    logging.getLogger("discord.gateway").setLevel(logging.INFO)
    logging.getLogger("discord.collector").setLevel(logging.INFO)
    logging.getLogger("discord.database").setLevel(logging.INFO)
    logging.getLogger("discord.llm").setLevel(logging.INFO)
    
    # 로그 파일 정보 출력
    logger.info(f"로그 파일 생성: {log_filename}")
    
    return logger 