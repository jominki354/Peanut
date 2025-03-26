from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import time
import json
import os
import re

# 크롤링 결과 저장할 디렉토리
OUTPUT_DIR = "carrotpilot_data"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 방문한 URL 추적
visited_urls = set()

# 크롤링된 데이터
crawled_data = {
    "pages": []
}

# 목표 메뉴 목록 - 찾고자 하는 모든 메뉴 항목 추가
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
    chrome_options.headless = False
    
    driver = webdriver.Chrome(options=chrome_options)
    driver.set_page_load_timeout(30)
    return driver

def extract_page_content(driver, url, title=None):
    """페이지 내용 추출"""
    # 제목이 제공되지 않은 경우 페이지에서 추출
    if not title:
        try:
            title_element = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "h1, h2, .page-title"))
            )
            title = title_element.text.strip()
        except:
            title = driver.title.strip()
    
    # 내용 추출 - 다양한 선택자 시도
    content = ""
    selectors = [
        ".page-content", "article", ".markdown-section", "main", 
        ".content", ".gitbook-content", ".book-body"
    ]
    
    for selector in selectors:
        try:
            content_element = driver.find_element(By.CSS_SELECTOR, selector)
            content = content_element.text.strip()
            if content:
                break
        except:
            continue
    
    # 내용이 여전히 비어있으면 body 전체 내용 가져오기
    if not content:
        try:
            content = driver.find_element(By.TAG_NAME, "body").text.strip()
        except:
            content = "내용을 추출할 수 없습니다."
    
    # 불필요한 공백 제거
    content = re.sub(r'\n{3,}', '\n\n', content)
    
    return {
        "title": title,
        "url": url,
        "content": content
    }

def extract_menu_links(driver):
    """메뉴에서 링크 추출 - 더 많은 선택자 시도"""
    links = []
    
    # 다양한 GitBook 레이아웃 선택자
    selectors = [
        ".group a", "nav a", ".sidebar-content a", ".menu-list a", 
        ".sidebar a", ".menu a", ".navigation a", ".book-summary a",
        "aside a", ".summary a", "ul.summary a", "ul.menu a", 
        "[role='navigation'] a", "ul li a", ".book-menu-content a"
    ]
    
    for selector in selectors:
        try:
            elements = driver.find_elements(By.CSS_SELECTOR, selector)
            for element in elements:
                href = element.get_attribute("href")
                title = element.text.strip()
                
                if (href and not href.startswith("#") and not href.startswith("javascript") 
                    and "carrotpilot" in href and title):
                    links.append({"url": href, "title": title})
        except:
            continue
    
    # 제목 텍스트 기반으로 타겟 메뉴와 일치하는지 확인
    target_links = []
    for link in links:
        for target in TARGET_MENUS:
            if target.lower() in link["title"].lower():
                target_links.append(link)
                crawled_menus.add(target)
                break
    
    # 중복 제거
    unique_links = []
    seen_urls = set()
    for link in target_links:
        if link["url"] not in seen_urls:
            seen_urls.add(link["url"])
            unique_links.append(link)
    
    # 직접적으로 찾지 못한 메뉴 항목도 추가 (URL 유추)
    for target in TARGET_MENUS:
        if target not in crawled_menus:
            # URL 유추 (공백 -> 하이픈, 소문자화)
            slug = target.lower().replace(" ", "-").replace("(", "").replace(")", "")
            inferred_url = f"https://g4iwnl.gitbook.io/carrotpilot/{slug}"
            unique_links.append({"url": inferred_url, "title": target})
    
    return unique_links

