from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import logging
import json
import time
from ctransformers import AutoModelForCausalLM, Config

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("llm-api-server")

# 모델 경로 설정
MODEL_PATH = "models/gemma3-4b/gemma-3-4b-it-Q4_K_M.gguf"

# 앱 인스턴스 생성
app = FastAPI(title="Local LLM API Server")

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 모델 초기화 함수
def initialize_model():
    logger.info(f"모델을 초기화합니다: {MODEL_PATH}")
    
    config = Config(
        gpu_layers=0,  # CPU 기반 (필요에 따라 조정)
        context_length=4096,  # 컨텍스트 길이
    )
    
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_PATH,
        config=config
    )
    
    logger.info("모델 초기화 완료")
    return model

# 모델 초기화
model = initialize_model()

# API 요청 모델 정의
class Message(BaseModel):
    role: str
    content: str

class ChatCompletionRequest(BaseModel):
    messages: List[Message]
    model: Optional[str] = "gemma-3-4b-it"
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = 500
    top_p: Optional[float] = 0.9
    frequency_penalty: Optional[float] = 0.0
    presence_penalty: Optional[float] = 0.0

# API 응답 모델 정의
class ChatCompletionResponse(BaseModel):
    id: str
    object: str
    created: int
    model: str
    choices: List[Dict[str, Any]]
    usage: Dict[str, int]

# 채팅 완료 엔드포인트
@app.post("/v1/chat/completions", response_model=ChatCompletionResponse)
async def create_chat_completion(request: ChatCompletionRequest):
    try:
        logger.info(f"API 요청 수신: {len(request.messages)} 메시지")
        
        # 요청 메시지를 프롬프트로 변환
        prompt = ""
        for msg in request.messages:
            if msg.role == "system":
                prompt += f"<|system|>\n{msg.content}\n"
            elif msg.role == "user":
                prompt += f"<|user|>\n{msg.content}\n"
            elif msg.role == "assistant":
                prompt += f"<|assistant|>\n{msg.content}\n"
        
        # 마지막 assistant 메시지 추가
        prompt += "<|assistant|>\n"
        
        logger.info(f"생성 시작: 온도={request.temperature}, 최대 토큰={request.max_tokens}")
        
        # 시작 시간 측정
        start_time = time.time()
        
        # 텍스트 생성
        generated_text = model(
            prompt,
            max_new_tokens=request.max_tokens,
            temperature=request.temperature,
            top_p=request.top_p,
            repetition_penalty=1.0 + request.frequency_penalty,
        )
        
        # 소요 시간 계산
        elapsed_time = time.time() - start_time
        
        logger.info(f"생성 완료: {len(generated_text)} 자, 소요 시간: {elapsed_time:.2f}초")
        
        # 응답 생성
        response = {
            "id": f"chatcmpl-{int(time.time())}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": request.model,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": generated_text
                    },
                    "finish_reason": "stop"
                }
            ],
            "usage": {
                "prompt_tokens": len(prompt),
                "completion_tokens": len(generated_text),
                "total_tokens": len(prompt) + len(generated_text)
            }
        }
        
        return response
        
    except Exception as e:
        logger.error(f"오류 발생: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"내부 서버 오류: {str(e)}")

# 건강 체크 엔드포인트
@app.get("/health")
async def health_check():
    return {"status": "ok", "model": MODEL_PATH}

# 메인 함수
if __name__ == "__main__":
    import uvicorn
    logger.info("LLM API 서버 시작 중...")
    uvicorn.run(app, host="0.0.0.0", port=8000) 