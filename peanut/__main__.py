import os
import sys
import logging

# 현재 디렉토리를 Python 경로에 추가 (상대 임포트를 위함)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from peanut.bot import PeanutBot

def main():
    """메인 실행 함수"""
    try:
        # 봇 생성 및 실행
        bot = PeanutBot()
        bot.run()
    except Exception as e:
        logging.error(f"봇 실행 중 오류 발생: {str(e)}", exc_info=True)
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main()) 