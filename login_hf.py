from huggingface_hub import login

# Hugging Face 로그인 프롬프트 표시
token = input("Hugging Face 토큰을 입력하세요 (https://huggingface.co/settings/tokens에서 생성): ")
login(token=token)
print("Hugging Face에 로그인되었습니다. 이제 제한된 모델에 접근할 수 있습니다.") 