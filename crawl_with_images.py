from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
import time
import json
import os
import re
import logging
import requests
import base64
from urllib.parse import urlparse, urljoin
from pathlib import Path
import hashlib
import random

# 로깅 설정
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[logging.FileHandler("carrot_crawl_with_images.log", encoding='utf-8'),
                              logging.StreamHandler()])

# 크롤링 결과 저장할 디렉토리
OUTPUT_DIR = "carrotpilot_data_with_images"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 이미지 저장 디렉토리
IMAGE_DIR = os.path.join(OUTPUT_DIR, "images")
os.makedirs(IMAGE_DIR, exist_ok=True)

# 방문한 URL 추적
visited_urls = set()

# 크롤링된 데이터
crawled_data = {
    "pages": []
}

# 목표 메뉴 목록
TARGET_MENUS = [
    "당근파일럿 가이드",
    "롱컨 개조 방법",
    "롱컨개조를 하는 이유",
    "HDA1 차량의 배선 개조",
    "HDA2 차량의 배선 개조 (26핀 하네스)",
    "HDA2 차량의 배선 개조 (18핀 하네스)",
    "당근파일럿 기초설정",
    "당근네비 & 당근맨 설치방법",
    "추가 정보 - 무선 adb",
    "SSH 키 생성 & 등록",
    "Fleet",
    "설정 백업 방법",
    "로그 관리 방법",
    "화면 녹화 및 다운로드",
    "FAQ",
    "통합 설명",
    "버튼 스패밍 (비롱컨)",
    "당근맨",
    "기본 설명",
    "튜닝",
    "롱컨 튜닝",
    "조향 튜닝",
    "당근파일럿 기능",
    "레이더트랙",
    "경로 기반 속도 제어",
    "DM 끄기",
    "Developers",
    "SSH 접속 ( PC로 )",
    "SSH 접속 ( 휴대폰으로 )",
    "시뮬레이터",
    "PlotJuggler",
    "Cabana"
]

# 크롤링된 메뉴 추적
crawled_menus = set()

def setup_driver():
    """Chrome WebDriver 설정"""
    chrome_options = Options()
    chrome_options.add_argument("--log-level=3")
    # 브라우저 창 크기 설정 (더 큰 창은 모바일 레이아웃을 피함)
    chrome_options.add_argument("--window-size=1920,1080")
    # 헤드리스 모드 비활성화 - GitBook 접근 문제 해결
    chrome_options.headless = False
    
    # 사용자 에이전트 설정 - 일반 브라우저로 가장
    chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36")
    
    # 쿠키 관련 설정
    chrome_options.add_argument("--enable-cookies")
    
    # 자바스크립트 관련 설정
    chrome_options.add_argument("--enable-javascript")
    
    # 인증 창 방지 및 자동화 감지 회피
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option("useAutomationExtension", False)
    
    # 기타 성능 향상 설정
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-gpu")
    
    driver = webdriver.Chrome(options=chrome_options)
    
    # 웹드라이버 감지 회피
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    driver.execute_script("Object.defineProperty(navigator, 'languages', {get: () => ['ko-KR', 'ko', 'en-US', 'en']})")
    driver.execute_script("Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]})")
    
    # 페이지 로드 타임아웃 설정
    driver.set_page_load_timeout(40)
    return driver

def wait_for_page_load(driver, timeout=20):
    """페이지가 완전히 로드될 때까지 기다림 - 대기 시간 증가"""
    try:
        # DOM이 완전히 로드될 때까지 대기
        WebDriverWait(driver, timeout).until(
            lambda d: d.execute_script('return document.readyState') == 'complete'
        )
        
        # 주요 컨텐츠 로딩 확인 시도
        try:
            WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.TAG_NAME, 'article'))
            )
        except:
            pass  # 무시하고 계속 진행
        
        # 추가 대기 - GitBook의 컨텐츠 로딩 및 JavaScript 실행을 위해
        time.sleep(7)
        return True
    except TimeoutException:
        logging.warning(f"페이지 로딩 타임아웃: {driver.current_url}")
        return False

