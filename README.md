# Peanut - 디스코드 채팅 수집 봇

Peanut은 디스코드 서버 내의 모든 채널에서 채팅을 수집하고 저장하는 봇입니다.

## 주요 기능

- 서버 내 모든 채널의 채팅 메시지 수집
- 과거부터 현재까지의 모든 메시지 저장
- 날짜, 채팅 내용, 유저 이름 등 모든 정보를 구체적으로 수집
- 이미 수집된 데이터는 중복 수집하지 않는 효율적인 수집 로직
- 30분마다 자동으로 새로운 채팅 수집 (설정 가능)
- 진행 상황을 디버그 콘솔과 로그 파일에 표시
- 모듈화된 구조로 확장 가능
- **특정 서버에서만 작동하도록 제한 가능**
- **수집된 데이터를 기반으로 질문에 답변하는 로컬 LLM 기능 지원**

## 설치 방법

1. 이 저장소를 클론합니다:
```
git clone https://github.com/yourusername/peanut.git
cd peanut
```

2. 필요한 패키지를 설치합니다:
```
pip install -r requirements.txt
```

3. `.env` 파일을 수정하여 디스코드 봇 토큰과 설정을 구성합니다:
```
DISCORD_TOKEN=your_discord_bot_token_here
DATABASE_PATH=db/discord_messages.db
ALLOWED_GUILD_IDS=123456789012345678,987654321098765432
COLLECTION_INTERVAL=1800
LLM_MODEL_PATH=models/gemma3-4b
EMBEDDING_MODEL=all-MiniLM-L6-v2
```

## 실행 방법

다음 명령어로 봇을 실행합니다:

```
python -m peanut
```

## 환경 설정

`.env` 파일에서 다음 설정을 조정할 수 있습니다:

- `DISCORD_TOKEN`: 디스코드 봇 토큰
- `DATABASE_PATH`: 데이터베이스 파일 경로
- `COLLECTION_INTERVAL`: 수집 간격 (초 단위, 기본값: 1800, 30분)
- `MAX_MESSAGES_PER_FETCH`: 한 번에 가져올 최대 메시지 수 (기본값: 1000)
- `LOG_LEVEL`: 로깅 레벨 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- `ALLOWED_GUILD_IDS`: 허용된 서버 ID 목록 (쉼표로 구분). 비워두면 모든 서버에서 작동합니다.
- `LLM_MODEL_PATH`: 로컬 LLM 모델 경로
- `EMBEDDING_MODEL`: 임베딩 모델 이름

## 특정 서버 제한 설정

봇을 특정 서버에서만 작동하도록 제한하려면:

1. 허용할 서버의 ID를 찾습니다 (디스코드 개발자 모드에서 서버 이름 우클릭 > ID 복사)
2. `.env` 파일에 ID 목록을 추가합니다:
   ```
   ALLOWED_GUILD_IDS=123456789012345678,987654321098765432
   ```
3. 쉼표로 여러 서버를 구분하여 추가할 수 있습니다
4. 허용 목록이 비어있으면 모든 서버에서 작동합니다
5. 허용되지 않은 서버에 봇이 초대되어도 서버에서 나가지 않고, 단순히 해당 서버에서는 메시지 수집 기능이 작동하지 않습니다

## LLM 모델 설정

로컬 LLM 모델을 사용하려면:

1. Gemma 3 4B 등의 지원 모델을 `models/gemma3-4b` 디렉토리에 다운로드하여 배치합니다.
   - Hugging Face에서 Gemma 3 4B 모델 다운로드 방법:
     ```
     git lfs install
     git clone https://huggingface.co/google/gemma-3-4b-instruct models/gemma3-4b
     ```
   - 또는 다른 경로에 모델이 있다면 `.env` 파일의 `LLM_MODEL_PATH`를 해당 경로로 설정하세요.

2. 임베딩 모델은 기본적으로 `all-MiniLM-L6-v2`를 사용하지만, 다른 sentence-transformers 호환 모델로 변경할 수 있습니다.

## 봇 명령어

### `/질문` 명령어

수집된 데이터를 기반으로 질문에 답변하는 슬래시 명령어입니다.

사용법:
```
/질문 질문: 당신의 질문
```

- 봇은 수집된 채팅 데이터에서 질문과 관련된 내용을 검색합니다.
- 관련 내용을 찾으면 로컬 LLM 모델을 사용하여 답변을 생성합니다.
- 관련 내용이 없으면 해당 정보를 찾을 수 없다고 응답합니다.

## 디스코드 봇 생성 방법

1. [Discord Developer Portal](https://discord.com/developers/applications)에 접속합니다.
2. "New Application"을 클릭하여 새 애플리케이션을 생성합니다.
3. "Bot" 탭에서 "Add Bot"을 클릭합니다.
4. "Reset Token"을 클릭하여 봇 토큰을 확인하고 복사합니다.
5. "Bot" 탭의 "Privileged Gateway Intents" 섹션에서 다음 권한을 활성화합니다:
   - Message Content Intent
   - Server Members Intent
6. "OAuth2" > "URL Generator"에서 봇 권한을 설정합니다:
   - Scopes: bot, applications.commands
   - Bot Permissions: Read Messages/View Channels, Read Message History, Send Messages, Use Slash Commands
7. 생성된 URL로 봇을 서버에 초대합니다.

## 모듈 구조

- `peanut/`: 메인 패키지
  - `__main__.py`: 애플리케이션 진입점
  - `bot.py`: 봇 클래스 정의
  - `db/`: 데이터베이스 관련 모듈
    - `database.py`: 데이터베이스 모델 및 관리자
  - `utils/`: 유틸리티 모듈
    - `config.py`: 설정 관리
    - `logger.py`: 로깅 설정
    - `collector.py`: 메시지 수집 로직
    - `llm.py`: LLM 모델 관리
  - `cogs/`: 명령어 및 기능 모듈
    - `qa.py`: 질문 응답 기능
  - `models/`: 로컬 모델 저장 디렉토리
    - `gemma3-4b/`: Gemma 3 4B 모델 파일

## 확장 가능성

이 프로젝트는 다음과 같은 기능으로 확장할 수 있습니다:

- 다양한 LLM 모델 지원(Mistral, Llama, OpenAI API 등)
- 여러 서버의 데이터 분석 및 비교 기능
- 웹 인터페이스를 통한 데이터 시각화 및 관리
- 정기적인 요약 및 인사이트 생성
- 사용자 맞춤형 명령어 및 응답 기능

## 라이센스

이 프로젝트는 MIT 라이센스에 따라 배포됩니다. 자세한 내용은 LICENSE 파일을 참조하세요. 