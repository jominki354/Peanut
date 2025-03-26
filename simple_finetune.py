import os
import json
import argparse
import torch
import subprocess
import shutil
from pathlib import Path
from datasets import Dataset
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    TrainingArguments,
    Trainer,
    DataCollatorForLanguageModeling,
    BitsAndBytesConfig
)
from peft import get_peft_model, LoraConfig, prepare_model_for_kbit_training
import pandas as pd

def prepare_formatted_dataset(dataset_path, output_path, model_type="gemma"):
    """파인튜닝용 포맷 데이터셋 준비"""
    print("📚 데이터셋 로드 중...")
    dataset = []
    with open(dataset_path, 'r', encoding='utf-8') as f:
        for line in f:
            data = json.loads(line.strip())
            dataset.append(data)
    
    print(f"✅ 데이터셋 로드 완료: {len(dataset)}개 QA 쌍")
    
    # 데이터셋 포맷팅 (Gemma 3 형식으로)
    print("🔄 데이터셋 포맷팅 중...")
    formatted_data = []
    
    if model_type.lower() == "gemma":
        for item in dataset:
            formatted_data.append({
                "text": f"<start_of_turn>user\n{item['prompt']}<end_of_turn>\n<start_of_turn>model\n{item['response']}<end_of_turn>"
            })
    
    # 포맷된 데이터 저장
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        for item in formatted_data:
            f.write(json.dumps(item, ensure_ascii=False) + '\n')
    
    print(f"✅ 포맷 변환 완료. 파일 저장: {output_path}")
    return len(dataset)