def download_image(url, base_url, referer=None):
    """이미지 다운로드 및 저장"""
    try:
        # URL이 상대 경로인 경우 절대 경로로 변환
        if not url.startswith(('http://', 'https://')) and base_url:
            url = urljoin(base_url, url)
        
        # URL 유효성 검사
        if not url.startswith(('http://', 'https://')):
            logging.warning(f"유효하지 않은 이미지 URL: {url}")
            return None
            
        # 이미지 URL에서 파일명 추출을 위한 해시 생성
        url_hash = hashlib.md5(url.encode()).hexdigest()
        
        # 이미지 파일 확장자 추출 시도
        parsed_url = urlparse(url)
        path = parsed_url.path
        ext = os.path.splitext(path)[1].lower()
        
        # 확장자가 없거나 유효하지 않은 경우 기본값 설정
        valid_exts = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg'}
        if ext not in valid_exts:
            ext = '.jpg'  # 기본 확장자
            
        # 이미지 파일 경로 생성
        image_filename = f"{url_hash}{ext}"
        image_path = os.path.join(IMAGE_DIR, image_filename)
        
        # 이미 다운로드된 이미지인지 확인
        if os.path.exists(image_path):
            logging.info(f"이미 다운로드된 이미지: {url}")
            return image_filename
            
        # HTTP 헤더 설정
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        # 리퍼러 설정 (제공된 경우)
        if referer:
            headers['Referer'] = referer
            
        # 이미지 다운로드
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()  # HTTP 오류 발생 시 예외 발생
        
        # 이미지 저장
        with open(image_path, 'wb') as f:
            f.write(response.content)
            
        logging.info(f"이미지 다운로드 성공: {url} -> {image_path}")
        return image_filename
        
    except Exception as e:
        logging.error(f"이미지 다운로드 실패: {url} - {str(e)}")
        return None

def extract_images_from_page(driver, base_url):
    """페이지 내 이미지 추출 및 다운로드"""
    images = []
    
    try:
        # 다양한 이미지 선택자로 시도
        selectors = [
            "img", 
            ".image-container img", 
            ".markdown-section img", 
            "article img", 
            "[role='main'] img",
            ".content img",
            ".book-body img"
        ]
        
        found_images = set()  # 중복 방지를 위한 세트
        
        for selector in selectors:
            try:
                img_elements = driver.find_elements(By.CSS_SELECTOR, selector)
                
                for img in img_elements:
                    try:
                        # src 또는 data-src 속성 확인
                        img_url = img.get_attribute("src") or img.get_attribute("data-src")
                        
                        if not img_url:
                            continue
                            
                        # 이미 처리한 이미지 URL인지 확인
                        if img_url in found_images:
                            continue
                            
                        found_images.add(img_url)
                        
                        # alt 텍스트 가져오기
                        alt_text = img.get_attribute("alt") or ""
                        
                        # 이미지 다운로드
                        image_filename = download_image(img_url, base_url)
                        
                        if image_filename:
                            images.append({
                                "url": img_url,
                                "alt": alt_text,
                                "filename": image_filename
                            })
                            
                    except StaleElementReferenceException:
                        continue
                        
            except Exception as e:
                logging.debug(f"이미지 선택자 {selector} 실패: {str(e)}")
                continue
                
    except Exception as e:
        logging.error(f"이미지 추출 중 오류 발생: {str(e)}")
        
    logging.info(f"총 {len(images)}개 이미지 추출 완료")
    return images

