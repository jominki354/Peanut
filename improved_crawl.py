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

# 로깅 설정
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[logging.FileHandler("carrot_crawl.log", encoding='utf-8'),
                              logging.StreamHandler()])

# 크롤링 결과 저장할 디렉토리
OUTPUT_DIR = "carrotpilot_data_improved"
os.makedirs(OUTPUT_DIR, exist_ok=True)

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
    chrome_options.headless = False  # 디버깅 시 False로 설정
    
    driver = webdriver.Chrome(options=chrome_options)
    driver.set_page_load_timeout(30)
    return driver

def wait_for_page_load(driver, timeout=10):
    """페이지가 완전히 로드될 때까지 기다림"""
    try:
        # DOM이 완전히 로드될 때까지 대기
        WebDriverWait(driver, timeout).until(
            lambda d: d.execute_script('return document.readyState') == 'complete'
        )
        # 추가 대기 - 일부 JS 로딩을 위해
        time.sleep(2)
        return True
    except TimeoutException:
        logging.warning(f"페이지 로딩 타임아웃: {driver.current_url}")
        return False

def extract_page_content(driver, url, title=None):
    """페이지 내용 추출"""
    # 제목이 제공되지 않은 경우 페이지에서 추출
    if not title:
        try:
            # 다양한 제목 선택자 시도
            title_selectors = [
                "h1", "h2", ".page-title", "header h1", ".title", 
                "[class*='title']", ".content-title", ".document-title"
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
        "div[class*='content']", ".inner-content", "[role='main']"
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
    if not content or "Page not found" in content:
        try:
            body_content = driver.find_element(By.TAG_NAME, "body").text.strip()
            
            # 페이지를 찾을 수 없음 메시지 필터링
            if not content or (len(body_content) > len(content) and "Page not found" not in body_content):
                content = body_content
        except Exception as e:
            logging.warning(f"본문 추출 실패: {url} - {str(e)}")
            content = "내용을 추출할 수 없습니다."
    
    # 불필요한 공백 및 중복 줄바꿈 제거
    content = re.sub(r'\n{3,}', '\n\n', content)
    content = content.replace('\t', ' ')
    
    # 내용이 너무 짧거나 "Page not found" 포함 시 유효하지 않은 콘텐츠로 간주
    if len(content) < 50 or "Page not found" in content or "찾을 수 없" in content:
        logging.warning(f"유효하지 않은 콘텐츠: {url} - {content[:100]}...")
        return None
    
    return {
        "title": title,
        "url": url,
        "content": content
    }

def content_length(text):
    """텍스트 길이 계산 (공백 제외)"""
    return len(re.sub(r'\s', '', text))

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
    # 트레일링 슬래시 제거 및 fragment 제거
    url = re.sub(r'[#?].*$', '', url.rstrip('/'))
    return url.lower()

def is_similar_title(title1, title2):
    """두 제목이 유사한지 확인"""
    # 소문자 변환, 특수문자 제거
    t1 = re.sub(r'[^\w\s]', '', title1.lower())
    t2 = re.sub(r'[^\w\s]', '', title2.lower())
    
    # 정확히 일치하는 경우
    if t1 == t2:
        return True
    
    # 하나가 다른 하나를 포함하는 경우
    if t1 in t2 or t2 in t1:
        return True
    
    # 단어 단위로 비교
    words1 = set(t1.split())
    words2 = set(t2.split())
    
    # 공통 단어 수
    common_words = words1.intersection(words2)
    
    # 최소 단어 길이의 절반 이상이 일치하면 유사하다고 판단
    min_words_len = min(len(words1), len(words2))
    if min_words_len > 0 and len(common_words) >= min_words_len / 2:
        return True
    
    return False

def crawl_page(driver, url, title=None, depth=0, max_depth=3):
    """페이지 크롤링"""
    if url in visited_urls:
        return
    
    normalized_url = normalize_url(url)
    if normalized_url in visited_urls:
        return
    
    visited_urls.add(normalized_url)
    logging.info(f"크롤링 중: {url} - {title or '제목 없음'} (깊이: {depth})")
    
    try:
        driver.get(url)
        # 페이지 로딩 대기
        if not wait_for_page_load(driver):
            logging.warning(f"페이지 로딩 실패: {url}")
            return
        
        # 스크롤 다운하여 모든 콘텐츠 로드
        scroll_page(driver)
        
        # 페이지 내용 추출
        page_data = extract_page_content(driver, url, title)
        
        # 유효한 콘텐츠가 있는 경우만 저장
        if page_data:
            crawled_data["pages"].append(page_data)
            # 데이터 저장
            save_crawled_data()
            
            # 진행 상황 출력
            logging.info(f"  - 내용 추출 완료: {page_data['title']} ({len(crawled_data['pages'])} 페이지 수집)")
        else:
            logging.warning(f"  - 유효한 내용 없음: {url}")
            return  # 유효한 내용이 없으면 링크 추출 중단
        
        # 최대 깊이에 도달하면 링크 추출 중단
        if depth >= max_depth:
            logging.info(f"최대 깊이 도달: {url}")
            return
            
        # 링크 추출
        links = extract_menu_links(driver)
        valid_links = [link for link in links if link["url"] not in visited_urls]
        logging.info(f"  - 발견된 새 링크: {len(valid_links)}개")
        
        # 모든 링크 방문
        for link in valid_links:
            # 서버 부하 방지를 위한 딜레이
            time.sleep(2)
            crawl_page(driver, link["url"], link.get("title"), depth + 1, max_depth)
                
    except Exception as e:
        logging.error(f"오류 발생: {url} - {str(e)}")

def scroll_page(driver):
    """페이지를 스크롤하여 모든 콘텐츠 로드"""
    try:
        # 점진적으로 스크롤
        last_height = driver.execute_script("return document.body.scrollHeight")
        
        for _ in range(5):  # 최대 5번 스크롤
            # 페이지 절반씩 스크롤
            driver.execute_script(f"window.scrollBy(0, {last_height / 2});")
            time.sleep(0.5)
            
            # 맨 아래까지 스크롤
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1)
            
            # 새 높이 계산
            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                break
            last_height = new_height
    except Exception as e:
        logging.warning(f"스크롤 오류: {str(e)}")

