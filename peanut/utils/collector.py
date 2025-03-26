import asyncio
import logging
import discord
import colorama
import re
import json
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional, Any, Tuple

from ..db.database import get_db_manager
from ..utils.config import get_config

# 색상 초기화
colorama.init()

# 로깅 설정
logger = logging.getLogger('discord.collector')

class MessageCollector:
    """디스코드 메시지 수집기 클래스"""
    def __init__(self, bot):
        self.bot = bot
        self.db_manager = get_db_manager()  # 기본 DB 매니저 (하위 호환성 유지)
        self.is_collecting = False
        self.collection_tasks = {}
        self.guild_collection_tasks = {}  # 서버별 수집 태스크
        self.config = get_config()
        self.bot_id = self.config.get('BOT_ID')
        self.collection_interval = int(self.config.get('COLLECTION_INTERVAL', 30 * 60))
        
        # 메시지 로깅 색상 설정
        self.colors = {
            'info': colorama.Fore.CYAN,
            'success': colorama.Fore.GREEN,
            'warning': colorama.Fore.YELLOW,
            'error': colorama.Fore.RED,
            'reset': colorama.Style.RESET_ALL
        }
    
    def analyze_message_content(self, content: str) -> Dict[str, Any]:
        """메시지 내용을 분석하여 주제, 마크다운, 콘텐츠 구조, 섹션 등을 추출
        
        Args:
            content: 메시지 내용
            
        Returns:
            분석 결과 딕셔너리
        """
        if not content:
            return {
                'topics': [],
                'sections': [],
                'markdown_used': [],
                'message_type': 'unknown',
                'content_structure': []
            }
        
        # 분석 결과 초기화
        analysis = {
            'topics': [],           # 주제 목록
            'sections': [],         # 섹션 구분 (여러 주제가 있는 경우)
            'markdown_used': [],    # 사용된 마크다운
            'message_type': 'text', # 메시지 유형 (text, code, question, explanation)
            'content_structure': [] # 콘텐츠 구조 (sections, paragraphs 등)
        }
        
        # 마크다운 분석
        markdown_patterns = {
            'code_block': re.compile(r'```(?:\w+)?\n(.+?)\n```', re.DOTALL),
            'inline_code': re.compile(r'`([^`]+)`'),
            'bold': re.compile(r'\*\*(.+?)\*\*'),
            'italic': re.compile(r'\*(.+?)\*'),
            'heading': re.compile(r'^#{1,6}\s+(.+?)$', re.MULTILINE),
            'bullet_list': re.compile(r'^\s*[\*\-\+]\s+(.+?)$', re.MULTILINE),
            'numbered_list': re.compile(r'^\s*\d+\.\s+(.+?)$', re.MULTILINE),
            'blockquote': re.compile(r'^\s*>\s+(.+?)$', re.MULTILINE),
            'link': re.compile(r'\[(.+?)\]\((.+?)\)')
        }
        
        for md_type, pattern in markdown_patterns.items():
            if pattern.search(content):
                analysis['markdown_used'].append(md_type)
        
        # 코드 블록이 많으면 코드 유형으로 판단
        if 'code_block' in analysis['markdown_used'] and len(re.findall(r'```', content)) >= 2:
            analysis['message_type'] = 'code'
        
        # 질문 패턴 분석
        question_patterns = [r'\?$', r'어떻게', r'무엇', r'언제', r'어디', r'누구', r'왜', r'질문', r'알려줘', r'알고 싶어']
        for pattern in question_patterns:
            if re.search(pattern, content):
                analysis['message_type'] = 'question'
                break
        
        # 설명 패턴 분석
        explanation_patterns = [r'설명', r'방법', r'다음과 같이', r'다음과 같은', r'입니다', r'됩니다', r'~입니다', r'~됩니다']
        if analysis['message_type'] != 'question':  # 이미 질문으로 분류되지 않았다면
            for pattern in explanation_patterns:
                if re.search(pattern, content):
                    analysis['message_type'] = 'explanation'
                    break
        
        # 콘텐츠 구조 분석
        
        # 1. 헤더 기반 구조 분석
        header_sections = re.split(r'^#{1,6}\s+(.+?)$', content, flags=re.MULTILINE)
        if len(header_sections) > 2:  # 헤더가 있으면
            sections = [s.strip() for s in header_sections if s.strip()]
            analysis['content_structure'].append('headers')
        
        # 2. 줄바꿈 기반 단락 분석
        paragraphs = [p.strip() for p in content.split('\n\n') if p.strip()]
        if len(paragraphs) > 1:
            analysis['content_structure'].append('paragraphs')
        
        # 3. 목록 구조 분석
        if re.search(r'^\s*[\*\-\+]\s+(.+?)$', content, re.MULTILINE) or re.search(r'^\s*\d+\.\s+(.+?)$', content, re.MULTILINE):
            analysis['content_structure'].append('lists')
        
        # 주제 추출 및 섹션 분석 (개선된 알고리즘)
        # 1. 빈 줄로 구분된 섹션 식별
        sections = []
        current_section = {"title": "", "content": "", "subtopics": []}
        
        # 빈 줄 기준으로 섹션 분리 (기본 분리)
        raw_sections = re.split(r'\n\s*\n', content)
        if len(raw_sections) > 1:
            analysis['content_structure'].append('multi_section')
        
        # 2. 주제와 제목 패턴 인식
        title_patterns = [
            # 제목 다음 개행
            (r'^([^\n:]+)[\s]*\n', 1),
            # 물음표로 끝나는 문장
            (r'^([^\n]+\?)[\s]*\n', 1),
            # 콜론으로 구분된 형태 (제목: 내용)
            (r'^([^:]+):(.+)$', 1)
        ]
        
        # 섹션 분석
        for i, section_text in enumerate(raw_sections):
            if not section_text.strip():
                continue
                
            section = {"content": section_text.strip(), "subtopics": [], "title": ""}
            
            # 첫 줄이나 패턴에서 섹션 제목 추출
            lines = section_text.strip().split('\n')
            potential_title = lines[0].strip() if lines else ""
            
            # 제목 패턴 검출
            is_title_found = False
            for pattern, group in title_patterns:
                title_match = re.match(pattern, section_text, re.MULTILINE)
                if title_match:
                    potential_title = title_match.group(group).strip()
                    is_title_found = True
                    break
            
            # 제목이 특별한 패턴을 가진 경우
            if potential_title.endswith('?') or len(potential_title) < 50:
                section["title"] = potential_title
                analysis['topics'].append(potential_title)
            
            # 하위 주제 추출 (콜론으로 구분된 경우)
            subtopic_pattern = re.findall(r'^([^:]+):\s*(.+)$', section_text, re.MULTILINE)
            for topic, _ in subtopic_pattern:
                topic = topic.strip()
                if topic and topic != section["title"] and len(topic) < 50:
                    section["subtopics"].append(topic)
                    analysis['topics'].append(topic)
            
            sections.append(section)
        
        # 특정 패턴으로 구분된 섹션 추가 처리
        section_divider_patterns = [
            r'\d+\.\s+(.+?)\n',  # 숫자 + 점 + 공백 + 제목 패턴 (예: "1. 제목")
            r'^-+\s*$',         # 구분선 패턴 (----------)
            r'^=+\s*$',         # 구분선 패턴 (==========)
        ]
        
        # 패턴에 따라 더 정확한 섹션 구분 시도
        for pattern in section_divider_patterns:
            if re.search(pattern, content, re.MULTILINE):
                analysis['content_structure'].append('sectioned')
                break
        
        # 섹션 저장
        analysis['sections'] = sections
        
        # 마크다운, 주제, 콘텐츠 구조 중복 제거
        for key in ['markdown_used', 'content_structure', 'topics']:
            analysis[key] = list(set(analysis[key]))
        
        return analysis
    
    def message_to_dict(self, message: discord.Message) -> Dict[str, Any]:
        """Discord 메시지를 데이터베이스 저장용 딕셔너리로 변환
        
        Args:
            message: Discord 메시지 객체
            
        Returns:
            저장용 딕셔너리 또는 None (무시할 메시지인 경우)
        """
        # 봇 메시지 필터링
        if hasattr(self.bot, 'bot_id'):
            # 봇 ID가 쉼표로 구분된 여러 ID를 포함하는 경우 처리
            bot_ids = [bot_id.strip() for bot_id in str(self.bot.bot_id).split(',')]
            if str(message.author.id) in bot_ids:
                logger.debug(f"[🤖] 봇(ID: {message.author.id})의 메시지는 무시합니다: {message.id}")
                return None
            
        # 첨부 파일 처리
        attachments = []
        for attachment in message.attachments:
            attachments.append({
                'url': attachment.url,
                'filename': attachment.filename,
                'size': attachment.size
            })
            
        # 채널 및 서버 정보 처리
        channel_name = None
        guild_id = None
        guild_name = None
        message_url = None
        
        # 채널 정보 확인
        if hasattr(message.channel, 'name'):
            channel_name = message.channel.name
        else:
            # 일부 채널 유형은 name 속성이 없을 수 있음
            channel_name = f"채널-{message.channel.id}"
            
        # 스레드 처리
        is_thread = False
        thread_name = None
        parent_channel_id = None
        parent_channel_name = None
        
        # 채널 유형 확인
        channel_type = None
        try:
            channel_type = message.channel.type
        except Exception:
            channel_type = None
            
        # 스레드인 경우 부모 채널 정보도 함께 저장
        if channel_type in [discord.ChannelType.public_thread, discord.ChannelType.private_thread, discord.ChannelType.news_thread]:
            is_thread = True
            thread_name = getattr(message.channel, 'name', f"스레드-{message.channel.id}")
            
            # 부모 채널 정보
            parent = getattr(message.channel, 'parent', None)
            if parent:
                parent_channel_id = str(parent.id)
                parent_channel_name = getattr(parent, 'name', f"채널-{parent.id}")
            
        # 서버 정보 확인
        if message.guild:
            guild_id = str(message.guild.id)
            guild_name = message.guild.name
            
            # 메시지 URL 생성
            message_url = f"https://discord.com/channels/{message.guild.id}/{message.channel.id}/{message.id}"
        else:
            # DM 또는 그룹 DM인 경우
            message_url = f"https://discord.com/channels/@me/{message.channel.id}/{message.id}"
            
        # 메시지 내용 분석
        content_analysis = self.analyze_message_content(message.content)
        
        # 저장용 딕셔너리 생성
        result = {
            'message_id': str(message.id),
            'channel_id': str(message.channel.id),
            'guild_id': guild_id,
            'channel_name': channel_name,
            'guild_name': guild_name,
            'author_id': str(message.author.id),
            'author_name': message.author.name,
            'content': message.content,
            'created_at': message.created_at,
            'attachments_count': len(message.attachments),
            'attachments_urls': json.dumps(attachments) if attachments else None,
            'collected_at': datetime.now(),
            
            # 추가 분석 정보
            'message_url': message_url,
            'topics': json.dumps(content_analysis['topics'], ensure_ascii=False) if content_analysis['topics'] else None,
            'message_type': content_analysis['message_type'],
            'content_structure': json.dumps(content_analysis['content_structure'], ensure_ascii=False) if content_analysis['content_structure'] else None,
            'markdown_used': json.dumps(content_analysis['markdown_used'], ensure_ascii=False) if content_analysis['markdown_used'] else None,
            'sections': json.dumps(content_analysis['sections'], ensure_ascii=False) if content_analysis['sections'] else None,
        }
        
        # 스레드 관련 정보 추가
        if is_thread:
            result['is_thread'] = True
            result['thread_name'] = thread_name
            result['parent_channel_id'] = parent_channel_id
            result['parent_channel_name'] = parent_channel_name
            
        return result
    
    async def collect_channel_messages(self, channel, after_date: Optional[datetime] = None, db_manager=None):
        """특정 채널의 메시지 수집
        
        Args:
            channel: 디스코드 채널 객체 (TextChannel, ForumChannel, Thread 등)
            after_date: 이 날짜 이후의 메시지만 수집 (기본: None)
            db_manager: 사용할 데이터베이스 매니저 (기본: None, None이면 기본 매니저 사용)
            
        Returns:
            수집한 메시지 수
        """
        # 모든 채널 유형 확인
        channel_type = None
        try:
            channel_type = channel.type
            channel_name = getattr(channel, 'name', str(channel.id))
        except Exception as e:
            logger.error(f"채널 타입 확인 중 오류 발생: {str(e)}")
            return 0
            
        # 채널 유형에 따른 처리
        if channel_type == discord.ChannelType.text:
            channel_type_str = "텍스트"
        elif channel_type == discord.ChannelType.voice:
            channel_type_str = "음성"
        elif channel_type == discord.ChannelType.forum:
            channel_type_str = "포럼"
        elif channel_type == discord.ChannelType.news:
            channel_type_str = "뉴스"
        elif channel_type in [discord.ChannelType.public_thread, discord.ChannelType.private_thread, discord.ChannelType.news_thread]:
            channel_type_str = "스레드"
        else:
            channel_type_str = f"기타({channel_type})"
            
        # 채널 또는 서버 권한 확인 (읽기 권한이 없으면 수집 불가)
        can_read = False
        try:
            if hasattr(channel, 'permissions_for'):
                perms = channel.permissions_for(channel.guild.me)
                can_read = perms.read_messages
            else:
                # 스레드 등 일부 채널은 다른 방식으로 권한 확인
                can_read = True  # 기본적으로 접근 가능하다고 가정
        except Exception as e:
            logger.warning(f"채널 권한 확인 중 오류 발생: {str(e)}")
            can_read = False
            
        if not can_read:
            logger.warning(f"{channel_type_str} 채널 '{channel_name}'({channel.id})에 대한 읽기 권한이 없어 메시지를 수집할 수 없습니다.")
            return 0
            
        # 권한이 있어도 봇이 채널을 볼 수 없는 다른 이유가 있을 수 있음
        try:
            # 테스트로 채널 ID에 접근해봄
            channel_id = channel.id
        except discord.errors.Forbidden:
            logger.warning(f"채널 ID {channel.id}에 접근할 수 없습니다. 권한 문제일 수 있습니다.")
            return 0
            
        try:
            logger.info(f"{channel_type_str} 채널 '{channel_name}'({channel.id}) 메시지 수집 시작")
            
            # 사용할 DB 매니저 결정
            if db_manager is None:
                db_manager = self.db_manager
                
            # 채널별 마지막 수집 시간 키 생성
            channel_last_collected_key = f"last_collected_channel_{channel.id}"
                
            # 최근 저장된 메시지 날짜 확인
            if after_date is None:
                # 채널별 마지막 수집 시간 먼저 확인
                channel_last_collected = await db_manager.get_collection_metadata(channel_last_collected_key)
                if channel_last_collected:
                    try:
                        after_date = datetime.strptime(channel_last_collected, '%Y-%m-%d %H:%M:%S')
                        logger.info(f"채널 '{channel_name}' 마지막 수집 시간: {after_date.strftime('%Y-%m-%d %H:%M:%S')}")
                    except ValueError:
                        logger.warning(f"채널 마지막 수집 시간 형식이 잘못되었습니다: {channel_last_collected}")
                        after_date = None
                
                # 채널별 데이터가 없으면 데이터베이스의 최신 메시지로 확인
                if after_date is None:
                    after_date = await db_manager.get_latest_message_date(channel.guild.id, channel.id)
                    if after_date:
                        logger.info(f"채널 '{channel_name}' 최신 메시지 날짜: {after_date.strftime('%Y-%m-%d %H:%M:%S')}")
                
                if after_date:
                    logger.info(f"'{channel_name}' 채널에서 {after_date.strftime('%Y-%m-%d %H:%M:%S')} 이후의 새 메시지만 수집합니다.")
            else:
                logger.info(f"'{channel_name}' 채널에서 {after_date.strftime('%Y-%m-%d %H:%M:%S')} 이후의 메시지만 수집합니다.")
                    
            # 메시지 수집
            processed_messages = []
            collected_count = 0
            
            # API 요청 최적화를 위한 배치 크기
            batch_size = 50
            
            try:
                if hasattr(channel, 'history'):
                    # 일반 채널 및 스레드 처리
                    # 메시지 검색 매개변수 설정
                    kwargs = {
                        'limit': 100,  # 한 번에 최대 100개씩 가져오기
                        'oldest_first': False  # 최신 메시지부터 가져오기
                    }
                    
                    if after_date:
                        kwargs['after'] = after_date
                        
                    async for message in channel.history(**kwargs):
                        # 봇 자신의 메시지는 무시
                        if self.bot_id:
                            # BOT_ID가 쉼표로 구분된 여러 ID를 포함하는 경우 처리
                            bot_ids = [bot_id.strip() for bot_id in str(self.bot_id).split(',')]
                            if str(message.author.id) in bot_ids:
                                continue
                            
                        # 메시지를 딕셔너리로 변환
                        message_dict = self.message_to_dict(message)
                        if message_dict:  # None이 아닌 경우에만 추가
                            processed_messages.append(message_dict)
                            collected_count += 1
                        
                        # 배치 단위로 저장
                        if len(processed_messages) >= batch_size:
                            await db_manager.save_messages(processed_messages)
                            processed_messages = []
                            
                            # API 요청 제한 완화를 위한 짧은 대기
                            await asyncio.sleep(0.1)
                elif channel_type == discord.ChannelType.forum:
                    # 포럼 채널 처리 - 활성 스레드 수집
                    if hasattr(channel, 'threads'):
                        # 활성 스레드 처리
                        for thread in channel.threads:
                            thread_count = await self.collect_channel_messages(thread, after_date, db_manager)
                            collected_count += thread_count
                            
                            # 스레드마다 잠시 대기 (레이트 리밋 방지)
                            await asyncio.sleep(0.5)
                        
                        # 보관된 스레드도 처리
                        if hasattr(channel, 'archived_threads'):
                            try:
                                async for thread in channel.archived_threads():
                                    thread_count = await self.collect_channel_messages(thread, after_date, db_manager)
                                    collected_count += thread_count
                                    
                                    # 스레드마다 잠시 대기 (레이트 리밋 방지)
                                    await asyncio.sleep(0.5)
                            except Exception as e:
                                logger.warning(f"보관된 스레드 수집 중 오류 발생: {str(e)}")
                else:
                    logger.info(f"채널 타입 {channel_type_str}은(는) 현재 메시지 수집을 지원하지 않습니다.")
                
                # 남은 메시지 저장
                if processed_messages:
                    await db_manager.save_messages(processed_messages)
                    
                # 수집 결과 로깅
                if collected_count > 0:
                    logger.info(f"{channel_type_str} 채널 '{channel_name}'({channel.id})에서 {collected_count}개 메시지 수집 완료")
                    
                    # 채널별 마지막 수집 시간 업데이트
                    now = datetime.utcnow()
                    await db_manager.save_collection_metadata(channel_last_collected_key, now.strftime('%Y-%m-%d %H:%M:%S'))
                    logger.debug(f"채널 '{channel_name}'({channel.id}) 마지막 수집 시간을 {now.strftime('%Y-%m-%d %H:%M:%S')}로 업데이트했습니다.")
                else:
                    logger.info(f"{channel_type_str} 채널 '{channel_name}'({channel.id})에서 새로운 메시지가 없습니다.")
                    
                return collected_count
                
            except discord.errors.Forbidden:
                logger.warning(f"채널 '{channel_name}'({channel.id})에 접근할 권한이 없습니다.")
                return 0
            except Exception as e:
                logger.error(f"채널 '{channel_name}'({channel.id}) 메시지 수집 중 오류 발생: {str(e)}")
                return 0
                
        except Exception as e:
            logger.error(f"채널 메시지 수집 중 예상치 못한 오류 발생: {str(e)}")
            return 0
    
    async def collect_guild_messages(self, guild):
        """특정 서버의 메시지를 수집"""
        if self.is_collecting:
            logger.warning(f"⚠️ 이미 메시지 수집 중입니다. 서버 '{guild.name}'({guild.id})의 수집을 건너뜁니다.")
            return 0

        # 서버별 DB 매니저 가져오기
        db_manager = self.bot.get_guild_db_manager(guild.id)
        
        # 서버별 마지막 수집 시간 키
        guild_last_collected_key = f"last_collected_guild_{guild.id}"
        
        try:
            self.is_collecting = True
            logger.info(f"🔍 서버 '{guild.name}'({guild.id})의 메시지 수집 시작...")

            # 텍스트 채널 목록 필터링
            text_channels = [c for c in guild.channels if isinstance(c, discord.TextChannel)]
            logger.info(f"ℹ️ 서버 '{guild.name}'({guild.id})의 텍스트 채널 수: {len(text_channels)}")
            
            # 채널에서 마지막으로 수집한 메시지 ID 가져오기
            last_message_ids = {}
            for channel in text_channels:
                last_msg_id = await db_manager.get_last_message_id(channel.id)
                if last_msg_id:
                    last_message_ids[channel.id] = int(last_msg_id)
            
            # 수집 시작 시간 기록
            collection_start_time = datetime.utcnow()
            total_collected = 0
            
            # 각 채널별로 메시지 수집
            for channel in text_channels:
                try:
                    channel_collected = 0
                    logger.info(f"🔍 채널 '{channel.name}'({channel.id}) 메시지 수집 중...")
                    
                    # 해당 채널의 마지막 메시지 ID 확인
                    last_msg_id = last_message_ids.get(channel.id)
                    if last_msg_id:
                        logger.info(f"ℹ️ 채널 '{channel.name}'의 마지막 메시지 ID: {last_msg_id}")
                        # 마지막 메시지 이후의 새 메시지만 수집
                        async for message in channel.history(limit=None, after=discord.Object(id=last_msg_id)):
                            # 메시지 정보 수집 및 저장
                            await self._save_message(message, db_manager)
                            channel_collected += 1
                    else:
                        # 첫 수집 시에는 최대 1000개 메시지만 수집
                        async for message in channel.history(limit=1000):
                            # 메시지 정보 수집 및 저장
                            await self._save_message(message, db_manager)
                            channel_collected += 1
                    
                    if channel_collected > 0:
                        logger.info(f"✅ 채널 '{channel.name}'에서 {channel_collected}개 메시지 수집 완료")
                    else:
                        logger.info(f"ℹ️ 채널 '{channel.name}'에서 새 메시지 없음")
                    
                    total_collected += channel_collected
                    
                except discord.Forbidden:
                    logger.warning(f"⚠️ 채널 '{channel.name}'({channel.id})에 접근 권한이 없습니다.")
                except Exception as e:
                    logger.error(f"❌ 채널 '{channel.name}'({channel.id}) 메시지 수집 중 오류: {str(e)}")
            
            # 마지막 수집 시간 업데이트 (서버별)
            collection_end_time = datetime.utcnow()
            collection_duration = (collection_end_time - collection_start_time).total_seconds()
            
            # 수집 메타데이터 저장
            await db_manager.save_collection_metadata(guild_last_collected_key, collection_end_time.strftime('%Y-%m-%d %H:%M:%S'))
            
            logger.info(f"✅ 서버 '{guild.name}'({guild.id})의 메시지 수집 완료: {total_collected}개 메시지 (소요 시간: {collection_duration:.2f}초)")
            return total_collected
            
        except Exception as e:
            logger.error(f"❌ 서버 '{guild.name}'({guild.id})의 메시지 수집 중 오류 발생: {str(e)}")
            return 0
        finally:
            self.is_collecting = False
    
    async def collect_all_guilds(self):
        """모든 허용된 서버에서 메시지 수집"""
        if self.is_collecting:
            logger.warning("이미 메시지 수집이 진행 중입니다.")
            return
            
        try:
            self.is_collecting = True
            
            start_time = datetime.now()
            logger.info(f"모든 서버 메시지 수집 시작 (시간: {start_time.strftime('%Y-%m-%d %H:%M:%S')})")
            
            # 마지막 전체 수집 시간 확인
            global_last_collection_time = await self.db_manager.get_last_collection_time()
            if global_last_collection_time:
                logger.info(f"마지막 전체 수집 시간: {global_last_collection_time.strftime('%Y-%m-%d %H:%M:%S')}")
            
            total_collected = 0
            guild_count = 0
            
            # 각 서버마다 메시지 수집
            for guild in self.bot.guilds:
                # 허용된 서버인지 확인
                if self.bot.is_guild_allowed(guild.id):
                    guild_count += 1
                    # 각 서버는 자체 마지막 수집 시간을 사용하므로 global_last_collection_time은 전달하지 않음
                    collected = await self.collect_guild_messages(guild)
                    total_collected += collected
                    
                    # 서버 간 간격을 두어 API 제한 방지
                    await asyncio.sleep(2)
            
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            
            # 저장된 총 메시지 수 확인
            total_messages = 0
            for guild in self.bot.guilds:
                if self.bot.is_guild_allowed(guild.id):
                    # 서버별 DB 매니저에서 메시지 수 확인
                    db_manager = self.bot.get_guild_db_manager(guild.id)
                    guild_messages = await db_manager.get_message_count(guild.id)
                    total_messages += guild_messages
            
            logger.info(
                f"{self.colors['success']}모든 서버 수집 완료: {guild_count}개 서버, {total_collected}개 새 메시지, "
                f"총 {total_messages}개 메시지, 소요 시간: {duration:.2f}초{self.colors['reset']}"
            )
            
            # 마지막 수집 시간 업데이트
            await self.db_manager.save_last_collection_time()
            logger.info(f"전체 마지막 수집 시간이 {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}로 업데이트되었습니다.")
            
        except Exception as e:
            logger.error(f"{self.colors['error']}메시지 수집 중 오류 발생: {str(e)}{self.colors['reset']}")
        finally:
            self.is_collecting = False
    
    async def schedule_collection(self):
        """정기적인 메시지 수집 스케줄링"""
        # 초기 설정 로그
        interval_minutes = self.collection_interval / 60
        logger.info(f"⏱️ 메시지 수집 스케줄러 시작: 수집 간격 {interval_minutes:.1f}분 ({self.collection_interval}초)")
        
        # 허용된 서버 목록 가져오기
        allowed_guilds = []
        for guild in self.bot.guilds:
            if self.bot.is_guild_allowed(guild.id):
                allowed_guilds.append(guild)
        
        # 각 서버에 대해 독립적인 수집 스케줄러 시작
        for guild in allowed_guilds:
            logger.info(f"서버 '{guild.name}'({guild.id})의 수집 스케줄러 설정 중...")
            self.guild_collection_tasks[guild.id] = asyncio.create_task(
                self.schedule_guild_collection(guild)
            )
            
        # 모든 서버의 스케줄러가 완료될 때까지 대기
        while True:
            await asyncio.sleep(60)  # 1분마다 상태 확인
            
            # 비정상 종료된 서버 스케줄러 다시 시작
            for guild in self.bot.guilds:
                if self.bot.is_guild_allowed(guild.id):
                    if guild.id not in self.guild_collection_tasks or self.guild_collection_tasks[guild.id].done():
                        logger.info(f"서버 '{guild.name}'({guild.id})의 수집 스케줄러 재시작 중...")
                        self.guild_collection_tasks[guild.id] = asyncio.create_task(
                            self.schedule_guild_collection(guild)
                        )
    
    async def schedule_guild_collection(self, guild):
        """서버별 메시지 수집 스케줄링"""
        guild_id = guild.id
        guild_name = guild.name
        
        # 서버별 DB 매니저 가져오기
        db_manager = self.bot.get_guild_db_manager(guild_id)
        
        # 서버별 마지막 수집 시간 키
        guild_last_collected_key = f"last_collected_guild_{guild_id}"
        
        # 서버별 메시지 수 확인
        guild_messages = await db_manager.get_message_count(guild_id)
        
        # 마지막 수집 시간 조회 (서버별)
        last_collection_time = await db_manager.get_collection_metadata(guild_last_collected_key)
        if last_collection_time:
            try:
                last_collection_time = datetime.strptime(last_collection_time, '%Y-%m-%d %H:%M:%S')
            except ValueError:
                last_collection_time = None
        
        # 저장된 메시지가 없거나 마지막 수집 시간이 없으면 즉시 수집 시작
        if guild_messages == 0 or not last_collection_time:
            logger.info(f"💡 서버 '{guild_name}'({guild_id})의 저장된 메시지가 없거나 최초 실행입니다 (메시지 수: {guild_messages}). 즉시 수집을 시작합니다...")
            collected = await self.collect_guild_messages(guild)
            logger.info(f"✅ 서버 '{guild_name}'({guild_id})의 첫 번째 수집 완료: {collected}개 메시지")
        elif last_collection_time:
            # 마지막 수집 시간 기준으로 다음 예정 시간 계산
            while True:
                now = datetime.utcnow()
                time_since_last = (now - last_collection_time).total_seconds()
                logger.info(f"ℹ️ 서버 '{guild_name}'({guild_id}) 마지막 수집 시간: {last_collection_time.strftime('%Y-%m-%d %H:%M:%S')} (약 {time_since_last/60:.1f}분 전)")
                
                if time_since_last < self.collection_interval:
                    # 아직 수집 간격이 되지 않았으면 대기
                    wait_time = self.collection_interval - time_since_last
                    next_collection = now + timedelta(seconds=wait_time)
                    logger.info(f"⏳ 서버 '{guild_name}'({guild_id}) 다음 예정 수집 시간: {next_collection.strftime('%Y-%m-%d %H:%M:%S')} (약 {wait_time/60:.1f}분 후)")
                    
                    # 대기 시간이 길면 여러 번 나눠서 대기 (중간에 봇 재시작 등에 대응)
                    if wait_time > 300:  # 5분 이상이면
                        await asyncio.sleep(300)  # 5분 대기
                    else:
                        await asyncio.sleep(wait_time)
                else:
                    # 수집 간격이 지났으면 수집 시작
                    logger.info(f"🔄 서버 '{guild_name}'({guild_id}) 마지막 수집 후 {time_since_last/60:.1f}분이 지났습니다. 수집을 시작합니다.")
                    collected = await self.collect_guild_messages(guild)
                    logger.info(f"✅ 서버 '{guild_name}'({guild_id}) 수집 완료: {collected}개 메시지")
                    
                    # 마지막 수집 시간 업데이트
                    last_collection_time = datetime.utcnow()
                    
                    # 1분 대기 후 다음 주기 시작
                    await asyncio.sleep(60)
    
    def start_collection_scheduler(self):
        """메시지 수집 스케줄러 시작"""
        self.collection_task = asyncio.create_task(self.schedule_collection())
        logger.info("🚀 메시지 수집 스케줄러가 시작되었습니다.")
        return self.collection_task
    
    async def _save_message(self, message, db_manager):
        """단일 메시지를 처리하여 DB에 저장
        
        Args:
            message: Discord 메시지 객체
            db_manager: 사용할 데이터베이스 매니저
            
        Returns:
            성공 여부 (True/False)
        """
        try:
            # 메시지를 딕셔너리로 변환
            message_dict = self.message_to_dict(message)
            
            # 메시지가 유효하면 저장
            if message_dict:
                await db_manager.save_messages([message_dict])
                return True
            return False
        except Exception as e:
            logger.error(f"메시지 저장 중 오류 발생: {str(e)}")
            return False 