def crawl_page(driver, url, title=None):
    """페이지 크롤링"""
    if url in visited_urls:
        return
    
    print(f"크롤링 중: {url} - {title or '제목 없음'}")
    visited_urls.add(url)
    
    try:
        driver.get(url)
        # 페이지 로딩 대기
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        
        # 스크롤 다운하여 모든 콘텐츠 로드
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)  # 로딩 기다리기
        
        # 페이지 내용 추출
        page_data = extract_page_content(driver, url, title)
        crawled_data["pages"].append(page_data)
        
        # 결과 즉시 저장
        with open(f"{OUTPUT_DIR}/carrotpilot_crawled_data.json", "w", encoding="utf-8") as f:
            json.dump(crawled_data, f, ensure_ascii=False, indent=2)
        
        # 진행 상황 출력
        print(f"  - 내용 추출 완료: {page_data['title']} ({len(crawled_data['pages'])}/{len(TARGET_MENUS)})")
        
        # 링크 추출
        links = extract_menu_links(driver)
        print(f"  - 발견된 링크: {len(links)}개")
        
        # 모든 링크 방문
        for link in links:
            if link["url"] not in visited_urls:
                # 서버 부하 방지를 위한 딜레이
                time.sleep(2)
                crawl_page(driver, link["url"], link["title"])
                
    except Exception as e:
        print(f"오류 발생: {url} - {str(e)}")

def create_finetuning_dataset():
    """파인튜닝을 위한 데이터셋 생성"""
    dataset = []
    
    for page in crawled_data["pages"]:
        # 내용이 너무 짧으면 제외
        if not page["content"] or len(page["content"]) < 50:
            continue
            
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
        related_content = ""
        for page in crawled_data["pages"]:
            keywords = question.replace("?", "").replace("무엇인가요", "").replace("어떻게", "").replace("주요", "").split()
            
            for keyword in keywords:
                if len(keyword) > 1 and (keyword in page["title"].lower() or keyword in page["content"].lower()):
                    related_content += f"\n\n{page['content']}"
                    break
        
        if related_content:
            dataset.append({
                "instruction": question,
                "output": related_content.strip()
            })
    
    # JSONL 파일로 저장
    with open(f"{OUTPUT_DIR}/carrotpilot_finetuning_dataset.jsonl", "w", encoding="utf-8") as f:
        for item in dataset:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    
    # JSON 파일로도 저장
    with open(f"{OUTPUT_DIR}/carrotpilot_finetuning_dataset.json", "w", encoding="utf-8") as f:
        json.dump(dataset, f, ensure_ascii=False, indent=2)
    
    return dataset

def main():
    """메인 함수"""
    start_url = "https://g4iwnl.gitbook.io/carrotpilot/"
    driver = setup_driver()
    
    try:
        # 처음에는 메인 페이지에서 시작
        crawl_page(driver, start_url)
        
        # 미수집 메뉴 확인
        uncrawled_menus = set(TARGET_MENUS) - crawled_menus
        if uncrawled_menus:
            print(f"\n아직 수집되지 않은 메뉴: {len(uncrawled_menus)}개")
            for menu in uncrawled_menus:
                print(f"  - {menu}")
                
            # 각 타겟 메뉴에 대해 직접 URL 추정 시도
            for menu in uncrawled_menus:
                slug = menu.lower().replace(" ", "-").replace("(", "").replace(")", "")
                inferred_url = f"https://g4iwnl.gitbook.io/carrotpilot/{slug}"
                print(f"\n[시도] {menu} -> {inferred_url}")
                crawl_page(driver, inferred_url, menu)
        
        print(f"\n크롤링 완료! 총 {len(crawled_data['pages'])}개 페이지를 수집했습니다.")
        
        # 파인튜닝 데이터셋 생성
        dataset = create_finetuning_dataset()
        print(f"파인튜닝 데이터셋 생성 완료! 총 {len(dataset)}개의 질문-답변 쌍이 생성되었습니다.")
        
        # 최종 결과 출력
        crawled_menu_names = [page["title"] for page in crawled_data["pages"]]
        print("\n수집된 메뉴:")
        for name in crawled_menu_names:
            print(f"  - {name}")
        
        print(f"\n결과 파일 위치: {os.path.abspath(OUTPUT_DIR)}")
        
    except Exception as e:
        print(f"오류 발생: {str(e)}")
    finally:
        driver.quit()

if __name__ == "__main__":
    main()