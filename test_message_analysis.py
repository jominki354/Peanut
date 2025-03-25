#!/usr/bin/env python3
"""
메시지 분석 테스트 스크립트
"""

import sys
import json
from pathlib import Path
import logging

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

def test_message_analysis():
    """메시지 분석 기능 테스트"""
    from peanut.utils.collector import MessageCollector
    
    logger.info("메시지 분석 테스트 시작...")
    
    # 수집기 생성 (봇 없이 독립적으로 사용)
    collector = MessageCollector(bot=None)
    
    # 테스트할 메시지 샘플
    test_messages = [
        """fleet manager
외국 브랜치에서 퍼온기능을 당근에 맞게 조금 수정했음
View Dashcam Footage: 주행로그를 볼수 있으며, 다운로드를 받을수 있다.
View Screen Recordings: 화면녹화로그를 볼수 있으며, 다운로드를 받을 수 있다.
Error Logs, Navigation: 작동안함
Tools : 설정값을 백업 및 복원가능

당근마스터가 분석을 위해 rlog와 qcamera를 요청하면?
Dashcam Routes에 들어가서
해당주행로그를 찾고..
1분단위로 되어 있는곳에서 해당증상이 발견된 영상을 찾는다.
찾았으면 잠시 멈추고 화면 아래에 있는 download: rlog 와 qcamera를 받고 upload 또는 카톡, 이메일등을 이용하여 보내준다.
엉뚱한거 보내주면, 그뒤로 분석안해줌
항상 최신버젼의 당근버젼을 사용해야함""",

        """제목: Python 웹 스크래핑 가이드
웹 스크래핑을 위한 기본 도구:
- BeautifulSoup4: HTML 파싱
- Requests: HTTP 요청 처리
- Selenium: 동적 웹페이지 처리

설치 방법:
```
pip install beautifulsoup4 requests selenium
```

주의사항:
1. 웹사이트의 robots.txt 확인
2. 적절한 딜레이 설정
3. 사용자 에이전트 설정

예제 코드:
```python
import requests
from bs4 import BeautifulSoup

url = 'https://example.com'
response = requests.get(url)
soup = BeautifulSoup(response.text, 'html.parser')
title = soup.title.text
print(title)
```"""
    ]
    
    # 각 메시지 분석
    for i, message in enumerate(test_messages):
        logger.info(f"\n{'='*50}\n테스트 메시지 #{i+1}\n{'='*50}")
        print(f"원본 메시지:\n{message}\n")
        
        # 메시지 분석
        analysis = collector.analyze_message_content(message)
        
        # 결과 출력 (보기 좋게 포맷팅)
        print("\n분석 결과:")
        print(f"- 주제: {', '.join(analysis['topics'])}")
        print(f"- 메시지 유형: {analysis['message_type']}")
        print(f"- 콘텐츠 구조: {', '.join(analysis['content_structure'])}")
        print(f"- 마크다운 사용: {', '.join(analysis['markdown_used']) if analysis['markdown_used'] else '없음'}")
        
        # 섹션 정보 출력
        print("\n섹션 분석:")
        for j, section in enumerate(analysis['sections']):
            print(f"\n섹션 #{j+1}:")
            print(f"- 제목: {section['title']}")
            print(f"- 하위 주제: {', '.join(section['subtopics']) if section['subtopics'] else '없음'}")
            # 콘텐츠는 너무 길어서 일부만 출력
            content_preview = section['content'][:100] + "..." if len(section['content']) > 100 else section['content']
            print(f"- 콘텐츠 미리보기: {content_preview}")
        
        # JSON 형식으로도 출력
        print("\n전체 분석 결과 (JSON):")
        pretty_json = json.dumps(analysis, ensure_ascii=False, indent=2)
        print(pretty_json)

if __name__ == "__main__":
    logger.info("테스트 스크립트 시작...")
    test_message_analysis()
    logger.info("테스트 완료!") 