def extract_page_content(driver, url, title=None):
    """페이지 내용 추출 - 추가 선택자 및 예외 처리"""
    # 제목이 제공되지 않은 경우 페이지에서 추출
    if not title:
        try:
            # 다양한 제목 선택자 시도
            title_selectors = [
                "h1", "h2", ".page-title", "header h1", ".title", 
                "[class*='title']", ".content-title", ".document-title",
                ".heading", "main h1", "main h2", "article h1", "article h2"
            ]
            for selector in title_selectors:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                for element in elements:
                    title_text = element.text.strip()
                    if title_text and len(title_text) > 0:
                        title = title_text
                        break
                if title:
                    break
                    
            # 그래도 없으면 타이틀 태그 사용
            if not title:
                title = driver.title.strip()
                
            # 불필요한 접미사 제거
            title = re.sub(r' \| CarrotPilot$', '', title)
        except Exception as e:
            logging.warning(f"제목 추출 실패: {url} - {str(e)}")
            title = url.split('/')[-1].replace('-', ' ').title() if url else "제목 없음"
    
    # 내용 추출 - 다양한 선택자 시도
    content = ""
    selectors = [
        ".page-content", "article", ".markdown-section", "main", 
        ".content", ".gitbook-content", ".book-body", ".body", 
        "#main-content", ".wrapper", ".document-container", ".text-content",
        "div[class*='content']", ".inner-content", "[role='main']",
        ".page-inner", "#book-content", ".page-wrapper"
    ]
    
    for selector in selectors:
        try:
            elements = driver.find_elements(By.CSS_SELECTOR, selector)
            for element in elements:
                try:
                    text = element.text.strip()
                    if text and len(text) > content_length(content):
                        content = text
                except StaleElementReferenceException:
                    continue
        except Exception as e:
            logging.debug(f"선택자 {selector} 실패: {str(e)}")
            continue
    
    # 내용이 여전히 비어있으면 body 전체 내용 가져오기
    if not content or "Page not found" in content or "Content owner not found" in content:
        try:
            body_content = driver.find_element(By.TAG_NAME, "body").text.strip()
            
            # 페이지를 찾을 수 없음 메시지 필터링
            if not content or (len(body_content) > len(content) and 
                              "Page not found" not in body_content and 
                              "Content owner not found" not in body_content):
                content = body_content
        except Exception as e:
            logging.warning(f"본문 추출 실패: {url} - {str(e)}")
            content = "내용을 추출할 수 없습니다."
    
    # 불필요한 공백 및 중복 줄바꿈 제거
    content = re.sub(r'\n{3,}', '\n\n', content)
    content = content.replace('\t', ' ')
    
    # 내용이 너무 짧거나 오류 메시지 포함 시 유효하지 않은 콘텐츠로 간주
    if (len(content) < 50 or 
        "Page not found" in content or 
        "Content owner not found" in content or 
        "찾을 수 없" in content):
        logging.warning(f"유효하지 않은 콘텐츠: {url} - {content[:100]}...")
        return None
    
    # 이미지 추출 및 다운로드
    images = extract_images_from_page(driver, url)
    
    return {
        "title": title,
        "url": url,
        "content": content,
        "images": images
    }

def content_length(text):
    """텍스트의 길이를 반환 (None이나 빈 문자열 처리)"""
    return len(text) if text else 0

def extract_menu_links(driver):
    """메뉴에서 링크 추출 - 더 많은 선택자 시도"""
    links = []
    
    # 다양한 GitBook 레이아웃 선택자
    selectors = [
        ".group a", "nav a", ".sidebar-content a", ".menu-list a", 
        ".sidebar a", ".menu a", ".navigation a", ".book-summary a",
        "aside a", ".summary a", "ul.summary a", "ul.menu a", 
        "[role='navigation'] a", "ul li a", ".book-menu-content a",
        "li a", ".menu-item a", "a.menu-item", ".nav-item a",
        ".side-bar a", ".sidebar-menu a", ".navigation-panel a"
    ]
    
    for selector in selectors:
        try:
            elements = driver.find_elements(By.CSS_SELECTOR, selector)
            for element in elements:
                try:
                    href = element.get_attribute("href")
                    title = element.text.strip()
                    
                    if (href and title and 
                        not href.startswith("#") and 
                        not href.startswith("javascript") and 
                        "carrotpilot" in href):
                        links.append({"url": href, "title": title})
                except StaleElementReferenceException:
                    continue
        except Exception as e:
            logging.debug(f"메뉴 선택자 {selector} 실패: {str(e)}")
            continue
    
    # 중복 제거
    unique_links = []
    seen_urls = set()
    
    for link in links:
        normalized_url = normalize_url(link["url"])
        if normalized_url not in seen_urls:
            seen_urls.add(normalized_url)
            
            # 타겟 메뉴와 비슷한지 확인
            for target in TARGET_MENUS:
                if is_similar_title(link["title"], target):
                    link["matched_target"] = target
                    crawled_menus.add(target)
                    unique_links.append(link)
                    break
            else:
                # 타겟 메뉴와 일치하지 않더라도 일단 저장
                unique_links.append(link)
    
    # 수집되지 않은 타겟 메뉴 확인 및 직접 URL 추론 시도
    for target in TARGET_MENUS:
        if target not in crawled_menus:
            # 이미 찾은 URL에서 패턴 추출
            if unique_links:
                # URL 구조 추론
                base_url = '/'.join(unique_links[0]["url"].split('/')[:-1])
                # 타겟명을 URL 형식으로 변환
                slug = target.lower().replace(" ", "-").replace("(", "").replace(")", "").replace("&", "and")
                inferred_url = f"{base_url}/{slug}"
                
                unique_links.append({
                    "url": inferred_url, 
                    "title": target,
                    "inferred": True  # 추론된 URL 표시
                })
                
                logging.info(f"추론된 URL 추가: {target} -> {inferred_url}")
            
    return unique_links

