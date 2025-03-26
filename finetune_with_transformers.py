import os
import json
import argparse
from pathlib import Path
import numpy as np
import torch
from datasets import Dataset
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    TrainingArguments,
    Trainer,
    DataCollatorForLanguageModeling
)
from peft import get_peft_model, LoraConfig, prepare_model_for_kbit_training

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

def format_dataset(dataset, model_type="llama"):
    """파인튜닝을 위한 포맷으로 데이터셋을 변환합니다."""
    formatted_data = []
    
    if model_type.lower() in ["llama", "mistral"]:
        # Llama/Mistral 모델을 위한 포맷
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
        return None
    
    # HF Dataset으로 변환
    try:
        hf_dataset = Dataset.from_pandas(pd.DataFrame(formatted_data))
        print(f"✅ HF Dataset 변환 완료: {len(hf_dataset)}개 항목")
        return hf_dataset
    except Exception as e:
        print(f"❌ HF Dataset 변환 실패: {str(e)}")
        return None

def tokenize_data(dataset, tokenizer, max_length=2048):
    """데이터셋을 토큰화합니다."""
    def tokenize_function(examples):
        return tokenizer(
            examples["text"],
            padding="max_length",
            truncation=True,
            max_length=max_length,
            return_tensors="pt"
        )
    
    try:
        tokenized_dataset = dataset.map(
            tokenize_function,
            batched=True,
            remove_columns=["text"]
        )
        print(f"✅ 데이터셋 토큰화 완료")
        return tokenized_dataset
    except Exception as e:
        print(f"❌ 데이터셋 토큰화 실패: {str(e)}")
        return None

