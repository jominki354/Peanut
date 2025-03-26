import asyncio
from peanut.utils.llm import get_llm_manager

async def test():
    # 당근파일럿 서버 ID로 LLM 매니저 생성
    llm = get_llm_manager(guild_id=1233051768569598022)
    
    # 질문에 대한 관련 메시지 검색
    msgs = await llm.find_relevant_messages('당근파일럿 설치')
    
    # 검색 결과 출력
    print(f'찾은 메시지 수: {len(msgs)}')
    
    # 최대 3개 메시지 내용 출력
    for i, msg in enumerate(msgs[:3]):
        print(f'메시지 {i+1}:')
        print(f'  ID: {msg.id}')
        print(f'  채널: {msg.channel_name}')
        print(f'  내용: {msg.content[:100]}...' if len(msg.content) > 100 else msg.content)
        print()

if __name__ == "__main__":
    asyncio.run(test()) 