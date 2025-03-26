import os
import json
import torch
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

def main():
    # 설정
    output_dir = "carrotpilot_finetuned_gemma3"
    dataset_path = "carrotpilot_data_with_images/carrotpilot_finetuning_dataset.jsonl"
    model_name = "google/gemma-3-2b-instruct"  # 더 작은 Gemma 3 2B 모델 사용
    
    print(f"🔍 데이터셋: {dataset_path}")
    print(f"🔍 출력 디렉토리: {output_dir}")
    print(f"🔍 모델: {model_name}")
    
    # 출력 디렉토리 생성
    os.makedirs(output_dir, exist_ok=True)
    
    # 데이터셋 로드
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
    for item in dataset:
        formatted_data.append({
            "text": f"<start_of_turn>user\n{item['prompt']}<end_of_turn>\n<start_of_turn>model\n{item['response']}<end_of_turn>"
        })
    
    # HF Dataset으로 변환
    print("🔄 HF Dataset 변환 중...")
    df = pd.DataFrame(formatted_data)
    hf_dataset = Dataset.from_pandas(df)
    print(f"✅ HF Dataset 변환 완료: {len(hf_dataset)}개 항목")
    
    # 토크나이저 로드
    print(f"🔄 토크나이저 로드 중: {model_name}")
    tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    
    # 데이터셋 토큰화
    print("🔄 데이터셋 토큰화 중...")
    def tokenize_function(examples):
        return tokenizer(
            examples["text"],
            padding="max_length",
            truncation=True,
            max_length=256,  # 컨텍스트 크기 더 축소 (메모리 절약)
            return_tensors="pt"
        )
    
    tokenized_dataset = hf_dataset.map(
        tokenize_function,
        batched=True,
        remove_columns=["text"]
    )
    print(f"✅ 데이터셋 토큰화 완료")
    
    # 학습/검증 분할
    split_dataset = tokenized_dataset.train_test_split(test_size=0.1)
    
    # 4비트 양자화 설정
    print("🔄 4비트 양자화 설정 중...")
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_use_double_quant=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.float16
    )
    
    # 모델 로드
    print(f"🔄 모델 로드 중: {model_name}")
    try:
        model = AutoModelForCausalLM.from_pretrained(
            model_name,
            quantization_config=bnb_config,
            device_map="auto",
            trust_remote_code=True
        )
        
        # LoRA 학습을 위한 모델 준비
        print("🔄 LoRA 학습을 위한 모델 준비 중...")
        model = prepare_model_for_kbit_training(model)
        
        # LoRA 설정 - GTX 1660에 맞게 매개변수 축소
        peft_config = LoraConfig(
            task_type="CAUSAL_LM",
            r=2,  # 순위 더 감소 (매우 작게)
            lora_alpha=8,
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
            num_train_epochs=1,  # 에포크 수 감소
            per_device_train_batch_size=2,  # 작은 모델이라 배치 크기 2
            per_device_eval_batch_size=2,
            gradient_accumulation_steps=8,  # 그래디언트 누적 단계
            evaluation_strategy="steps",
            eval_steps=20,
            save_strategy="steps",
            save_steps=20,
            save_total_limit=2,
            logging_dir=os.path.join(output_dir, "logs"),
            logging_steps=10,
            learning_rate=5e-5,
            weight_decay=0.01,
            fp16=True,
            bf16=False,
            max_grad_norm=0.3,
            warmup_ratio=0.03,
            group_by_length=True,
            lr_scheduler_type="cosine",
            report_to="none",
            optim="paged_adamw_8bit",  # 메모리 절약을 위한 8비트 옵티마이저
            gradient_checkpointing=True  # 메모리 절약을 위한 그래디언트 체크포인팅
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
```python
from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline

# 토크나이저와 모델 로드
tokenizer = AutoTokenizer.from_pretrained("{os.path.join(output_dir, 'final_model')}")
model = AutoModelForCausalLM.from_pretrained("{os.path.join(output_dir, 'final_model')}")

# 텍스트 생성 파이프라인 생성
pipe = pipeline("text-generation", model=model, tokenizer=tokenizer, device=0)  # device=0은 첫 번째 GPU 사용

# 추론 수행
prompt = "당근파일럿에 대해 알려줘"
result = pipe(prompt, max_length=512, do_sample=True, temperature=0.7)
print(result[0]['generated_text'])
```

LMStudio에서 사용:
1. LMStudio의 '모델 가져오기' 기능 사용
2. '{os.path.join(output_dir, 'final_model')}' 경로를 지정

✅ 모델을 LMStudio에서 사용하려면 Hugging Face 모델 형식을 GGUF로 변환해야 할 수도 있습니다.
""")
    except Exception as e:
        print(f"❌ 파인튜닝 중 오류 발생: {str(e)}")
        print("메모리 부족 오류면 다음과 같이 설정을 더 조정해보세요:")
        print("1. 배치 크기를 1로 줄이기")
        print("2. 그래디언트 누적 단계를 늘리기")
        print("3. 컨텍스트 크기를 더 줄이기 (128)")
        print("4. LoRA 랭크(r)를 1로 설정")
        print("5. 더 작은 모델 사용 (예: Phi-1.5)")

if __name__ == "__main__":
    main() 