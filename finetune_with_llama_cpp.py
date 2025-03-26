import json
import os
import argparse
import subprocess
import sys
from pathlib import Path

def check_requirements():
    """필요한 패키지가 설치되어 있는지 확인합니다."""
    try:
        import llama_cpp
        print("✅ llama-cpp-python이 설치되어 있습니다.")
    except ImportError:
        print("❌ llama-cpp-python이 설치되어 있지 않습니다.")
        print("설치 명령어: pip install llama-cpp-python")
        return False
    
    return True

def load_dataset(jsonl_path):
    """JSONL 파일에서 데이터셋을 로드합니다."""
    dataset = []
    try:
        with open(jsonl_path, 'r', encoding='utf-8') as f:
            for line in f:
                data = json.loads(line.strip())
                dataset.append(data)
        print(f"✅ 데이터셋 로드 완료: {len(dataset)}개 QA 쌍")
        
        # 샘플 데이터 출력
        if dataset:
            print("\n데이터셋 샘플:")
            print(f"질문: {dataset[0]['prompt'][:100]}...")
            print(f"답변: {dataset[0]['response'][:100]}...")
        
        return dataset
    except Exception as e:
        print(f"❌ 데이터셋 로드 실패: {str(e)}")
        return None

def prepare_finetune_format(dataset, output_path, model_type="llama"):
    """파인튜닝을 위한 포맷으로 데이터셋을 변환합니다."""
    formatted_data = []
    
    if model_type.lower() == "llama":
        # Llama 모델을 위한 포맷
        for item in dataset:
            formatted_data.append({
                "text": f"<s>[INST] {item['prompt']} [/INST] {item['response']}</s>"
            })
    elif model_type.lower() == "mistral":
        # Mistral 모델을 위한 포맷
        for item in dataset:
            formatted_data.append({
                "text": f"<s>[INST] {item['prompt']} [/INST] {item['response']}</s>"
            })
    elif model_type.lower() == "gemma":
        # Gemma 모델을 위한 포맷
        for item in dataset:
            formatted_data.append({
                "text": f"<start_of_turn>user\n{item['prompt']}<end_of_turn>\n<start_of_turn>model\n{item['response']}<end_of_turn>"
            })
    else:
        print(f"❌ 지원하지 않는 모델 타입: {model_type}")
        return False
    
    # 포맷된 데이터 저장
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            for item in formatted_data:
                f.write(json.dumps(item, ensure_ascii=False) + '\n')
        print(f"✅ 포맷 변환 완료. 파일 저장: {output_path}")
        return True
    except Exception as e:
        print(f"❌ 포맷 변환 실패: {str(e)}")
        return False

def run_finetune(model_path, dataset_path, output_dir, epochs=3, ctx_size=2048, model_type="llama"):
    """llama.cpp를 사용하여 파인튜닝을 실행합니다."""
    try:
        # 출력 디렉토리 생성
        os.makedirs(output_dir, exist_ok=True)
        
        # 모델 타입에 따른 파인튜닝 명령어 생성
        if model_type.lower() in ["llama", "mistral", "gemma"]:
            # llama.cpp의 finetune 명령어
            cmd = [
                "llama-finetune",
                "--model", model_path,
                "--lora-out", os.path.join(output_dir, "carrotpilot-lora.bin"),
                "--train-data", dataset_path,
                "--epochs", str(epochs),
                "--ctx-size", str(ctx_size),
                "--threads", str(max(1, os.cpu_count() // 2)),  # CPU 코어의 절반 사용
                "--learning-rate", "5e-5",
                "--lora-r", "8",
                "--adam-beta1", "0.9",
                "--adam-beta2", "0.999",
                "--adam-eps", "1e-8",
                "--batch-size", "8",  # 메모리에 따라 조정
                "--checkpoint-out", os.path.join(output_dir, "checkpoint"),
                "--checkpoint-steps", "50"
            ]
            
            print("🚀 파인튜닝 시작...")
            print(f"명령어: {' '.join(cmd)}")
            
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            
            # 실시간 출력 표시
            for line in process.stdout:
                print(line, end='')
            
            process.wait()
            
            if process.returncode == 0:
                print(f"✅ 파인튜닝 완료! LoRA 모델 저장 위치: {os.path.join(output_dir, 'carrotpilot-lora.bin')}")
                return True
            else:
                print(f"❌ 파인튜닝 실패: 종료 코드 {process.returncode}")
                return False
        else:
            print(f"❌ 지원하지 않는 모델 타입: {model_type}")
            return False
    except Exception as e:
        print(f"❌ 파인튜닝 중 오류 발생: {str(e)}")
        return False

def main():
    parser = argparse.ArgumentParser(description="로컬 LLM에 당근파일럿 데이터로 파인튜닝")
    parser.add_argument("--model", required=True, help="GGUF 파일 경로")
    parser.add_argument("--model-type", default="llama", choices=["llama", "mistral", "gemma"], 
                        help="모델 유형 (llama, mistral, gemma)")
    parser.add_argument("--dataset", default="carrotpilot_data_with_images/carrotpilot_finetuning_dataset.jsonl", 
                        help="JSONL 데이터셋 파일 경로")
    parser.add_argument("--output-dir", default="carrotpilot_finetuned", help="파인튜닝된 모델을 저장할 디렉토리")
    parser.add_argument("--epochs", type=int, default=3, help="에포크 수")
    parser.add_argument("--ctx-size", type=int, default=2048, help="컨텍스트 크기")
    
    args = parser.parse_args()
    
    # 요구사항 체크
    if not check_requirements():
        sys.exit(1)
    
    # 모델 파일 체크
    if not os.path.exists(args.model):
        print(f"❌ 모델 파일을 찾을 수 없습니다: {args.model}")
        sys.exit(1)
    
    # 데이터셋 로드
    dataset = load_dataset(args.dataset)
    if not dataset:
        sys.exit(1)
    
    # 파인튜닝 포맷으로 변환
    formatted_dataset_path = os.path.join(Path(args.output_dir), "formatted_dataset.jsonl")
    if not prepare_finetune_format(dataset, formatted_dataset_path, args.model_type):
        sys.exit(1)
    
    # 파인튜닝 실행
    if not run_finetune(args.model, formatted_dataset_path, args.output_dir, args.epochs, args.ctx_size, args.model_type):
        sys.exit(1)
    
    print("✨ 모든 과정이 성공적으로 완료되었습니다!")
    print(f"🔍 LoRA 모델 위치: {os.path.join(args.output_dir, 'carrotpilot-lora.bin')}")
    print(f"""
파인튜닝된 모델 사용 예시:
llama-cpp-python을 사용하는 경우:
from llama_cpp import Llama
model = Llama(
    model_path="{args.model}",
    lora_path="{os.path.join(args.output_dir, 'carrotpilot-lora.bin')}",
    n_ctx=2048,
    n_gpu_layers=-1  # 가능한 모든 레이어에 GPU 사용
)
output = model.create_completion("당근파일럿에 대해 알려줘", max_tokens=1024)
print(output["choices"][0]["text"])
""")

if __name__ == "__main__":
    main() 