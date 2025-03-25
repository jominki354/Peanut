# LMStudio를 이용한 Peanut 봇 연동 가이드

## 1. LMStudio 설치하기

1. [LMStudio 공식 웹사이트](https://lmstudio.ai/)에서 LMStudio를 다운로드하여 설치합니다.

## 2. LMStudio에서 모델 로드하기

1. LMStudio를 실행합니다.
2. "Browse" 탭에서 "Hugging Face"를 선택합니다.
3. 검색창에 "gemma" 또는 "gemma-3-4b-it"를 입력하여 Gemma 모델을 검색합니다.
4. "Google/gemma-3-4b-it" 또는 사용하고자 하는 Gemma 모델을 선택하여 다운로드합니다.
5. 다운로드가 완료되면 모델을 선택한 후 "Use in Chat" 버튼을 클릭합니다.

## 3. Local Inference Server 실행하기

1. 좌측 메뉴에서 "Local Inference Server" 탭을 선택합니다.
2. 다음 설정을 확인합니다:
   - Server: OpenAI Compatible Server
   - Host: localhost
   - Port: 1234 (기본값)
   - Model: 앞서 선택한 모델 (Gemma-3-4b-it 권장)
3. "Start server" 버튼을 클릭하여 서버를 시작합니다.
4. 서버가 성공적으로 시작되면 "Server is running" 메시지가 표시됩니다.

## 4. Peanut 봇 실행하기

1. Peanut 봇의 `.env` 파일을 열고 `LLM_API_URL` 값이 다음과 같이 설정되어 있는지 확인합니다:
   ```
   LLM_API_URL=http://localhost:1234/v1/chat/completions
   ```
2. 다음 명령어로 봇을 시작합니다:
   ```
   python -m peanut
   ```
3. 봇이 성공적으로 시작되면 LMStudio API에 연결되어 질문에 응답할 수 있게 됩니다.

## 5. 테스트하기

1. 디스코드 서버에서 `/질문` 명령어를 사용하여 봇에게 질문합니다.
2. 봇은 LMStudio를 통해 실행 중인 Gemma 모델을 사용하여 응답을 생성합니다.
3. LMStudio의 "Local Inference Server" 탭에서 API 호출 로그를 확인할 수 있습니다.

## 주의사항

- LMStudio가 실행 중이고 서버가 활성화된 상태에서만 봇이 정상적으로 작동합니다.
- 모델의 성능은 컴퓨터의 사양에 따라 달라질 수 있습니다.
- GPU 가속을 사용하면 응답 속도가 빨라집니다 (LMStudio의 설정에서 구성 가능).
- 다른 모델을 사용할 경우, 응답 품질과 형식이 달라질 수 있습니다. 