def finetune_with_llama_cpp(model_path, dataset_path, output_dir, epochs=3, ctx_size=1024):
    """llama-cpp-python을 사용하여 파인튜닝을 실행합니다."""
    try:
        # 출력 디렉토리 생성
        os.makedirs(output_dir, exist_ok=True)
        
        # Hugging Face에서 llama.cpp 가져오기
        print("🔄 llama.cpp 클론 중...")
        if not os.path.exists("llama.cpp"):
            subprocess.run(["git", "clone", "https://github.com/ggerganov/llama.cpp"], check=True)
        
        # llama.cpp 빌드
        print("🔄 llama.cpp 빌드 중...")
        os.chdir("llama.cpp")
        subprocess.run(["cmake", "-B", "build"], check=True)
        subprocess.run(["cmake", "--build", "build", "--config", "Release"], check=True)
        
        # 파인튜닝 명령어 생성
        finetune_cmd = [
            os.path.join("build", "bin", "Release", "finetune") if os.name == 'nt' else os.path.join("build", "bin", "finetune"),
            "--model", model_path,
            "--train-data", dataset_path,
            "--checkpoint-out", os.path.join("..", output_dir, "checkpoint"),
            "--checkpoint-steps", "50",
            "--lora-out", os.path.join("..", output_dir, "carrotpilot-lora.bin"),
            "--epochs", str(epochs),
            "--ctx-size", str(ctx_size),
            "--learning-rate", "5e-5",
            "--batch-size", "2",
            "--threads", "8",
            "--lora-r", "8"
        ]
        
        print("🚀 llama.cpp로 파인튜닝 시작...")
        print(f"명령어: {' '.join(finetune_cmd)}")
        
        process = subprocess.Popen(finetune_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        
        # 실시간 출력 표시
        for line in process.stdout:
            print(line, end='')
        
        process.wait()
        
        # 원래 디렉토리로 돌아가기
        os.chdir("..")
        
        if process.returncode == 0:
            print(f"✅ 파인튜닝 완료! LoRA 모델 저장 위치: {os.path.join(output_dir, 'carrotpilot-lora.bin')}")
            return True
        else:
            print(f"❌ 파인튜닝 실패: 종료 코드 {process.returncode}")
            return False
    except Exception as e:
        print(f"❌ 파인튜닝 중 오류 발생: {str(e)}")
        # 원래 디렉토리로 돌아가기
        if os.getcwd().endswith("llama.cpp"):
            os.chdir("..")
        return False

def clone_llama_cpp_if_needed():
    """llama.cpp가 없으면 클론"""
    if not os.path.exists("llama.cpp"):
        print("🔄 llama.cpp 클론 중...")
        try:
            subprocess.run(["git", "clone", "https://github.com/ggerganov/llama.cpp"], check=True)
            return True
        except Exception as e:
            print(f"❌ llama.cpp 클론 실패: {str(e)}")
            return False
    return True

def main():
    # 모델 파일 경로 설정
    model_path = "C:/Users/jomin/.lmstudio/models/lmstudio-community/gemma-3-4b-it-GGUF/gemma-3-4b-it-Q4_K_M.gguf"
    output_dir = "carrotpilot_finetuned_gemma3"
    dataset_path = "carrotpilot_data_with_images/carrotpilot_finetuning_dataset.jsonl"
    
    print(f"🔍 데이터셋: {dataset_path}")
    print(f"🔍 출력 디렉토리: {output_dir}")
    print(f"🔍 모델 경로: {model_path}")
    
    # 출력 디렉토리 생성
    os.makedirs(output_dir, exist_ok=True)
    
    # 포맷된 데이터셋 준비
    formatted_dataset_path = os.path.join(output_dir, "formatted_dataset.jsonl")
    prepare_formatted_dataset(dataset_path, formatted_dataset_path, "gemma")
    
    # llama.cpp 클론
    if not clone_llama_cpp_if_needed():
        print("llama.cpp를 클론할 수 없습니다. 수동으로 설치해주세요.")
        return
    
    # Visual Studio 있는지 확인
    try:
        result = subprocess.run(["cmake", "--version"], capture_output=True, text=True)
        if "cmake version" not in result.stdout:
            print("❌ CMake가 설치되어 있지 않습니다.")
            print("Visual Studio 2019 또는 2022와 'C++를 사용한 데스크톱 개발' 워크로드를 설치해주세요.")
            return
    except:
        print("❌ CMake가 설치되어 있지 않습니다.")
        print("Visual Studio 2019 또는 2022와 'C++를 사용한 데스크톱 개발' 워크로드를 설치해주세요.")
        return
    
    # Hugging Face 모델로 파인튜닝 시도
    print("""
⚠️ GGUF 파일을 직접 파인튜닝하려면 llama.cpp를 빌드해야 합니다.
   이 과정은 Visual Studio 설치가 필요합니다.
   
   대안으로 Hugging Face 모델을 사용하시겠습니까?
   1. llama.cpp 빌드 시도 (Visual Studio 필요)
   2. 대신 Hugging Face의 원본 모델 사용
    """)
    
    choice = input("선택하세요 (1 또는 2): ")
    
    if choice == "1":
        # llama.cpp로 파인튜닝
        result = finetune_with_llama_cpp(
            model_path, 
            formatted_dataset_path, 
            output_dir, 
            epochs=1, 
            ctx_size=1024
        )
        
        if result:
            print(f"""
✨ 파인튜닝이 성공적으로 완료되었습니다!
🔍 LoRA 모델 위치: {os.path.join(output_dir, 'carrotpilot-lora.bin')}

LMStudio에서 사용 방법:
1. 기존 모델 로드: {model_path}
2. LoRA 어댑터 추가: {os.path.join(output_dir, 'carrotpilot-lora.bin')}

또는 Python에서 다음과 같이 사용:
```python
from llama_cpp import Llama

model = Llama(
    model_path="{model_path}",
    lora_path="{os.path.join(output_dir, 'carrotpilot-lora.bin')}",
    n_ctx=1024,
    n_gpu_layers=-1  # 가능한 모든 레이어에 GPU 사용
)

output = model.create_completion("당근파일럿에 대해 알려줘", max_tokens=512)
print(output["choices"][0]["text"])
```
""")
        else:
            print("❌ 파인튜닝에 실패했습니다. 대신 Hugging Face 모델을 사용해보세요.")
    else:
        # Hugging Face 모델 사용
        print("🔄 Hugging Face 모델 사용 준비 중...")
        
        # 데이터셋 HF 포맷으로 변환
        dataset = []
        with open(dataset_path, 'r', encoding='utf-8') as f:
            for line in f:
                data = json.loads(line.strip())
                dataset.append(data)
        
        formatted_data = []
        for item in dataset:
            formatted_data.append({
                "text": f"<start_of_turn>user\n{item['prompt']}<end_of_turn>\n<start_of_turn>model\n{item['response']}<end_of_turn>"
            })
        
        # HF Dataset으로 변환
        df = pd.DataFrame(formatted_data)
        hf_dataset = Dataset.from_pandas(df)
        
        # 토크나이저 로드
        print("🔄 Gemma 3 토크나이저 로드 중...")
        tokenizer = AutoTokenizer.from_pretrained("google/gemma-3-4b-instruct", use_fast=True)
        tokenizer.pad_token = tokenizer.eos_token
        
        # 데이터셋 토큰화
        def tokenize_function(examples):
            return tokenizer(
                examples["text"],
                padding="max_length",
                truncation=True,
                max_length=1024,
                return_tensors="pt"
            )
        
        tokenized_dataset = hf_dataset.map(
            tokenize_function,
            batched=True,
            remove_columns=["text"]
        )
        
        # 학습/검증 분할
        split_dataset = tokenized_dataset.train_test_split(test_size=0.1)
        
        # 4비트 양자화 설정
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_use_double_quant=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.float16
        )
        
        # 모델 로드
        print("🔄 Gemma 3 모델 로드 중...")
        try:
            model = AutoModelForCausalLM.from_pretrained(
                "google/gemma-3-4b-instruct",
                quantization_config=bnb_config,
                device_map="auto",
                trust_remote_code=True
            )
            
            # LoRA 학습을 위한 모델 준비
            model = prepare_model_for_kbit_training(model)
            
            # LoRA 설정 - GTX 1660에 맞게 매개변수 축소
            peft_config = LoraConfig(
                task_type="CAUSAL_LM",
                r=8,
                lora_alpha=16,
                lora_dropout=0.05,
                target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
                bias="none",
            )
            
            # LoRA 어댑터 적용
            model = get_peft_model(model, peft_config)
            model.print_trainable_parameters()
            
            # 학습 인자 설정 - GTX 1660에 맞게 조정
            training_args = TrainingArguments(
                output_dir=output_dir,
                num_train_epochs=1,
                per_device_train_batch_size=2,
                per_device_eval_batch_size=2,
                gradient_accumulation_steps=8,
                evaluation_strategy="steps",
                eval_steps=100,
                save_strategy="steps",
                save_steps=100,
                save_total_limit=2,
                logging_dir=os.path.join(output_dir, "logs"),
                logging_steps=10,
                learning_rate=1e-4,
                weight_decay=0.01,
                fp16=True,
                bf16=False,
                max_grad_norm=0.3,
                warmup_ratio=0.03,
                group_by_length=True,
                lr_scheduler_type="cosine",
                report_to="none",
                optim="paged_adamw_8bit"
            )
            
            # 데이터 콜레이터 정의
            data_collator = DataCollatorForLanguageModeling(
                tokenizer=tokenizer, 
                mlm=False
            )
            
            # 트레이너 초기화
            trainer = Trainer(
                model=model,
                args=training_args,
                train_dataset=split_dataset["train"],
                eval_dataset=split_dataset["test"],
                data_collator=data_collator,
                tokenizer=tokenizer
            )
            
            # 모델 학습
            print("🚀 파인튜닝 시작...")
            trainer.train()
            
            # 모델 저장
            print(f"✅ 파인튜닝 완료! 모델 저장 중...")
            model.save_pretrained(os.path.join(output_dir, "final_model"))
            tokenizer.save_pretrained(os.path.join(output_dir, "final_model"))
            
            print(f"""
✨ 모든 과정이 성공적으로 완료되었습니다!
🔍 파인튜닝된 모델 위치: {os.path.join(output_dir, 'final_model')}

파인튜닝된 모델 사용 예시:
from transformers import AutoModelForCausalLM, AutoTokenizer

# 토크나이저와 모델 로드
tokenizer = AutoTokenizer.from_pretrained("{os.path.join(output_dir, 'final_model')}")
model = AutoModelForCausalLM.from_pretrained("{os.path.join(output_dir, 'final_model')}")

# 추론 수행
prompt = "당근파일럿에 대해 알려줘"
inputs = tokenizer(prompt, return_tensors="pt")
outputs = model.generate(**inputs, max_length=1024)
print(tokenizer.decode(outputs[0], skip_special_tokens=True))
""")
        except Exception as e:
            print(f"❌ 파인튜닝 중 오류 발생: {str(e)}")
            print("메모리 부족 오류면 배치 크기, 에포크 수, 컨텍스트 크기를 더 줄여보세요.")

if __name__ == "__main__":
    main() 