def normalize_url(url):
    """URL 정규화"""
    if not url:
        return ""
    
    # 프로토콜, 쿼리 파라미터, 해시 제거
    normalized = re.sub(r'^https?://', '', url)
    normalized = re.sub(r'\?.*$', '', normalized)
    normalized = re.sub(r'#.*$', '', normalized)
    
    # 끝에 오는 슬래시 제거
    normalized = re.sub(r'/$', '', normalized)
    
    return normalized.lower()

def is_similar_title(title1, title2):
    """두 제목이 유사한지 확인"""
    if not title1 or not title2:
        return False
    
    # 대소문자 구분 없이 비교
    title1 = title1.lower().strip()
    title2 = title2.lower().strip()
    
    # 정확히 일치하면 True
    if title1 == title2:
        return True
    
    # 하나가 다른 하나에 포함되면 True
    if title1 in title2 or title2 in title1:
        return True
    
    # 공백, 특수문자 제거 후 비교
    clean_title1 = re.sub(r'[^\w가-힣]', '', title1)
    clean_title2 = re.sub(r'[^\w가-힣]', '', title2)
    
    if clean_title1 == clean_title2:
        return True
    
    # 편집 거리 계산 (레벤슈타인 거리)
    max_len = max(len(title1), len(title2))
    if max_len == 0:
        return False
    
    import difflib
    similarity = difflib.SequenceMatcher(None, title1, title2).ratio()
    
    # 유사도가 0.8 이상이면 유사한 것으로 간주
    return similarity >= 0.8

def crawl_page(driver, url, title=None, depth=0, max_depth=3):
    """페이지를 크롤링하고 링크 추적"""
    # 방문한 URL인지 확인
    normalized_url = normalize_url(url)
    if normalized_url in visited_urls:
        logging.info(f"이미 방문한 페이지 건너뜀: {url}")
        return
    
    # 방문 기록
    visited_urls.add(normalized_url)
    
    logging.info(f"크롤링 중: {url} (제목: {title or '미정'}, 깊이: {depth})")
    
    try:
        # 페이지 로드
        driver.get(url)
        success = wait_for_page_load(driver)
        
        if not success:
            logging.warning(f"페이지 로드 실패: {url}")
            return
            
        # 현재 URL 가져오기 (리디렉션 후)
        current_url = driver.current_url
        
        # 페이지 내용 추출
        page_data = extract_page_content(driver, current_url, title)
        
        if page_data:
            logging.info(f"페이지 콘텐츠 추출 성공: {current_url} - 제목: {page_data['title']}")
            crawled_data["pages"].append(page_data)
            
            # 정기적으로 중간 결과 저장
            if len(crawled_data["pages"]) % 5 == 0:
                save_crawled_data()
        else:
            logging.warning(f"유효한 콘텐츠 없음: {current_url}")
            return
        
        # 깊이 제한 확인
        if depth >= max_depth:
            logging.info(f"최대 깊이 도달: {url} (깊이: {depth})")
            return
            
        # 메뉴 링크 추출
        menu_links = extract_menu_links(driver)
        logging.info(f"메뉴에서 {len(menu_links)}개 링크 추출됨")
        
        # 각 링크 방문
        for link in menu_links:
            link_url = link["url"]
            link_title = link["title"]
            
            # 이미 방문한 URL이면 건너뜀
            if normalize_url(link_url) in visited_urls:
                continue
                
            # 페이지가 추론된 URL인 경우 표시
            inferred = link.get("inferred", False)
            if inferred:
                logging.info(f"추론된 URL 방문 시도: {link_url} (제목: {link_title})")
            
            # 하위 페이지 크롤링
            crawl_page(driver, link_url, link_title, depth + 1, max_depth)
            
    except Exception as e:
        logging.error(f"페이지 크롤링 중 오류 발생: {url} - {str(e)}")

