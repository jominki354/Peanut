import os
import logging
import aiohttp
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta, timezone
import re
import time
import requests

# sentence_transformers 관련 임포트 제거
# from sentence_transformers import SentenceTransformer, util

from ..db.database import get_db_manager, DiscordMessage
from sqlalchemy import select, func, or_, and_
from sqlalchemy.sql import text

# 로깅 설정
logger = logging.getLogger('discord.llm')

class LLMManager:
    """외부 LLM API를 사용하는 클래스"""
    
    def __init__(self, api_url=None, guild_id=None):
        """LLM 매니저 초기화
        
        Args:
            api_url: LLM API URL, 없으면 환경 변수에서 가져옴
            guild_id: 서버 ID, 지정하면 서버별 데이터베이스를 사용함
        """
        from ..utils.config import get_config
        
        # 설정 로드
        self.config = get_config()
        
        # API URL 설정
        self.api_url = api_url or self.config.get('LLM_API_URL', 'http://localhost:1234/v1/chat/completions')
        
        # 모델 API 정보 추출
        self.model_name = self.extract_model_name()
        
        # 초기화 상태
        self.is_initialized = False
        
        # 서버 ID 설정
        self.guild_id = guild_id
        
        # 데이터베이스 매니저
        self.db_manager = get_db_manager(guild_id=self.guild_id)
        
        # 봇의 사용자 ID (메시지 필터링용)
        self.bot_id = self.config.get('BOT_ID', None)
        # 봇 ID 목록으로 변환 (쉼표로 구분된 문자열일 경우)
        self.bot_id_list = []
        if self.bot_id:
            self.bot_id_list = [bid.strip() for bid in self.bot_id.split(',') if bid.strip()]
            logger.info(f"메시지 검색에서 제외할 봇 ID 목록: {self.bot_id_list}")
        
        logger.info(f"LLM 매니저가 초기화되었습니다. API URL: {self.api_url}")
        if self.model_name:
            logger.info(f"추정 모델: {self.model_name}")
    
    def extract_model_name(self):
        """API URL에서 모델 이름 추출 시도"""
        try:
            # URL에 모델 정보가 있는지 확인
            if 'localhost' in self.api_url or '127.0.0.1' in self.api_url:
                return "LMStudio API (로컬)"
            elif 'openai' in self.api_url:
                return "OpenAI API"
            else:
                return "외부 LLM API"
        except:
            return "알 수 없는 LLM API"
    
    async def initialize_models(self):
        """API 연결 초기화"""
        if self.is_initialized:
            return
            
        try:
            logger.info("LLM API 연결을 초기화하고 있습니다...")
            
            # API 연결 테스트
            async with aiohttp.ClientSession() as session:
                try:
                    # 간단한 요청으로 API 테스트
                    test_data = {
                        "messages": [
                            {"role": "user", "content": "안녕하세요"}
                        ],
                        "temperature": 0.3,
                        "max_tokens": 10
                    }
                    
                    async with session.post(self.api_url, json=test_data) as response:
                        if response.status != 200:
                            error_text = await response.text()
                            logger.warning(f"API 연결 테스트 실패: 상태 코드 {response.status}, 응답: {error_text}")
                        else:
                            response_json = await response.json()
                            # 모델 정보 추출 시도
                            if 'model' in response_json:
                                self.model_name = response_json['model']
                                logger.info(f"API 연결 테스트 성공! 사용 모델: {self.model_name}")
                            else:
                                logger.info("API 연결 테스트 성공!")
                except Exception as e:
                    logger.warning(f"API 연결 테스트 중 오류: {str(e)}")
            
            # 초기화 완료
            self.is_initialized = True
            logger.info("LLM 매니저 초기화가 완료되었습니다.")
        
        except Exception as e:
            logger.error(f"API 초기화 중 오류 발생: {str(e)}", exc_info=True)
            raise
    
    def extract_keywords(self, query: str) -> List[str]:
        """질문에서 중요 키워드 추출
        
        Args:
            query: 사용자 질문
            
        Returns:
            추출된 키워드 목록
        """
        # 불용어 정의 (한국어 일반 조사, 대명사, 의문사만 포함)
        stopwords = {
            '이', '그', '저', '것', '수', '를', '에', '의', '가', '이다', '은', '는', '이런', '저런',
            '어떤', '무슨', '어떻게', '어디', '언제', '뭐', '왜', '누가', '누구', '어느', '했', '했나요',
            '했어요', '인가요', '인지', '인데', '있나요', '있어요', '일까요', '할까요', '합니까', '입니까',
            '계신가요', '인가요', '있을까요', '알려주세요', '알려줘', '알려줘요', '해주세요', '해줘', '해줘요'
        }
        
        # 원래 쿼리를 보존 (대소문자 구분, 숫자 포함)
        original_words = re.findall(r'[a-zA-Z0-9가-힣]+', query)
        
        # 복합어 및 특수 용어 검사 (연속된 단어 조합)
        compound_terms = []
        words_in_order = re.findall(r'[a-zA-Z0-9가-힣]+', query)
        
        # 2~3단어 복합어 추출
        for i in range(len(words_in_order)-1):
            # 2단어 복합어
            compound = words_in_order[i] + words_in_order[i+1]
            compound_terms.append(compound)
            
            # 3단어 복합어 (있을 경우)
            if i < len(words_in_order)-2:
                compound = words_in_order[i] + words_in_order[i+1] + words_in_order[i+2]
                compound_terms.append(compound)
        
        # 한글, 영문, 숫자만 추출 (특수문자 제거)
        cleaned_query = re.sub(r'[^\w\s가-힣]', ' ', query.lower())
        
        # 단어 분리 및 불용어 제거
        words = cleaned_query.split()
        keywords = [word for word in words if word not in stopwords and len(word) > 1]
        
        # 전문 용어와 중요 단어 추가 (대소문자 구분)
        for word in original_words:
            # 영문 약어나 모델명은 그대로 유지하여 추가
            if re.match(r'^[A-Z0-9]+$', word) or re.search(r'[A-Z][a-z0-9]*', word) or re.match(r'.*[0-9].*', word):
                if word.lower() not in [k.lower() for k in keywords]:
                    keywords.append(word)
        
        # 복합어 추가
        for term in compound_terms:
            if len(term) > 3 and term.lower() not in [k.lower() for k in keywords]:
                keywords.append(term)
        
        # 중복 제거 및 중요도 순으로 정렬 (단어 길이 기준)
        keywords = sorted(set(keywords), key=len, reverse=True)
        
        logger.debug(f"추출된 키워드: {keywords}")
        return keywords[:20]  # 상위 20개 키워드 사용 (더 많은 키워드 활용)
    
    def analyze_query_intent(self, query: str) -> Dict[str, Any]:
        """질문의 의도 분석
        
        Args:
            query: 사용자 질문
            
        Returns:
            분석된 의도 정보
        """
        intent = {
            'is_question': False,  # 질문인지 여부
            'question_type': None,  # 질문 유형 (what, how, why 등)
            'time_related': False,  # 시간 관련 여부
            'person_related': False,  # 사람 관련 여부
            'topic': None  # 주요 주제
        }
        
        # 질문인지 판단
        question_markers = ['어떻게', '무엇', '언제', '어디', '누구', '왜', '?', '까요', '인가요', '인지']
        for marker in question_markers:
            if marker in query:
                intent['is_question'] = True
                break
        
        # 질문 유형 분석
        if '어떻게' in query or '방법' in query:
            intent['question_type'] = 'how'
        elif '언제' in query or '날짜' in query or '시간' in query or '기간' in query:
            intent['question_type'] = 'when'
            intent['time_related'] = True
        elif '누구' in query or '이름' in query or '사람' in query:
            intent['question_type'] = 'who'
            intent['person_related'] = True
        elif '왜' in query or '이유' in query:
            intent['question_type'] = 'why'
        elif '어디' in query or '장소' in query or '위치' in query:
            intent['question_type'] = 'where'
        
        # 키워드에서 주제 추정
        keywords = self.extract_keywords(query)
        if keywords:
            intent['topic'] = keywords[0]  # 가장 중요한 키워드를 주제로 설정
        
        logger.debug(f"질문 의도 분석: {intent}")
        return intent
        
    async def find_relevant_messages(self, query: str, limit: int = 30) -> List[DiscordMessage]:
        """질문과 관련된 메시지 검색
        
        Args:
            query: 사용자 질문
            limit: 검색할 최대 메시지 수
            
        Returns:
            관련 메시지 목록
        """
        try:
            # 짧은 쿼리를 위한 직접 검색 처리 (3단어 이하)
            words = query.strip().split()
            if len(words) <= 3:
                # 짧은 쿼리는 직접 정확한 키워드로 검색
                direct_query = query.strip().lower()
                logger.info(f"짧은 쿼리 감지: '{direct_query}' - 직접 검색 시도")
                
                async with self.db_manager.AsyncSessionLocal() as session:
                    # 기본 쿼리 조건
                    conditions = [
                        DiscordMessage.content.isnot(None),
                        DiscordMessage.content != ""
                    ]
                    
                    # 봇 ID 필터링
                    if self.bot_id_list:
                        # 여러 봇 ID 처리
                        bot_conditions = []
                        for bot_id in self.bot_id_list:
                            bot_conditions.append(DiscordMessage.author_id != bot_id)
                        
                        if bot_conditions:
                            # 모든 봇 ID를 제외하는 조건 (AND 연산)
                            for condition in bot_conditions:
                                conditions.append(condition)
                    
                    # 직접 검색 - 정확한 매치
                    direct_conditions = []
                    
                    # 1. 제목/첫줄 검색 (가장 우선순위 높음)
                    direct_conditions.append(
                        DiscordMessage.content.ilike(f"# {direct_query}%")  # 마크다운 제목 형식 검색
                    )
                    direct_conditions.append(
                        DiscordMessage.content.ilike(f"## {direct_query}%")  # 마크다운 부제목 형식 검색
                    )
                    direct_conditions.append(
                        DiscordMessage.content.ilike(f"{direct_query}:%")  # 키-값 형식 검색
                    )
                    
                    # 2. 전체 내용 검색
                    for word in words:
                        if len(word) >= 2:  # 2글자 이상 단어만 검색
                            direct_conditions.append(
                                DiscordMessage.content.ilike(f"%{word}%")
                            )
                    
                    # 직접 검색 실행
                    stmt = select(DiscordMessage).where(
                        and_(*conditions, or_(*direct_conditions))
                    ).order_by(DiscordMessage.created_at.desc()).limit(limit)
                    
                    result = await session.execute(stmt)
                    direct_matches = result.scalars().all()
                    
                    if direct_matches:
                        logger.info(f"직접 검색으로 {len(direct_matches)}개의 관련 메시지를 찾았습니다.")
                        return direct_matches

            # 표준 검색 과정 (키워드 기반)
            # 키워드 추출
            keywords = self.extract_keywords(query)
            
            # 의도 분석
            intent = self.analyze_query_intent(query)
            
            if not keywords:
                logger.warning("키워드를 추출할 수 없습니다. 최근 메시지를 반환합니다.")
                return await self.get_recent_messages(limit)
            
            logger.info(f"검색 키워드: {', '.join(keywords)}")
            
            async with self.db_manager.AsyncSessionLocal() as session:
                # 기본 쿼리 조건: 내용이 비어있지 않고 봇 메시지 제외
                conditions = [
                    DiscordMessage.content.isnot(None),
                    DiscordMessage.content != ""
                ]
                
                # 봇 ID 필터링
                if self.bot_id_list:
                    # 여러 봇 ID 처리
                    bot_conditions = []
                    for bot_id in self.bot_id_list:
                        bot_conditions.append(DiscordMessage.author_id != bot_id)
                    
                    if bot_conditions:
                        # 모든 봇 ID를 제외하는 조건 (AND 연산)
                        for condition in bot_conditions:
                            conditions.append(condition)
                
                # 1단계: 정확한 키워드 기반 검색 (첫 3개 키워드)
                primary_keywords = keywords[:3] if len(keywords) >= 3 else keywords
                exact_matches = []
                
                # 정확한 키워드 매치 검색
                for keyword in primary_keywords:
                    # 특수한 경우: 영문/숫자 혼합 키워드는 대소문자 구분하여 검색 (정확도 향상)
                    if re.search(r'[A-Z0-9]', keyword):
                        # 정확한 대소문자 매치
                        stmt = select(DiscordMessage).where(
                            and_(*conditions, DiscordMessage.content.contains(keyword))
                        ).order_by(DiscordMessage.created_at.desc()).limit(limit)
                    else:
                        # 일반 키워드는 대소문자 구분 없이 검색
                        stmt = select(DiscordMessage).where(
                            and_(*conditions, DiscordMessage.content.ilike(f'%{keyword}%'))
                        ).order_by(DiscordMessage.created_at.desc()).limit(limit)
                    
                    # 결과 가져오기
                    result = await session.execute(stmt)
                    matches = result.scalars().all()
                    
                    # 정확도 점수 추가: 제목에 키워드가 있으면 가중치 부여
                    scored_matches = []
                    for msg in matches:
                        score = 1.0  # 기본 점수
                        
                        # 정확한 단어 일치 확인 (단어 경계 기준)
                        try:
                            content_lower = msg.content.lower()
                            keyword_lower = keyword.lower()
                            
                            # 제목이나 첫 줄에 키워드가 있으면 가중치 부여
                            first_line = content_lower.split('\n')[0] if '\n' in content_lower else content_lower
                            if keyword_lower in first_line:
                                score += 0.5
                            
                            # 마크다운 제목이나 키-값 패턴이면 가중치 부여 (정보성 높음)
                            if first_line.startswith('# ') or first_line.startswith('## ') or ':' in first_line:
                                score += 1.0
                            
                            # 완전한 단어 일치인 경우 가중치 부여
                            if re.search(r'\b' + re.escape(keyword_lower) + r'\b', content_lower):
                                score += 1.0
                            
                            # 질문의 첫 번째 키워드와 일치하면 가중치 추가
                            if keywords and keyword_lower == keywords[0].lower():
                                score += 0.5
                        except:
                            pass
                            
                        scored_matches.append((msg, score))
                    
                    # 점수 기준 정렬 후 추가
                    scored_matches.sort(key=lambda x: x[1], reverse=True)
                    exact_matches.extend([msg for msg, _ in scored_matches])
                
                # 중복 제거
                seen_ids = set()
                filtered_exact_matches = []
                for msg in exact_matches:
                    if msg.id not in seen_ids:
                        seen_ids.add(msg.id)
                        filtered_exact_matches.append(msg)
                
                # 정확한 매치가 충분하면 반환
                if len(filtered_exact_matches) >= 1:  # 최소 1개라도 결과가 있으면 반환 (원래는 5)
                    logger.info(f"정확한 키워드 검색으로 {len(filtered_exact_matches)}개의 관련 메시지를 찾았습니다.")
                    return filtered_exact_matches[:limit]  # 지정된 한도까지만 반환
                
                # 2단계: 모든 키워드 OR 조건으로 검색 (기존 방식)
                keyword_conditions = []
                for keyword in keywords:
                    if len(keyword) > 1:  # 2글자 이상인 키워드만 사용
                        keyword_conditions.append(DiscordMessage.content.ilike(f'%{keyword}%'))
                
                # 시간 관련 질문인 경우 최근 메시지를 더 중요하게 고려
                time_limit = limit
                if intent['time_related']:
                    time_limit = min(50, limit * 2)  # 시간 관련 질문은 더 많은 메시지 검색
                
                # 키워드 기반 검색
                if keyword_conditions:
                    stmt = select(DiscordMessage).where(
                        and_(*conditions, or_(*keyword_conditions))
                    ).order_by(DiscordMessage.created_at.desc()).limit(time_limit)
                    
                    result = await session.execute(stmt)
                    messages = result.scalars().all()
                    
                    # 정확한 매치와 병합하고 중복 제거
                    all_messages = filtered_exact_matches.copy()
                    for msg in messages:
                        if msg.id not in seen_ids:
                            seen_ids.add(msg.id)
                            all_messages.append(msg)
                    
                    # 충분한 결과가 나왔으면 그대로 반환
                    if len(all_messages) >= 1:  # 최소 1개라도 있으면 반환 (원래 5)
                        logger.info(f"키워드 검색으로 {len(all_messages)}개의 관련 메시지를 찾았습니다.")
                        return all_messages[:limit]  # 최대 limit 개수만큼 반환
                    
                    # 충분한 결과가 없으면 키워드 확장 검색
                    logger.info(f"키워드 검색 결과가 부족합니다 ({len(all_messages)}개). 확장 검색을 시도합니다.")
                
                # 3단계: 확장 검색 - 단어 일부 매칭 및 유사어 검색
                expanded_conditions = []
                
                # 키워드 변형 (축약형이나 일부만 포함된 경우 검색)
                for keyword in keywords[:5]:  # 상위 5개 키워드만 변형
                    if len(keyword) >= 4:  # 4글자 이상인 단어만 부분 매칭
                        # 단어의 앞부분만 사용한 검색
                        expanded_conditions.append(DiscordMessage.content.ilike(f'%{keyword[:len(keyword)-1]}%'))
                
                # 확장 검색 실행
                if expanded_conditions:
                    stmt = select(DiscordMessage).where(
                        and_(*conditions, or_(*expanded_conditions))
                    ).order_by(DiscordMessage.created_at.desc()).limit(limit)
                    
                    result = await session.execute(stmt)
                    expanded_messages = result.scalars().all()
                    
                    # 기존 결과와 병합
                    all_messages = filtered_exact_matches.copy()
                    for msg in messages:
                        if msg.id not in seen_ids:
                            seen_ids.add(msg.id)
                            all_messages.append(msg)
                    
                    for msg in expanded_messages:
                        if msg.id not in seen_ids:
                            seen_ids.add(msg.id)
                            all_messages.append(msg)
                    
                    if all_messages:
                        logger.info(f"확장 검색 포함 총 {len(all_messages)}개의 관련 메시지를 찾았습니다.")
                        return all_messages[:limit]
                
                # 4단계: SQL LIKE 검색 시도 (부분 일치)
                # 핵심 키워드 2개만 사용
                core_keywords = keywords[:2] if keywords else []
                if core_keywords:
                    partial_conditions = []
                    for keyword in core_keywords:
                        if len(keyword) > 2:
                            # SQL LIKE 패턴 적용
                            partial_conditions.append(
                                DiscordMessage.content.ilike(f'%{keyword[:3]}%')  # 앞 3글자만 검색
                            )
                    
                    if partial_conditions:
                        stmt = select(DiscordMessage).where(
                            and_(*conditions, or_(*partial_conditions))
                        ).order_by(DiscordMessage.created_at.desc()).limit(limit)
                        
                        result = await session.execute(stmt)
                        partial_matches = result.scalars().all()
                        
                        # 이전 결과와 병합
                        final_messages = []
                        seen_final_ids = set()
                        
                        # 먼저 정확한 매치 추가
                        for msg in filtered_exact_matches:
                            if msg.id not in seen_final_ids:
                                seen_final_ids.add(msg.id)
                                final_messages.append(msg)
                        
                        # 다음 OR 조건 매치 추가
                        for msg in messages:
                            if msg.id not in seen_final_ids:
                                seen_final_ids.add(msg.id)
                                final_messages.append(msg)
                        
                        # 마지막 부분 매치 추가
                        for msg in partial_matches:
                            if msg.id not in seen_final_ids:
                                seen_final_ids.add(msg.id)
                                final_messages.append(msg)
                        
                        if final_messages:
                            logger.info(f"부분 매치 포함 총 {len(final_messages)}개의 관련 메시지를 찾았습니다.")
                            return final_messages[:limit]
                
                # 여전히 충분한 결과가 없으면 최근 메시지 반환
                logger.warning("관련 메시지를 찾을 수 없습니다. 최근 메시지를 반환합니다.")
                return await self.get_recent_messages(limit)
                
        except Exception as e:
            logger.error(f"관련 메시지 검색 중 오류 발생: {str(e)}", exc_info=True)
            return await self.get_recent_messages(limit)
    
    async def get_recent_messages(self, limit: int = 100) -> List[DiscordMessage]:
        """최근 메시지를 가져옴 (백업 방법)
        
        Args:
            limit: 가져올 메시지 수
            
        Returns:
            최근 메시지 목록
        """
        try:
            logger.info(f"최근 {limit}개 메시지를 가져오는 중...")
            
            # 최근 메시지 가져오기
            async with self.db_manager.AsyncSessionLocal() as session:
                # 비어있지 않은 메시지만 가져옴, 봇 메시지 제외
                stmt = select(DiscordMessage).where(
                    DiscordMessage.content.isnot(None),
                    DiscordMessage.content != ""
                )
                
                # 봇 ID가 설정되어 있으면 봇 메시지 제외
                if self.bot_id_list:
                    # 여러 봇 ID 처리
                    for bot_id in self.bot_id_list:
                        stmt = stmt.where(DiscordMessage.author_id != bot_id)
                
                # 최근 메시지부터 정렬
                stmt = stmt.order_by(DiscordMessage.created_at.desc()).limit(limit)
                
                result = await session.execute(stmt)
                messages = result.scalars().all()
                
                if not messages:
                    logger.warning("가져올 메시지가 없습니다.")
                    return []
                
                logger.info(f"{len(messages)}개의 최근 메시지를 가져왔습니다.")
                return messages
                
        except Exception as e:
            logger.error(f"메시지 가져오기 중 오류 발생: {str(e)}", exc_info=True)
            return []
    
    async def generate_response(self, query: str, context_messages: List[Dict] = None, system_prompt: str = None) -> Dict[str, Any]:
        """LLM API를 사용하여 응답을 생성
        
        Args:
            query: 사용자 질문
            context_messages: 컨텍스트로 추가할 메시지 목록
            system_prompt: 시스템 프롬프트 (없으면 기본값 사용)
            
        Returns:
            응답 텍스트를 포함한 딕셔너리
        """
        # 시작 시간 기록
        start_time = time.time()
        logger.info(f"[🔍] 응답 생성 시작 (약 10-30초 소요)...")
        
        # 시스템 프롬프트 기본값 설정
        if not system_prompt:
            system_prompt = self.get_system_prompt()
        
        # API 요청 메시지 구성
        messages = [
            {"role": "system", "content": system_prompt}
        ]
        
        # 컨텍스트 메시지가 없거나 관련 없는 메시지인지 확인
        has_relevant_context = False
        
        # 인식할 수 있는 최대 토큰(문자) 수 제한에 맞게 메시지 추가
        try:
            if context_messages:
                # 메시지를 시간순으로 정렬 (오래된 순)
                sorted_messages = sorted(
                    context_messages, 
                    key=lambda x: x.get('created_at', '0') if x.get('created_at') else '0'
                )
                
                # 키워드와 메시지 내용의 관련성 검사
                keywords = self.extract_keywords(query)
                if keywords and sorted_messages:
                    # 모든 키워드 추출 (분해된 키워드 포함)
                    all_keywords = keywords.copy()
                    decomposed_keywords = []
                    
                    # 분해된 키워드 추가 (예: '당근파일럿'의 경우 '당근', '파일럿' 추가)
                    for keyword in keywords:
                        if len(keyword) >= 4:
                            # 한글의 경우 보통 2글자씩 의미를 가지므로 2글자 단위로 분해
                            # 영문이나 혼합된 경우는 그대로 사용
                            if re.match(r'^[가-힣]+$', keyword):
                                for i in range(0, len(keyword), 2):
                                    if i + 2 <= len(keyword):
                                        part = keyword[i:i+2]
                                        if len(part) >= 2 and part not in all_keywords:
                                            decomposed_keywords.append(part)
                    
                    # 주요 키워드와 분해 키워드 구분 (주요 키워드에 우선 점수 부여)
                    all_keywords.extend(decomposed_keywords)
                    
                    # 각 메시지에 대한 관련성 점수 계산
                    message_scores = []
                    
                    for msg in sorted_messages:
                        content = msg.get('content', '').lower()
                        score = 0
                        matched_keywords = []
                        
                        # 1. 주요 키워드 먼저 확인 (원본 키워드)
                        for keyword in keywords:
                            if len(keyword) >= 2 and keyword.lower() in content:
                                # 주요 키워드 매치는 높은 점수 부여
                                score += 5
                                matched_keywords.append(keyword)
                                # 첫 2개 키워드는 중요도가 더 높음
                                if keyword in keywords[:2]:
                                    score += 3
                        
                        # 2. 분해 키워드 확인 (더 낮은 가중치)
                        for keyword in decomposed_keywords:
                            if len(keyword) >= 2 and keyword.lower() in content:
                                # 분해된 키워드는 낮은 점수 부여
                                score += 1
                                matched_keywords.append(keyword)
                        
                        # 3. 특별한 케이스: '당근파일럿'과 같은 주요 복합 키워드가 있는 경우
                        # 이 경우 '당근'과 '설치'만 있는 메시지보다 '당근파일럿'을 포함한 메시지를 우선시
                        for i, keyword in enumerate(keywords):
                            if i == 0 and len(keyword) >= 4 and keyword.lower() in content:
                                # 첫 번째 키워드(가장 중요)가 메시지에 포함되어 있으면 추가 점수
                                score += 10
                        
                        # 점수가 있는 메시지만 후보로 기록
                        if score > 0:
                            message_scores.append((msg, score, matched_keywords))
                    
                    # 점수 기준 정렬 (높은 점수가 앞으로)
                    message_scores.sort(key=lambda x: x[1], reverse=True)
                    
                    # 점수 로깅 및 관련성 여부 결정
                    if message_scores:
                        # 최소 점수 기준 설정 (조정 가능)
                        min_score_threshold = 3  # 기존 5에서 3으로 낮춤 - 당조3 같은 짧은 키워드에 적합
                        
                        # 높은 점수의 메시지가 있다면 관련성 있다고 판단
                        if message_scores[0][1] >= min_score_threshold:
                            has_relevant_context = True
                            top_message, score, matched = message_scores[0]
                            logger.info(f"가장 관련성 높은 메시지 (점수: {score}): {top_message.get('content', '')[:50]}...")
                            logger.info(f"일치 키워드: {', '.join(matched)}")
                        else:
                            # 점수가 낮은 경우, 첫 번째 주요 키워드가 포함된 메시지가 있는지 확인
                            if keywords and any(keywords[0].lower() in msg.get('content', '').lower() for msg, _, _ in message_scores):
                                has_relevant_context = True
                                logger.info(f"주요 키워드 '{keywords[0]}' 포함 메시지가 있어 관련성 있다고 판단함")
                            else:
                                # 점수가 낮고 주요 키워드도 없는 경우는 관련성이 낮다고 판단
                                has_relevant_context = False
                                logger.warning(f"메시지가 있지만 관련성 점수가 낮습니다 (최고 점수: {message_scores[0][1] if message_scores else 0})")
                    else:
                        # 키워드가 직접 매치되지 않은 경우, 단순히 메시지가 존재하는지만 확인
                        # 이는 find_relevant_messages가 이미 필터링을 했다는 것을 감안한 접근
                        if sorted_messages:
                            has_relevant_context = True
                            logger.info("점수화되지 않았지만 관련 메시지가 존재합니다.")
                
                # 관련 컨텍스트가 있는 경우에만 메시지 추가 
                # 또는 점수화 결과를 기반으로 상위 메시지만 추가
                sorted_messages_to_use = []
                if has_relevant_context:
                    # 점수화된 결과가 있으면 점수 기준으로 상위 메시지 선택
                    if 'message_scores' in locals() and message_scores:
                        # 점수 기준 상위 메시지만 사용 (최대 30개, 점수 2 이상)
                        high_scored_messages = [msg for msg, score, _ in message_scores if score >= 2]  # 기존 4에서 2로 낮춤
                        sorted_messages_to_use = high_scored_messages[:30]  # 상위 30개로 제한
                        logger.info(f"점수 기준 선택된 메시지: {len(sorted_messages_to_use)}개")
                    else:
                        # 기존 방식대로 모든 메시지 사용
                        sorted_messages_to_use = sorted_messages
                    
                    # 선택된 메시지를 API 요청에 추가
                    for msg in sorted_messages_to_use:
                        # 메시지를 context로 변환하고 추가
                        context_message = {"role": "user", "content": ""}
                        
                        # add_info 함수 호출
                        new_context_message = self.add_info(context_message, msg)
                        
                        # 메시지가 유효한 경우 추가
                        if new_context_message:
                            messages.append(new_context_message)
            
            # 사용자 질문 추가 (컨텍스트 관련성 정보 포함)
            if not has_relevant_context:
                # 관련 정보가 없는 경우 명확한 지시를 포함한 질문으로 변경
                enhanced_query = f"{query}\n\n참고: 이 질문에 관련된 정보가 데이터베이스에 없습니다. 질문과 관련된 정보가 없다고 명확하게 답변해주세요. 관련 없는 내용으로 답변하지 마세요."
                messages.append({"role": "user", "content": enhanced_query})
            else:
                # 관련 정보가 있는 경우 해당 정보를 활용하도록 지시
                enhanced_query = f"{query}\n\n참고: 위 메시지들에 질문과 관련된 정보가 제공되었습니다. 이 정보를 바탕으로 질문에 답변해주세요. 제공된 정보가 질문과 직접적으로 일치하지 않더라도, 간접적으로 관련된 정보를 활용하여 가능한 한 도움이 되는 답변을 제공하세요. 완전히 관련 없는 정보만 있다면 솔직하게 '관련 정보를 찾을 수 없습니다'라고 답변하세요."
                messages.append({"role": "user", "content": enhanced_query})
            
            # API 요청 실행 (aiohttp 사용)
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url=self.api_url,
                    headers={"Content-Type": "application/json"},
                    json={
                        "model": self.model_name,
                        "messages": messages,
                        "temperature": 0.1,  # 낮은 temperature로 사실적인 응답 유도
                        "max_tokens": 2000   # 응답 길이 제한
                    },
                    timeout=180  # 타임아웃 적용 (초)
                ) as response:
                    response_data = await response.json()
            
            if 'error' in response_data:
                logger.error(f"[❌] API 오류: {response_data['error']}")
                return {
                    "response": f"오류가 발생했습니다: {response_data.get('error', {}).get('message', '알 수 없는 오류')}",
                    "usage": {"prompt_tokens": 0, "completion_tokens": 0},
                    "status": "error"
                }
            
            # 응답 추출
            model_response = response_data['choices'][0]['message']['content']
            usage = response_data.get('usage', {"prompt_tokens": 0, "completion_tokens": 0})
            
            elapsed_time = time.time() - start_time
            logger.info(f"[✅] 응답 생성 완료 (소요시간: {elapsed_time:.2f}초)")
            logger.info(f"[📊] 토큰 사용량: 프롬프트 {usage['prompt_tokens']}개, 응답 {usage['completion_tokens']}개")
            
            # 컨텍스트 관련성 없을 때 로그 추가
            if not has_relevant_context:
                first_line = query.split('\n')[0] if '\n' in query else query
                logger.warning(f"[⚠️] 질문 '{first_line}'에 관련된 컨텍스트가 없습니다. 관련 정보 없음 응답 생성")
            
            return {
                "response": model_response,
                "usage": usage,
                "status": "success",
                "elapsed_time": elapsed_time,
                "has_relevant_context": has_relevant_context
            }
            
        except Exception as e:
            logger.error(f"[❌] 응답 생성 중 오류 발생: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            
            return {
                "response": f"죄송합니다, 응답 생성 중 오류가 발생했습니다: {str(e)}",
                "usage": {"prompt_tokens": 0, "completion_tokens": 0},
                "status": "error"
            }

    def get_system_prompt(self):
        """시스템 프롬프트 반환"""
        return f"""당신은 디스코드 서버의 채팅 기록을 기반으로 질문에 답변하는 친근한 AI 도우미입니다.
오직 제공된 채팅 기록의 정보만을 사용하여 응답해주세요.

중요 지침:
1. 외부 지식이나 정보는 절대 사용하지 마세요. 오직 제공된 메시지만 참고하세요.
2. 제공된 메시지에 관련 정보가 있으나 불완전하다면, 그 정보를 바탕으로 최대한 도움이 되는 답변을 제공하세요. 
3. 제공된 메시지에 질문과 직접 관련된 정보가 전혀 없는 경우에만 "죄송합니다만, 질문하신 내용에 대한 관련 정보를 찾을 수 없습니다."라고 명확하게 답변하세요.
4. 부분적으로 관련된 정보가 있다면, 그 정보를 활용하여 가능한 한 유용한 답변을 제공하세요.
5. 답변에 정확한 정보만 포함시키세요. 추측하거나 채팅 기록에 없는 내용을 만들어내지 마세요.
6. 디스코드 서버에서 수집된 메시지임을 명시적으로 언급하지 마세요.
7. 출처나 작성자 정보를 절대 포함하지 마세요. 메시지 내용만 전달하세요.
8. 어떤 형태로든 참조 정보나 출처를 표시하지 마세요. 어떠한 경우에도 참조 번호나 인용 표시를 사용하지 마세요.
9. '~에 따르면', '~가 언급했듯이', '~의 메시지에서'와 같은 표현을 사용하지 마세요.
10. 내용만 전달하고, 그 출처에 대해서는 어떤 언급도 하지 마세요.
11. 메시지에 작성자, 시간, 채널 정보가 포함되어 있더라도 이를 응답에 언급하지 마세요.
12. "참조 정보", "출처", "인용" 등의 섹션이나 표시를 절대 사용하지 마세요.
13. 검색된 메시지가 짧더라도 내용을 그대로 사용하세요. 메시지를 추가 설명 없이 반환하지 마세요.
14. 질문과 간접적으로라도 관련된 내용이 있다면 그 내용을 활용해 답변하세요. 완전히 관련 없는 경우에만 관련 정보가 없다고 답변하세요.
15. 절대로 "관련 정보가 없지만, ..."과 같은 식으로 답변하지 마세요. 관련 정보가 전혀 없는 경우에만 "관련 정보를 찾을 수 없습니다"라고 답변하세요.

답변 형식:
- 존댓말을 쓰며 친근하고 전문성있게 대답하세요.
- 디스코드 마크다운을 활용하여 가독성 좋게 답변을 구성하세요:
  * 중요한 내용은 **굵은 글씨**로 강조
  * 목록이 필요할 때는 bullet points 사용
  * 코드는 `코드 블록`으로 표시
  * 긴 코드는 ```언어 코드블록``` 형식으로 표시
  * 제목이나 소제목은 ### 또는 ## 사용
- 간결하고 명확하게 답변하되, 친근한 어투를 유지하세요.
- 질문이 너무 짧거나 모호해도 가능한 한 관련 정보를 제공하세요.

이 지침을 철저히 따라 사용자의 질문에 친근하고 도움이 되는 답변을 제공해주세요."""

    def add_info(self, context_message, msg):
        """컨텍스트 메시지에 정보를 추가"""
        # 기본 메시지 내용 설정
        formatted_content = msg.get('content', '')
        
        # 메시지 내용이 없으면 무시
        if not formatted_content:
            return None
        
        # 메시지 내용 정제 (메시지 구분을 위한 마커 추가)
        if formatted_content.strip():
            # 생성 시간 정보 추가 (이 정보는 참조 정보가 아니라 시간적 맥락을 위해 유지)
            created_at = msg.get('created_at')
            if created_at:
                try:
                    # ISO 포맷 문자열을 datetime으로 파싱
                    created_datetime = datetime.fromisoformat(created_at)
                    # 한국 시간대로 변환 (UTC+9)
                    kst = timezone(timedelta(hours=9))
                    created_datetime = created_datetime.astimezone(kst)
                    # 날짜 포맷 (년-월-일)
                    date_str = created_datetime.strftime("%Y-%m-%d")
                    
                    # 메시지 내용 앞에 날짜 추가 (작성자 및 채널 정보 제외)
                    context_message["content"] = f"[{date_str}] {formatted_content}"
                except (ValueError, TypeError) as e:
                    # 날짜 파싱 오류 시 원본 내용만 사용
                    context_message["content"] = formatted_content
            else:
                # 생성 시간 없으면 원본 내용만 사용
                context_message["content"] = formatted_content
        
        return context_message

# LLM 매니저 싱글톤 인스턴스
_llm_manager = None
_guild_llm_managers = {}

def get_llm_manager(guild_id=None) -> LLMManager:
    """LLM 매니저 싱글톤 인스턴스 반환
    
    Args:
        guild_id: 서버 ID, 지정하면 서버별 데이터베이스를 사용함
        
    Returns:
        LLMManager 인스턴스
    """
    global _llm_manager, _guild_llm_managers
    
    # 서버 ID가 지정된 경우, 서버별 LLM 매니저 사용
    if guild_id:
        if guild_id not in _guild_llm_managers:
            _guild_llm_managers[guild_id] = LLMManager(guild_id=guild_id)
        return _guild_llm_managers[guild_id]
    
    # 기본 LLM 매니저
    if _llm_manager is None:
        _llm_manager = LLMManager()
    
    return _llm_manager 