def train_model(model_name, dataset_path, output_dir, epochs=3, batch_size=8, model_type="llama", quantize=False):
    """Transformers를 사용하여 파인튜닝을 실행합니다."""
    try:
        # 출력 디렉토리 생성
        os.makedirs(output_dir, exist_ok=True)
        
        # 데이터셋 로드
        qa_dataset = load_dataset(dataset_path)
        if not qa_dataset:
            return False
        
        # 데이터셋 포맷팅
        formatted_dataset = format_dataset(qa_dataset, model_type)
        if formatted_dataset is None:
            return False
        
        # 토크나이저 로드
        print(f"🔄 토크나이저 로드 중: {model_name}")
        tokenizer = AutoTokenizer.from_pretrained(model_name, use_fast=True)
        
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token
        
        # 데이터셋 토큰화
        tokenized_dataset = tokenize_data(formatted_dataset, tokenizer)
        if tokenized_dataset is None:
            return False
        
        # 학습/검증 분할
        split_dataset = tokenized_dataset.train_test_split(test_size=0.1)
        
        # 모델 로드
        print(f"🔄 모델 로드 중: {model_name}")
        
        # 양자화 여부에 따라 모델 로드 방식 다르게 설정
        if quantize:
            from transformers import BitsAndBytesConfig
            
            # BitsAndBytes 설정
            bnb_config = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_use_double_quant=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_compute_dtype=torch.float16
            )
            
            # 양자화된 모델 로드
            model = AutoModelForCausalLM.from_pretrained(
                model_name,
                quantization_config=bnb_config,
                device_map="auto"
            )
            
            # 양자화된 모델을 LoRA 학습을 위해 준비
            model = prepare_model_for_kbit_training(model)
        else:
            # 일반 모델 로드
            model = AutoModelForCausalLM.from_pretrained(
                model_name,
                torch_dtype=torch.float16,
                device_map="auto"
            )
        
        # LoRA 설정
        peft_config = LoraConfig(
            task_type="CAUSAL_LM",
            r=16,
            lora_alpha=32,
            lora_dropout=0.05,
            target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
            bias="none",
        )
        
        # LoRA 어댑터 적용
        model = get_peft_model(model, peft_config)
        model.print_trainable_parameters()
        
        # 학습 인자 설정
        training_args = TrainingArguments(
            output_dir=output_dir,
            num_train_epochs=epochs,
            per_device_train_batch_size=batch_size,
            per_device_eval_batch_size=batch_size,
            gradient_accumulation_steps=4,
            evaluation_strategy="steps",
            eval_steps=50,
            save_strategy="steps",
            save_steps=50,
            save_total_limit=3,
            logging_dir=os.path.join(output_dir, "logs"),
            logging_steps=10,
            learning_rate=2e-4,
            weight_decay=0.01,
            fp16=True,
            bf16=False,
            max_grad_norm=0.3,
            warmup_ratio=0.03,
            group_by_length=True,
            lr_scheduler_type="cosine",
            report_to="none"
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
        
        print(f"✅ 모델 저장 완료: {os.path.join(output_dir, 'final_model')}")
        return True
        
    except Exception as e:
        print(f"❌ 파인튜닝 중 오류 발생: {str(e)}")
        return False

def main():
    parser = argparse.ArgumentParser(description="Transformers를 사용한 당근파일럿 데이터 파인튜닝")
    parser.add_argument("--model", required=True, help="Hugging Face 모델 이름 또는 경로")
    parser.add_argument("--model-type", default="llama", choices=["llama", "mistral", "gemma"], 
                        help="모델 유형 (llama, mistral, gemma)")
    parser.add_argument("--dataset", default="carrotpilot_data_with_images/carrotpilot_finetuning_dataset.jsonl", 
                        help="JSONL 데이터셋 파일 경로")
    parser.add_argument("--output-dir", default="carrotpilot_finetuned_hf", help="파인튜닝된 모델을 저장할 디렉토리")
    parser.add_argument("--epochs", type=int, default=3, help="에포크 수")
    parser.add_argument("--batch-size", type=int, default=8, help="배치 크기")
    parser.add_argument("--quantize", action="store_true", help="4비트 양자화 사용 여부")
    
    args = parser.parse_args()
    
    # 필요한 패키지 import 체크
    try:
        import transformers
        import datasets
        import peft
        import pandas as pd
        print("✅ 필요한 패키지가 모두 설치되어 있습니다.")
    except ImportError as e:
        print(f"❌ 필요한 패키지가 설치되어 있지 않습니다: {e}")
        print("설치 명령어: pip install transformers datasets peft pandas")
        return
    
    if args.quantize:
        try:
            import bitsandbytes
            print("✅ bitsandbytes가 설치되어 있습니다.")
        except ImportError:
            print("❌ 양자화를 위한 bitsandbytes가 설치되어 있지 않습니다.")
            print("설치 명령어: pip install bitsandbytes")
            print("계속 진행하려면 --quantize 옵션을 제거하거나 bitsandbytes를 설치하세요.")
            return
    
    # GPU 확인
    if torch.cuda.is_available():
        print(f"✅ GPU 사용 가능: {torch.cuda.get_device_name(0)}")
    else:
        print("⚠️ GPU를 찾을 수 없습니다. CPU로 학습을 진행합니다. 이는 매우 느릴 수 있습니다.")
    
    # 데이터셋 확인
    if not os.path.exists(args.dataset):
        print(f"❌ 데이터셋 파일을 찾을 수 없습니다: {args.dataset}")
        return
    
    # 파인튜닝 실행
    success = train_model(
        args.model, 
        args.dataset, 
        args.output_dir, 
        args.epochs, 
        args.batch_size, 
        args.model_type,
        args.quantize
    )
    
    if success:
        print("✨ 모든 과정이 성공적으로 완료되었습니다!")
        print(f"🔍 파인튜닝된 모델 위치: {os.path.join(args.output_dir, 'final_model')}")
        print(f"""
파인튜닝된 모델 사용 예시:
from transformers import AutoModelForCausalLM, AutoTokenizer

# 토크나이저와 모델 로드
tokenizer = AutoTokenizer.from_pretrained("{os.path.join(args.output_dir, 'final_model')}")
model = AutoModelForCausalLM.from_pretrained("{os.path.join(args.output_dir, 'final_model')}")

# 추론 수행
prompt = "당근파일럿에 대해 알려줘"
inputs = tokenizer(prompt, return_tensors="pt")
outputs = model.generate(**inputs, max_length=1024)
print(tokenizer.decode(outputs[0], skip_special_tokens=True))
""")
    else:
        print("❌ 파인튜닝 과정 중 오류가 발생했습니다.")

if __name__ == "__main__":
    main() 