def save_crawled_data():
    """크롤링 데이터 저장"""
    file_path = os.path.join(OUTPUT_DIR, "carrotpilot_crawled_data.json")
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(crawled_data, f, ensure_ascii=False, indent=2)
        logging.info(f"크롤링 데이터 저장 완료: {file_path}")
    except Exception as e:
        logging.error(f"데이터 저장 실패: {str(e)}")

def create_finetuning_dataset():
    """미세조정을 위한 QA 데이터셋 생성"""
    if not crawled_data["pages"]:
        logging.warning("데이터셋을 생성할 페이지가 없습니다.")
        return
        
    # 데이터셋 형식: [{"prompt": "질문", "response": "답변"}]
    dataset = []
    
    for page in crawled_data["pages"]:
        title = page["title"]
        content = page["content"]
        url = page["url"]
        images = page["images"]
        
        # 일반적인 형식의 질문 생성
        base_questions = [
            f"{title}에 대해 설명해주세요.",
            f"{title}이란 무엇인가요?",
            f"{title}의 주요 특징은 무엇인가요?",
            f"{title}을 어떻게 사용하나요?",
        ]
        
        # 타이틀 기반 추가 질문 생성
        if "방법" in title or "개조" in title:
            base_questions.append(f"{title} 절차를 단계별로 알려주세요.")
            base_questions.append(f"{title}을 위해 필요한 준비물은 무엇인가요?")
            
        if "설치" in title:
            base_questions.append(f"{title}의 요구사항은 무엇인가요?")
            base_questions.append(f"{title} 과정에서 발생할 수 있는 문제와 해결책은?")
            
        if "튜닝" in title:
            base_questions.append(f"{title}으로 얻을 수 있는 이점은 무엇인가요?")
            base_questions.append(f"{title}시 주의해야 할 점은 무엇인가요?")
            
        if "로그" in title or "관리" in title:
            base_questions.append(f"{title}에 대한 기본 정보를 알려주세요.")
            base_questions.append(f"{title}에 접근하는 방법은?")
            
        # 이미지 관련 질문 추가
        if images:
            base_questions.append(f"{title}의 이미지를 보여주세요.")
            base_questions.append(f"{title}에 대한 시각적 가이드를 제공해주세요.")
        
        # 각 질문에 대한 답변 생성
        for question in base_questions:
            # 이미지 정보를 포함한 답변 생성
            answer = content
            
            # 이미지가 있으면 답변에 이미지 정보 추가
            if images and ("이미지" in question or "시각적" in question):
                image_descriptions = []
                
                for idx, img in enumerate(images, 1):
                    img_filename = img["filename"]
                    img_alt = img["alt"] if img["alt"] else f"{title} 관련 이미지 {idx}"
                    
                    image_path = os.path.join(IMAGE_DIR, img_filename)
                    relative_path = os.path.relpath(image_path, OUTPUT_DIR)
                    
                    image_desc = f"[이미지 {idx}: {img_alt}] - 경로: {relative_path}"
                    image_descriptions.append(image_desc)
                
                # 이미지 설명을 답변에 추가
                if image_descriptions:
                    answer += "\n\n관련 이미지:\n" + "\n".join(image_descriptions)
            
            # 데이터셋에 추가
            dataset.append({
                "prompt": question,
                "response": answer
            })
    
    # 데이터셋 저장 - JSON 형식
    json_path = os.path.join(OUTPUT_DIR, "carrotpilot_finetuning_dataset.json")
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(dataset, f, ensure_ascii=False, indent=2)
    
    # 데이터셋 저장 - JSONL 형식 (한 줄에 하나의 JSON 객체)
    jsonl_path = os.path.join(OUTPUT_DIR, "carrotpilot_finetuning_dataset.jsonl")
    with open(jsonl_path, 'w', encoding='utf-8') as f:
        for item in dataset:
            f.write(json.dumps(item, ensure_ascii=False) + '\n')
    
    logging.info(f"미세조정 데이터셋 생성 완료: {len(dataset)}개 QA 쌍")
    logging.info(f"데이터셋 저장 위치: {json_path}, {jsonl_path}")

