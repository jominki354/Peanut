import json
import os
import re
import random
from pathlib import Path

def load_dataset(filepath):
    """데이터셋 파일 로드"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            # JSON 또는 JSONL 형식 확인
            if filepath.endswith('.jsonl'):
                # JSONL 형식: 한 줄에 하나의 JSON 객체
                dataset = [json.loads(line) for line in f]
            else:
                # JSON 형식: 배열
                dataset = json.load(f)
        return dataset
    except Exception as e:
        print(f"파일 로드 중 오류 발생: {e}")
        return None

def print_dataset_stats(dataset):
    """데이터셋 통계 출력"""
    if not dataset:
        print("데이터셋이 비어 있습니다.")
        return

    total_count = len(dataset)
    
    # 질문 길이 통계
    q_lengths = [len(item["prompt"]) for item in dataset]
    avg_q_length = sum(q_lengths) / total_count
    min_q_length = min(q_lengths)
    max_q_length = max(q_lengths)
    
    # 답변 길이 통계
    a_lengths = [len(item["response"]) for item in dataset]
    avg_a_length = sum(a_lengths) / total_count
    min_a_length = min(a_lengths)
    max_a_length = max(a_lengths)
    
    # 고유 질문 수
    unique_questions = len(set(item["prompt"] for item in dataset))
    
    # 이미지 포함 답변 수
    img_responses = sum(1 for item in dataset if "관련 이미지:" in item["response"])
    
    # "Page not found" 응답 수
    not_found_responses = sum(1 for item in dataset if "Page not found" in item["response"])
    not_found_percentage = (not_found_responses / total_count) * 100 if total_count > 0 else 0
    
    print(f"=== 데이터셋 통계 ===")
    print(f"총 데이터 수: {total_count}")
    print(f"평균 질문 길이: {avg_q_length:.1f} 문자")
    print(f"최소 질문 길이: {min_q_length} 문자")
    print(f"최대 질문 길이: {max_q_length} 문자")
    print(f"평균 답변 길이: {avg_a_length:.1f} 문자")
    print(f"최소 답변 길이: {min_a_length} 문자")
    print(f"최대 답변 길이: {max_a_length} 문자")
    print(f"고유 질문 수: {unique_questions}")
    print(f"이미지 포함 답변 수: {img_responses} ({img_responses/total_count*100:.1f}%)")
    print(f"'Page not found' 응답 수: {not_found_responses} ({not_found_percentage:.1f}%)")
    print("=" * 20)

def print_samples(dataset, start_idx=0, count=5, random_sample=False):
    """데이터셋 샘플 출력"""
    if not dataset:
        print("데이터셋이 비어 있거나 로드에 실패했습니다.")
        return
        
    total_count = len(dataset)
    print(f"\n=== 데이터셋 샘플 (총 {total_count}개 중) ===")
    
    if random_sample:
        # 무작위 샘플 선택
        indices = random.sample(range(total_count), min(count, total_count))
        samples = [dataset[i] for i in indices]
    else:
        # 시작 인덱스부터 연속 샘플 선택
        start_idx = max(0, min(start_idx, total_count - 1))
        end_idx = min(start_idx + count, total_count)
        samples = dataset[start_idx:end_idx]
        
    for i, item in enumerate(samples, 1):
        question = item["prompt"]
        answer = item["response"]
        
        # 이미지 정보 추출
        images = []
        if "관련 이미지:" in answer:
            img_section = answer.split("관련 이미지:")[1].strip()
            img_lines = img_section.split("\n")
            for line in img_lines:
                if "[이미지" in line and "경로:" in line:
                    images.append(line.strip())
            
            # 원본 답변에서 이미지 부분 제외
            main_answer = answer.split("관련 이미지:")[0].strip()
        else:
            main_answer = answer
            
        print(f"\n----- 샘플 {i} -----")
        print(f"질문: {question}")
        print(f"답변: {main_answer[:300]}" + ("..." if len(main_answer) > 300 else ""))
        
        if images:
            print(f"\n이미지 정보 ({len(images)}개):")
            for img in images[:3]:  # 처음 3개 이미지만 표시
                print(f"  {img}")
            if len(images) > 3:
                print(f"  ... 외 {len(images)-3}개 더 있음")
                
        print("-" * 40)

def print_full_content(dataset, index):
    """특정 인덱스의 전체 내용 출력"""
    if not dataset or index >= len(dataset):
        print(f"인덱스 {index}의 항목을 찾을 수 없습니다.")
        return
        
    item = dataset[index]
    question = item["prompt"]
    answer = item["response"]
    
    print(f"\n=== 인덱스 {index}의 전체 내용 ===")
    print(f"질문: {question}")
    print(f"답변:")
    print(answer)
    print("=" * 50)

def check_image_files(dataset, image_dir):
    """이미지 파일 존재 확인"""
    if not dataset:
        return
        
    image_paths = set()
    missing_images = set()
    
    # 모든 응답에서 이미지 경로 추출
    for item in dataset:
        answer = item["response"]
        if "관련 이미지:" in answer:
            img_section = answer.split("관련 이미지:")[1].strip()
            img_pattern = r"경로:\s*([^\[\]\n]+)"
            img_matches = re.findall(img_pattern, img_section)
            
            for img_path in img_matches:
                img_path = img_path.strip()
                image_paths.add(img_path)
                
                # 파일 존재 확인
                full_path = os.path.join(os.path.dirname(image_dir), img_path)
                if not os.path.exists(full_path):
                    missing_images.add(img_path)
    
    print(f"\n=== 이미지 파일 확인 ===")
    print(f"총 참조된 이미지 수: {len(image_paths)}")
    print(f"누락된 이미지 수: {len(missing_images)}")
    
    if missing_images:
        print("\n누락된 이미지 경로 (최대 5개):")
        for path in list(missing_images)[:5]:
            print(f"  {path}")
        if len(missing_images) > 5:
            print(f"  ... 외 {len(missing_images)-5}개 더 있음")

def main():
    """메인 함수"""
    # 데이터셋과 이미지 디렉토리 경로
    dataset_dir = "carrotpilot_data_with_images"
    json_path = os.path.join(dataset_dir, "carrotpilot_finetuning_dataset.json")
    jsonl_path = os.path.join(dataset_dir, "carrotpilot_finetuning_dataset.jsonl")
    image_dir = os.path.join(dataset_dir, "images")
    
    # 데이터셋 로드 시도
    dataset = None
    if os.path.exists(jsonl_path):
        print(f"JSONL 파일 로드 중: {jsonl_path}")
        dataset = load_dataset(jsonl_path)
    elif os.path.exists(json_path):
        print(f"JSON 파일 로드 중: {json_path}")
        dataset = load_dataset(json_path)
    else:
        print(f"데이터셋 파일을 찾을 수 없습니다: {json_path} 또는 {jsonl_path}")
        return
    
    if not dataset:
        print("데이터셋 로드 실패")
        return
        
    # 통계 출력
    print_dataset_stats(dataset)
    
    # 처음 5개 샘플 출력
    print_samples(dataset, start_idx=0, count=5)
    
    # 중간 5개 샘플 출력
    middle_idx = len(dataset) // 2
    print_samples(dataset, start_idx=middle_idx, count=5)
    
    # 무작위 5개 샘플 출력
    print_samples(dataset, count=5, random_sample=True)
    
    # 이미지가 포함된 답변 찾기
    image_samples = [i for i, item in enumerate(dataset) if "관련 이미지:" in item["response"]]
    if image_samples:
        print("\n=== 이미지가 포함된 샘플 ===")
        img_sample_idx = random.choice(image_samples)
        print_full_content(dataset, img_sample_idx)
    else:
        print("\n이미지가 포함된 샘플을 찾을 수 없습니다.")
    
    # 이미지 파일 확인
    check_image_files(dataset, image_dir)

if __name__ == "__main__":
    main() 