def save_crawled_data():
    """수집된 데이터 저장"""
    try:
        with open(f"{OUTPUT_DIR}/carrotpilot_crawled_data.json", "w", encoding="utf-8") as f:
            json.dump(crawled_data, f, ensure_ascii=False, indent=2)
        logging.debug(f"중간 데이터 저장 완료: {len(crawled_data['pages'])} 페이지")
    except Exception as e:
        logging.error(f"데이터 저장 오류: {str(e)}")

def create_finetuning_dataset():
    """파인튜닝을 위한 데이터셋 생성"""
    dataset = []
    
    # 유효한 페이지 필터링
    valid_pages = [page for page in crawled_data["pages"] 
                   if page["content"] and len(page["content"]) >= 50 
                   and "Page not found" not in page["content"]]
    
    logging.info(f"데이터셋 생성 중: 총 {len(valid_pages)}개의 유효한 페이지")
    
    for page in valid_pages:
        # 기본 질문-답변 쌍
        dataset.append({
            "instruction": f"{page['title']}에 대해 설명해주세요.",
            "output": page["content"]
        })
        
        dataset.append({
            "instruction": f"{page['title']}란 무엇인가요?",
            "output": page["content"]
        })
        
        # 추가 질문-답변 쌍 (내용에 따라)
        keywords = {
            "설치": ["설치 방법", "설치하는 법", "어떻게 설치"],
            "튜닝": ["튜닝 방법", "조절 방법", "어떻게 튜닝"],
            "개조": ["개조 방법", "어떻게 개조", "배선 연결"],
            "기능": ["기능 설명", "어떤 기능", "주요 기능"],
            "접속": ["접속 방법", "어떻게 접속", "연결 방법"],
            "설정": ["설정 방법", "어떻게 설정", "구성 방법"]
        }
        
        for keyword, questions in keywords.items():
            if keyword in page["title"].lower() or keyword in page["content"].lower():
                for question_template in questions:
                    dataset.append({
                        "instruction": f"{page['title']}의 {question_template}을 알려주세요.",
                        "output": page["content"]
                    })
    
    # 특별한 질문 추가 (일반적인 질문)
    general_questions = [
        "당근파일럿이란 무엇인가요?",
        "당근파일럿을 어떻게 사용하나요?",
        "당근파일럿의 주요 기능은 무엇인가요?",
        "롱컨과 비롱컨의 차이는 무엇인가요?",
        "당근파일럿 설치 방법을 알려주세요.",
        "레이더트랙이란 무엇인가요?",
        "당근맨 앱은 어떻게 사용하나요?"
    ]
    
    # 일반 질문에 대한 답변 생성 (관련 페이지 내용 결합)
    for question in general_questions:
        related_content = []
        for page in valid_pages:
            keywords = question.replace("?", "").replace("무엇인가요", "").replace("어떻게", "").replace("주요", "").split()
            
            for keyword in keywords:
                if len(keyword) > 1 and (keyword in page["title"].lower() or keyword in page["content"].lower()):
                    related_content.append(page["content"])
                    break
        
        if related_content:
            # 관련 내용을 모두 결합
            combined_content = "\n\n".join(related_content)
            dataset.append({
                "instruction": question,
                "output": combined_content
            })
    
    # 중복 제거
    unique_dataset = []
    seen_instructions = set()
    
    for item in dataset:
        instruction = item["instruction"]
        if instruction not in seen_instructions:
            seen_instructions.add(instruction)
            unique_dataset.append(item)
    
    logging.info(f"중복 제거 후 데이터셋 크기: {len(unique_dataset)}개 항목")
    
    # JSONL 파일로 저장
    with open(f"{OUTPUT_DIR}/carrotpilot_finetuning_dataset.jsonl", "w", encoding="utf-8") as f:
        for item in unique_dataset:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    
    # JSON 파일로도 저장
    with open(f"{OUTPUT_DIR}/carrotpilot_finetuning_dataset.json", "w", encoding="utf-8") as f:
        json.dump(unique_dataset, f, ensure_ascii=False, indent=2)
    
    return unique_dataset