def main():
    """메인 실행 함수"""
    # 크롤링할 메뉴 목록 - 사용자가 지정한 메뉴로 제한
    target_menus = [
        "당근파일럿 가이드",
        "롱컨 개조 방법",
        "롱컨개조를 하는 이유",
        "HDA1 차량의 배선 개조",
        "HDA2 차량의 배선 개조 (26핀 하네스)",
        "HDA2 차량의 배선 개조 (18핀 하네스)",
        "당근파일럿 기초설정",
        "당근네비 & 당근맨 설치방법",
        "추가 정보 - 무선 adb",
        "SSH 키 생성 & 등록",
        "Fleet",
        "설정 백업 방법",
        "로그 관리 방법",
        "화면 녹화 및 다운로드",
        "FAQ",
        "통합 설명",
        "버튼 스패밍 (비롱컨)",
        "당근맨",
        "기본 설명",
        "튜닝",
        "롱컨 튜닝",
        "조향 튜닝",
        "당근파일럿 기능",
        "레이더트랙",
        "경로 기반 속도 제어",
        "DM 끄기",
        "Developers",
        "SSH 접속 ( PC로 )",
        "SSH 접속 ( 휴대폰으로 )",
        "시뮬레이터",
        "PlotJuggler",
        "Cabana"
    ]
    
    # TARGET_MENUS 글로벌 변수 업데이트
    global TARGET_MENUS
    TARGET_MENUS = target_menus
    
    logging.info("크롤링 시작")
    logging.info(f"출력 디렉토리: {OUTPUT_DIR}")
    logging.info(f"이미지 디렉토리: {IMAGE_DIR}")
    
    driver = None
    try:
        driver = setup_driver()
        
        # 메인 페이지 방문
        main_url = "https://g4iwnl.gitbook.io/carrotpilot/"
        logging.info(f"메인 페이지 방문 중: {main_url}")
        driver.get(main_url)
        success = wait_for_page_load(driver)
        
        if not success:
            logging.error(f"메인 페이지 로드 실패: {main_url}")
            return
        
        # 현재 URL 가져오기 (리디렉션 후)
        current_url = driver.current_url
        logging.info(f"메인 페이지 로드 성공: {current_url}")
        
        # 메인 페이지 내용 추출
        main_page_data = extract_page_content(driver, current_url, "당근파일럿 가이드")
        if main_page_data:
            logging.info(f"메인 페이지 콘텐츠 추출 성공: {current_url}")
            crawled_data["pages"].append(main_page_data)
            visited_urls.add(normalize_url(current_url))
            save_crawled_data()
        
        # 스크롤하면서 모든 메뉴 링크 추출
        found_menu_items = []
        
        # 스크롤 및 메뉴 링크 추출 함수
        def extract_all_menu_links():
            # 다양한 메뉴 링크 선택자들
            menu_selectors = [
                ".group a", "nav a", ".sidebar-content a", ".menu-list a", 
                ".sidebar a", ".menu a", ".navigation a", ".book-summary a",
                "aside a", ".summary a", "ul.summary a", "ul.menu a", 
                "[role='navigation'] a", "ul li a", ".book-menu-content a",
                "li a", ".menu-item a", "a.menu-item", ".nav-item a",
                ".side-bar a", ".sidebar-menu a", ".navigation-panel a",
                ".css-175oi2r a"  # GitBook의 신규 선택자도 추가
            ]
            
            all_menu_links = []
            
            # 스크롤하면서 메뉴 링크 추출
            for _ in range(10):  # 스크롤 최대 10회 반복
                # 현재 보이는 모든 링크 추출
                for selector in menu_selectors:
                    try:
                        elements = driver.find_elements(By.CSS_SELECTOR, selector)
                        for element in elements:
                            try:
                                href = element.get_attribute("href")
                                title = element.text.strip()
                                
                                if (href and title and 
                                    not href.startswith("#") and 
                                    not href.startswith("javascript") and 
                                    "carrotpilot" in href):
                                    
                                    # 중복 방지를 위해 URL 정규화
                                    normalized_url = normalize_url(href)
                                    
                                    # 특정 메뉴 항목인지 확인
                                    is_target = False
                                    target_title = ""
                                    for target in target_menus:
                                        if is_similar_title(title, target):
                                            is_target = True
                                            target_title = target
                                            break
                                    
                                    all_menu_links.append({
                                        "url": href,
                                        "title": title,
                                        "normalized_url": normalized_url,
                                        "is_target": is_target,
                                        "target_title": target_title
                                    })
                            except StaleElementReferenceException:
                                continue
                    except Exception as e:
                        logging.debug(f"메뉴 선택자 {selector} 실패: {str(e)}")
                
                # 페이지를 아래로 스크롤
                driver.execute_script("window.scrollBy(0, 300);")
                time.sleep(1)  # 스크롤 후 잠시 대기
            
            # 중복 제거
            unique_links = []
            seen_urls = set()
            
            for link in all_menu_links:
                if link["normalized_url"] not in seen_urls:
                    seen_urls.add(link["normalized_url"])
                    unique_links.append(link)
            
            return unique_links
        
        # 메뉴 링크 추출
        menu_links = extract_all_menu_links()
        logging.info(f"총 {len(menu_links)}개 메뉴 링크 추출됨")
        
        # 목표 메뉴 항목만 필터링
        target_links = [link for link in menu_links if link["is_target"]]
        other_links = [link for link in menu_links if not link["is_target"]]
        
        logging.info(f"목표 메뉴 항목: {len(target_links)}개, 기타 메뉴 항목: {len(other_links)}개")
        
        # 추출된 목표 메뉴 항목의 제목 출력
        found_titles = [link["title"] for link in target_links]
        logging.info(f"추출된 목표 메뉴 항목: {found_titles}")
        
        # 찾지 못한 메뉴 항목 확인
        found_target_titles = {link["target_title"] for link in target_links if link["target_title"]}
        missing_targets = [target for target in target_menus if target not in found_target_titles]
        if missing_targets:
            logging.warning(f"찾지 못한 메뉴 항목: {missing_targets}")
        
        # 모든 링크 목록 (목표 메뉴 우선, 나머지는 추가)
        all_links = target_links + other_links
        
        # 각 링크 방문 및 내용 추출
        for i, link in enumerate(all_links):
            url = link["url"]
            title = link["title"]
            is_target = link["is_target"]
            
            # 이미 방문한 URL이면 건너뜀
            if normalize_url(url) in visited_urls:
                logging.info(f"이미 방문한 페이지 건너뜀: {url}")
                continue
            
            # 목표 메뉴가 아니고, 목표 메뉴를 충분히 크롤링했으면 건너뜀
            if not is_target and len([p for p in crawled_data["pages"] if p["url"] in [l["url"] for l in target_links]]) >= len(target_links) * 0.8:
                logging.info(f"비대상 메뉴 건너뜀 (충분한 대상 메뉴 크롤링 완료): {url}")
                continue
                
            try:
                logging.info(f"페이지 방문 중 ({i+1}/{len(all_links)}): {url} (제목: {title}, 목표 메뉴: {'예' if is_target else '아니오'})")
                
                # 페이지 로드
                driver.get(url)
                success = wait_for_page_load(driver)
                
                if not success:
                    logging.warning(f"페이지 로드 실패: {url}")
                    continue
                
                # 현재 URL 가져오기 (리디렉션 후)
                current_url = driver.current_url
                
                # 페이지 내용 추출
                page_data = extract_page_content(driver, current_url, title)
                
                if page_data:
                    logging.info(f"페이지 콘텐츠 추출 성공: {current_url} - 제목: {page_data['title']}")
                    crawled_data["pages"].append(page_data)
                    visited_urls.add(normalize_url(current_url))
                    
                    # 정기적으로 중간 결과 저장
                    if len(crawled_data["pages"]) % 3 == 0:
                        save_crawled_data()
                else:
                    logging.warning(f"유효한 콘텐츠 없음: {current_url}")
                
                # 잠시 대기하여 서버 부하 및 봇 감지 방지
                wait_time = random.uniform(2, 4)
                logging.debug(f"다음 페이지 방문 전 {wait_time:.1f}초 대기")
                time.sleep(wait_time)
                
            except Exception as e:
                logging.error(f"페이지 처리 중 오류 발생: {url} - {str(e)}")
        
        # 최종 데이터 저장
        save_crawled_data()
        create_finetuning_dataset()
        
        # 크롤링 결과 요약
        logging.info(f"총 {len(crawled_data['pages'])}개 페이지 크롤링 완료")
        crawled_titles = [page["title"] for page in crawled_data["pages"]]
        logging.info(f"크롤링된 페이지 제목: {crawled_titles}")
        
        logging.info("크롤링 성공적으로 완료됨")
    except Exception as e:
        logging.error(f"크롤링 중 오류 발생: {str(e)}")
    finally:
        if driver:
            driver.quit()
            logging.info("웹드라이버 종료됨")

if __name__ == "__main__":
    main()  