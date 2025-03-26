import json
import os
import random

def show_dataset_samples(file_path, num_samples=5, random_samples=False, start_index=0, show_full_content=False):
    """JSONL 파일에서 지정된 수만큼의 샘플을 출력합니다."""
    if not os.path.exists(file_path):
        print(f"파일을 찾을 수 없습니다: {file_path}")
        return
    
    data = []
    try:
        # JSONL 파일 형식인지 확인
        if file_path.endswith('.jsonl'):
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    data.append(json.loads(line))
        # JSON 파일 형식인지 확인
        elif file_path.endswith('.json'):
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
    except Exception as e:
        print(f"파일 읽기 오류: {e}")
        return
    
    # 샘플 선택
    samples = []
    if random_samples:
        # 랜덤하게 샘플 선택
        if len(data) > num_samples:
            samples = random.sample(data, num_samples)
        else:
            samples = data
    else:
        # 지정된 인덱스부터 순차적으로 샘플 선택
        end_index = min(start_index + num_samples, len(data))
        samples = data[start_index:end_index]
    
    # 샘플 출력
    print(f"\n총 {len(samples)}개 샘플 출력 (전체 {len(data)}개 중):\n")
    for i, sample in enumerate(samples, 1):
        sample_index = data.index(sample) if random_samples else start_index + i - 1
        print(f"=== 샘플 {i} (인덱스: {sample_index}) ===")
        print(f"질문: {sample.get('instruction', '질문 없음')}")
        
        # 답변 출력
        answer = sample.get('output', '답변 없음')
        if show_full_content or len(answer) <= 200:
            print(f"답변: {answer}")
        else:
            print(f"답변: {answer[:200]}...\n(전체 길이: {len(answer)}자)")
        print()
    
    return data

def show_dataset_stats(file_path):
    """데이터셋의 통계 정보를 출력합니다."""
    if not os.path.exists(file_path):
        print(f"파일을 찾을 수 없습니다: {file_path}")
        return
    
    data = []
    try:
        # JSONL 파일 형식인지 확인
        if file_path.endswith('.jsonl'):
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    data.append(json.loads(line))
        # JSON 파일 형식인지 확인
        elif file_path.endswith('.json'):
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
    except Exception as e:
        print(f"파일 읽기 오류: {e}")
        return
    
    # 통계 정보 출력
    print(f"\n=== 데이터셋 통계 ===")
    print(f"총 데이터 수: {len(data)}")
    
    # 질문 길이 통계
    q_lengths = [len(item.get('instruction', '')) for item in data]
    avg_q_length = sum(q_lengths) / len(q_lengths) if q_lengths else 0
    print(f"평균 질문 길이: {avg_q_length:.1f}자")
    print(f"최소 질문 길이: {min(q_lengths) if q_lengths else 0}자")
    print(f"최대 질문 길이: {max(q_lengths) if q_lengths else 0}자")
    
    # 답변 길이 통계
    a_lengths = [len(item.get('output', '')) for item in data]
    avg_a_length = sum(a_lengths) / len(a_lengths) if a_lengths else 0
    print(f"평균 답변 길이: {avg_a_length:.1f}자")
    print(f"최소 답변 길이: {min(a_lengths) if a_lengths else 0}자")
    print(f"최대 답변 길이: {max(a_lengths) if a_lengths else 0}자")
    
    # 고유 질문 개수
    unique_questions = len(set([item.get('instruction', '') for item in data]))
    print(f"고유 질문 수: {unique_questions}")
    
    # Page not found 응답 수 계산
    not_found_count = sum(1 for item in data if "Page not found" in item.get('output', ''))
    print(f"'Page not found' 응답 수: {not_found_count} ({not_found_count/len(data)*100:.1f}%)")
    
    return data

def show_full_content_sample(data, index):
    """특정 인덱스의 전체 내용을 출력합니다."""
    if 0 <= index < len(data):
        sample = data[index]
        print(f"\n=== 인덱스 {index}의 전체 내용 ===")
        print(f"질문: {sample.get('instruction', '질문 없음')}")
        print(f"답변: {sample.get('output', '답변 없음')}")
    else:
        print(f"인덱스 {index}는 유효하지 않습니다. (0-{len(data)-1} 범위 내에서 지정)")

def main():
    # 데이터 폴더 경로
    data_dir = "carrotpilot_data"
    
    # 파일 경로들
    jsonl_file = os.path.join(data_dir, "carrotpilot_finetuning_dataset.jsonl")
    json_file = os.path.join(data_dir, "carrotpilot_finetuning_dataset.json")
    
    # JSONL 파일이 있으면 JSONL 파일 사용, 없으면 JSON 파일 사용
    if os.path.exists(jsonl_file):
        target_file = jsonl_file
    elif os.path.exists(json_file):
        target_file = json_file
    else:
        print(f"데이터셋 파일을 찾을 수 없습니다. 경로를 확인하세요: {data_dir}")
        return
    
    # 통계 정보 출력
    data = show_dataset_stats(target_file)
    
    # 정상적인 첫 번째 샘플 전체 내용 출력
    print("\n=== 첫 번째 샘플 전체 내용 ===")
    show_full_content_sample(data, 0)
    
    # "Page not found"가 없는 샘플 찾기
    valid_samples = [i for i, item in enumerate(data) if "Page not found" not in item.get('output', '')]
    if valid_samples:
        print(f"\n총 {len(valid_samples)}개의 유효한 샘플이 있습니다.")
        print(f"유효한 샘플 인덱스: {valid_samples[:10]}{'...' if len(valid_samples) > 10 else ''}")
        
        # 유효한 샘플 중 랜덤하게 5개 선택하여 표시
        if len(valid_samples) > 5:
            selected_samples = random.sample(valid_samples, 5)
        else:
            selected_samples = valid_samples
            
        print("\n=== 유효한 샘플 중 무작위 선택 ===")
        for idx in selected_samples:
            show_full_content_sample(data, idx)
    else:
        print("유효한 샘플이 없습니다.")
    
    print(f"\n모든 데이터는 {target_file} 파일에서 확인할 수 있습니다.")

if __name__ == "__main__":
    random.seed(42)  # 재현성을 위한 시드 설정
    main() 