def main():
    """메인 함수"""
    start_url = "https://g4iwnl.gitbook.io/carrotpilot/"
    
    logging.info("크롤링 시작")
    driver = setup_driver()
    
    try:
        # 처음에는 메인 페이지에서 시작
        crawl_page(driver, start_url, max_depth=3)
        
        # 미수집 메뉴 확인
        uncrawled_menus = set(TARGET_MENUS) - crawled_menus
        if uncrawled_menus:
            logging.info(f"\n아직 수집되지 않은 메뉴: {len(uncrawled_menus)}개")
            for menu in uncrawled_menus:
                logging.info(f"  - {menu}")
                
            # 각 타겟 메뉴에 대해 직접 URL 추정 시도
            for menu in uncrawled_menus:
                slug = menu.lower().replace(" ", "-").replace("(", "").replace(")", "").replace("&", "and")
                inferred_url = f"https://g4iwnl.gitbook.io/carrotpilot/{slug}"
                logging.info(f"\n[시도] {menu} -> {inferred_url}")
                crawl_page(driver, inferred_url, menu, max_depth=2)
        
        logging.info(f"\n크롤링 완료! 총 {len(crawled_data['pages'])}개 페이지를 수집했습니다.")
        
        # 파인튜닝 데이터셋 생성
        dataset = create_finetuning_dataset()
        logging.info(f"파인튜닝 데이터셋 생성 완료! 총 {len(dataset)}개의 질문-답변 쌍이 생성되었습니다.")
        
        # 수집된 메뉴 목록 출력
        crawled_menu_names = [page["title"] for page in crawled_data["pages"]]
        logging.info("\n수집된 메뉴:")
        for name in crawled_menu_names:
            logging.info(f"  - {name}")
        
        logging.info(f"\n결과 파일 위치: {os.path.abspath(OUTPUT_DIR)}")
        
    except Exception as e:
        logging.error(f"오류 발생: {str(e)}")
    finally:
        driver.quit()

if __name__ == "__main__":
    main() 