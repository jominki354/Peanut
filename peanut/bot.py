import discord
import asyncio
import logging
from discord.ext import commands
from discord import app_commands
import aiohttp
from pathlib import Path
from datetime import datetime

from .utils.config import get_config
from .utils.logger import setup_logger
from .utils.collector import MessageCollector
from .db.database import get_db_manager
from .utils.llm import get_llm_manager

# 로거 설정
logger = setup_logger()

class PeanutBot(commands.Bot):
    """채팅 데이터 수집 봇 클래스"""
    
    def __init__(self):
        # 봇 설정 로드
        self.config = get_config()
        
        # 허용된 서버 ID 목록 설정
        allowed_guild_ids_str = self.config.get('ALLOWED_GUILD_IDS', '')
        self.allowed_guild_ids = set()
        if allowed_guild_ids_str:
            try:
                self.allowed_guild_ids = {int(guild_id.strip()) for guild_id in allowed_guild_ids_str.split(',') if guild_id.strip()}
                logger.info(f"허용된 서버 ID 목록: {self.allowed_guild_ids}")
            except ValueError as e:
                logger.error(f"ALLOWED_GUILD_IDS 파싱 중 오류 발생: {str(e)}")
        
        # 봇 인텐트 설정 (메시지 내용, 멤버 정보 등에 대한 접근 권한)
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        
        # 봇 초기화
        super().__init__(command_prefix='!', intents=intents)
        
        # 데이터베이스 매니저 초기화 - 기본 데이터베이스 사용
        self.db_manager = get_db_manager()
        
        # 각 서버별 데이터베이스 매니저 저장할 딕셔너리
        self.guild_db_managers = {}
        
        # 메시지 수집기 초기화
        self.collector = MessageCollector(self)
        
        # 이벤트 핸들러 등록
        self.setup_events()

    async def setup_cogs(self):
        """봇 cog 로드 함수"""
        try:
            # cogs 디렉토리 확인
            cog_path = Path(__file__).parent / "cogs"
            logger.info(f"Cog 디렉토리 경로: {cog_path} (존재 여부: {cog_path.exists()})")
            
            # 이용 가능한 cog 파일 리스트
            available_cogs = list(cog_path.glob("*.py"))
            logger.info(f"발견된 Cog 파일: {[cog.name for cog in available_cogs]}")
            
            # QA cog 로드 시도
            try:
                # 직접 cog 클래스 임포트 및 추가 시도
                from .cogs.qa import QACog
                await self.add_cog(QACog(self))
                logger.info("QA Cog를 성공적으로 로드했습니다.")
            except ImportError:
                logger.error("QA Cog를 임포트할 수 없습니다. 파일이 없거나 경로가 잘못되었습니다.")
                # 대체 방법으로 확장 로드 시도
                try:
                    await self.load_extension("peanut.cogs.qa")
                    logger.info("확장 방식으로 QA Cog를 성공적으로 로드했습니다.")
                except Exception as load_error:
                    logger.error(f"확장 방식으로도 QA Cog 로드 실패: {str(load_error)}")
                    # 질문 명령어를 직접 등록
                    self.create_direct_question_command()
            except Exception as qa_error:
                logger.error(f"QA Cog 로드 중 오류 발생: {str(qa_error)}", exc_info=True)
                # 질문 명령어를 직접 등록
                self.create_direct_question_command()
            
            # 추가적인 cog도 여기에 로드할 수 있음
        except Exception as e:
            logger.error(f"Cog 로드 중 오류 발생: {str(e)}", exc_info=True)
            logger.warning("일부 기능이 비활성화될 수 있습니다.")
            # 필수 명령어 직접 등록
            self.create_direct_question_command()
    
    def create_direct_question_command(self):
        """Cog 로딩에 실패했을 때 질문 명령어를 직접 등록"""
        @self.tree.command(name="질문", description="수집된 데이터를 기반으로 질문에 답변합니다")
        async def question_command(interaction: discord.Interaction, 질문: str):
            try:
                await interaction.response.defer(thinking=True, ephemeral=False)
            except discord.errors.NotFound:
                logger.warning(f"사용자 {interaction.user}의 상호작용이 만료되었습니다. 응답을 보낼 수 없습니다.")
                return
            except Exception as e:
                logger.error(f"defer 중 예상치 못한 오류 발생: {str(e)}")
                return
            
            try:
                logger.info(f"사용자 {interaction.user}의 질문: {질문}")
                
                # LLM 매니저 가져오기 - 서버별 DB 사용
                guild_id = interaction.guild.id if interaction.guild else None
                llm_manager = get_llm_manager(guild_id=guild_id)
                
                # 질문과 관련된 서버 내 메시지 검색
                relevant_messages = await llm_manager.find_relevant_messages(질문, limit=30)
                
                if not relevant_messages:
                    logger.warning("질문과 관련된 메시지를 찾을 수 없습니다. 최근 메시지를 사용합니다.")
                    relevant_messages = await llm_manager.get_recent_messages(limit=20)
                
                # 메시지를 딕셔너리 형태로 변환
                context_messages = []
                
                for msg in relevant_messages:
                    context_messages.append({
                        'id': msg.id,
                        'channel_id': msg.channel_id,
                        'author_id': msg.author_id,
                        'author_name': msg.author_name,
                        'content': msg.content,
                        'created_at': msg.created_at.isoformat() if msg.created_at else None,
                        'channel_name': msg.channel_name
                    })
                
                # 사용자에게 알릴 정보: 찾은 메시지 수와 키워드
                keywords = llm_manager.extract_keywords(질문)
                keyword_info = f"검색 키워드: {', '.join(keywords[:5])}" if keywords else "키워드 없음"
                logger.info(f"컨텍스트로 {len(context_messages)}개의 메시지를 사용합니다. {keyword_info}")
                
                # 찾은 메시지 ID 로깅
                if context_messages:
                    message_ids = [msg.get('id') for msg in context_messages if msg.get('id')]
                    logger.info(f"참조된 메시지 ID: {', '.join(message_ids[:5])}{'...' if len(message_ids) > 5 else ''}")
                
                # 질문에 추가 지시사항 포함
                enhanced_query = f"""질문: {질문}

참고: 이 질문에 관련된 정보가 있습니다. 답변할 때 출처나 작성자 정보는 포함하지 마세요. 어떤 형태의 참조 정보나 출처 표시도 하지 마세요."""
                
                # 컨텍스트가 없는 경우 다른 안내 메시지 사용
                if not context_messages:
                    enhanced_query = f"""질문: {질문}

참고: 이 질문에 관련된 정보가 충분히 없습니다. 질문에 관련된 내용이 데이터베이스에 없을 수 있습니다. 
가능한 한 답변해주되, 명확한 정보가 없으면 솔직하게 정보가 부족하다고 답변해주세요."""
                
                # 비동기 메소드 지원 여부 확인
                if asyncio.iscoroutinefunction(llm_manager.generate_response):
                    response_data = await llm_manager.generate_response(enhanced_query, context_messages=context_messages)
                else:
                    response_data = llm_manager.generate_response(enhanced_query, context_messages=context_messages)
                    
                # 예전 반환 형식 호환성: 문자열 반환 또는 딕셔너리에서 응답 추출
                response = response_data['response'] if isinstance(response_data, dict) else response_data
                
                # 관련성 정보 확인
                has_relevant_context = response_data.get('has_relevant_context', False) if isinstance(response_data, dict) else False
                
                # 메시지 링크 생성
                reference_count = len(context_messages) if context_messages else 0
                message_links_text = ""
                
                # 관련성 있는 메시지가 있는 경우에만 링크 표시
                if has_relevant_context and context_messages and reference_count > 0:
                    # 응답 텍스트에 "관련 정보를 찾을 수 없습니다"라는 메시지가 포함되어 있는지 확인
                    no_info_phrases = [
                        "관련 정보를 찾을 수 없", "관련된 정보가 없", "관련 정보가 없",
                        "질문하신 내용에 대한 정보가 없", "해당 내용에 대한 정보가 없",
                        "데이터베이스에서 찾을 수 없", "관련 내용이 없", "정보가 부족"
                    ]
                    contains_no_info = any(phrase in response for phrase in no_info_phrases)
                    
                    # 주요 키워드가 있는지 확인
                    keywords = llm_manager.extract_keywords(질문)
                    main_keyword = keywords[0] if keywords else None
                    
                    # 관련 정보가 없다는 응답인 경우 링크를 표시하지 않음
                    if not contains_no_info:
                        # 모든 메시지를 순회하여 관련성 점수 계산
                        scored_messages = []
                        for idx, msg in enumerate(context_messages):
                            content = msg.get('content', '').lower()
                            score = 0
                            
                            # 주요 키워드가 포함된 메시지에 높은 점수 부여
                            if main_keyword and main_keyword.lower() in content:
                                score += 10
                            
                            # 다른 키워드도 확인
                            for kw in keywords[1:3]:  # 상위 3개 키워드 검사
                                if kw.lower() in content:
                                    score += 5
                            
                            # 메시지가 충분히 길고 의미있는 내용인 경우 추가 점수
                            if len(content) > 50:
                                score += 2
                            
                            # 일정 점수 이상인 메시지만 후보에 포함
                            if score >= 5:
                                scored_messages.append((idx, msg, score))
                        
                        # 점수 기준으로 정렬
                        scored_messages.sort(key=lambda x: x[2], reverse=True)
                        
                        # 표시할 메시지 선택 (점수 기준 완화 - 5점 이상, 최대 3개)
                        display_messages = []
                        for msg_data in scored_messages:
                            if msg_data[2] >= 5:  # 점수 5점 이상인 메시지 포함
                                display_messages.append(msg_data)
                                if len(display_messages) >= 3:  # 최대 3개까지만 표시
                                    break
                        
                        # 표시할 메시지가 있는 경우에만 링크 생성
                        if display_messages:
                            links = []
                            
                            # 숫자 이모티콘 리스트 (참조 링크용)
                            number_emojis = ["1️⃣", "2️⃣", "3️⃣"]
                            
                            for i, (orig_idx, msg, score) in enumerate(display_messages):
                                # 메시지 ID와 채널 ID 추출
                                msg_id = msg.get('id')
                                channel_id = msg.get('channel_id')
                                
                                if msg_id and channel_id and interaction.guild:
                                    # 숫자 이모티콘을 사용한 클릭 가능한 링크 생성
                                    link_url = f"https://discord.com/channels/{interaction.guild.id}/{channel_id}/{msg_id}"
                                    number_emoji = number_emojis[i % len(number_emojis)]
                                    links.append(f"[{number_emoji}]({link_url})")
                                    logger.info(f"참조 메시지 {i+1}: 점수 {score}, ID {msg_id}")
                            
                            if links:
                                # 쉼표와 공백으로 링크 사이에 여백 추가
                                message_links_text = f"\n\n**참조한 메시지**: {',  '.join(links)}"
                                logger.info(f"총 {len(links)}개의 참조 링크를 표시합니다.")
                        else:
                            logger.info("표시할 만큼 관련성 높은 메시지가 없어 참조 링크를 표시하지 않습니다.")
                
                # 응답에 링크 정보 추가
                full_response = response + message_links_text
                
                # 응답 전송
                embed = discord.Embed(
                    title=f"질문: {질문[:50]}{'...' if len(질문) > 50 else ''}",
                    description=full_response,
                    color=discord.Color.blue()
                )
                
                # 푸터에 참조 정보 추가 (관련성 정보 포함)
                footer_text = f"요청자: {interaction.user}"
                
                # 응답 텍스트에 "관련 정보를 찾을 수 없습니다"라는 메시지가 포함되어 있는지 확인
                no_info_phrases = ["관련 정보를 찾을 수 없", "관련된 정보가 없", "관련 정보가 없"]
                contains_no_info = any(phrase in response for phrase in no_info_phrases)
                
                # 푸터 정보 설정 (응답 내용과 일관되게)
                if has_relevant_context and reference_count > 0 and not contains_no_info and display_messages:
                    footer_text += " (참조 정보 있음)"
                else:
                    footer_text += " (관련 정보 없음)"
                
                embed.set_footer(text=footer_text)
                
                try:
                    await interaction.followup.send(embed=embed)
                    logger.info(f"사용자 {interaction.user}의 질문에 응답을 보냈습니다.")
                except discord.errors.NotFound:
                    logger.warning(f"사용자 {interaction.user}의 상호작용이 만료되었습니다. 응답을 보낼 수 없습니다.")
                except Exception as e:
                    logger.error(f"응답 전송 중 오류 발생: {str(e)}")
                
            except Exception as e:
                logger.error(f"질문 응답 중 오류 발생: {str(e)}", exc_info=True)
                try:
                    await interaction.followup.send(f"죄송합니다. 질문을 처리하는 중 오류가 발생했습니다: {str(e)}")
                except discord.errors.NotFound:
                    logger.warning(f"사용자 {interaction.user}의 상호작용이 만료되었습니다. 오류 응답을 보낼 수 없습니다.")
                except Exception as follow_error:
                    logger.error(f"오류 응답 전송 중 추가 오류 발생: {str(follow_error)}")
        
        logger.info("질문 명령어를 직접 등록했습니다.")
    
    async def clear_all_commands(self):
        """기존 명령어 초기화"""
        logger.info("기존 명령어를 초기화하고 있습니다...")
        
        try:
            # 허용된 서버의 명령어 초기화
            if self.allowed_guild_ids:
                for guild_id in self.allowed_guild_ids:
                    try:
                        guild = self.get_guild(int(guild_id))
                        if guild:
                            # 서버 명령어 초기화 (API 직접 호출)
                            await self.http.bulk_upsert_guild_commands(self.user.id, guild.id, [])
                            logger.info(f"서버 '{guild.name}'의 모든 명령어를 초기화했습니다.")
                        else:
                            logger.warning(f"서버 ID {guild_id}를 찾을 수 없습니다.")
                    except Exception as e:
                        logger.error(f"서버 {guild_id} 명령어 초기화 오류: {str(e)}")
            
            # 전역 명령어 초기화
            await self.http.bulk_upsert_global_commands(self.user.id, [])
            logger.info("전역 명령어를 초기화했습니다.")
            
        except Exception as e:
            logger.error(f"명령어 초기화 중 오류 발생: {str(e)}", exc_info=True)
    
    async def register_commands(self):
        """슬래시 명령어를 등록"""
        try:
            logger.info("슬래시 명령어 등록 시작...")
            
            # 허용된 서버의 명령어 동기화
            if self.allowed_guild_ids:
                for guild_id in self.allowed_guild_ids:
                    try:
                        guild = self.get_guild(int(guild_id))
                        if guild:
                            # 이미 명령어가 등록되어 있는지 확인
                            existing_commands = await self.tree.fetch_commands(guild=guild)
                            
                            # 필요한 명령어 목록 (필요에 따라 확장 가능)
                            needed_commands = {"질문"}
                            existing_command_names = {cmd.name for cmd in existing_commands}
                            
                            # 현재 상태 로깅
                            if existing_commands:
                                logger.info(f"서버 '{guild.name}'에 이미 {len(existing_commands)}개의 명령어가 등록되어 있습니다: {', '.join(existing_command_names)}")
                            
                            # 명령어 동기화가 필요한지 확인
                            if needed_commands.issubset(existing_command_names):
                                logger.info(f"서버 '{guild.name}'에 필요한 모든 명령어가 이미 등록되어 있습니다. 동기화를 건너뜁니다.")
                                continue  # 필요한 모든 명령어가 있으면 건너뛰기
                            
                            # 명령어 변경이 필요한 경우에만 동기화 수행
                            logger.info(f"서버 '{guild.name}'에 필요한 명령어가 누락되어 있어 동기화를 수행합니다.")
                            synced = await self.tree.sync(guild=guild)
                            logger.info(f"서버 '{guild.name}'에 {len(synced)}개의 슬래시 명령어를 동기화했습니다: {', '.join(cmd.name for cmd in synced)}")
                        else:
                            logger.warning(f"서버 ID {guild_id}를 찾을 수 없습니다.")
                    except Exception as e:
                        logger.error(f"서버 {guild_id} 명령어 동기화 오류: {str(e)}")
            
            # 글로벌 명령어 확인 및 동기화
            try:
                # 현재 글로벌 명령어 확인
                existing_global_commands = await self.tree.fetch_commands()
                
                if existing_global_commands:
                    logger.info(f"전역에 이미 {len(existing_global_commands)}개의 명령어가 등록되어 있습니다: {', '.join(cmd.name for cmd in existing_global_commands)}")
                    # 글로벌 명령어가 있으면 동기화 건너뛰기
                    return
                
                # 글로벌 명령어가 없는 경우에만 동기화
                logger.info("전역 명령어가 없어 동기화를 수행합니다.")
                global_commands = await self.tree.sync()
                logger.info(f"전역 명령어 {len(global_commands)}개를 동기화했습니다: {', '.join(cmd.name for cmd in global_commands)}")
            except Exception as e:
                logger.error(f"전역 명령어 동기화 오류: {str(e)}")
            
            logger.info("명령어 등록 프로세스가 완료되었습니다.")
        
        except Exception as e:
            logger.error(f"슬래시 명령어 등록 중 오류 발생: {str(e)}", exc_info=True)
    
    def is_guild_allowed(self, guild_id):
        """서버 ID가 허용 목록에 있는지 확인"""
        # 허용 목록이 비어있으면 모든 서버가 허용되지 않음
        if not self.allowed_guild_ids:
            logger.info(f"허용된 서버 목록이 비어 있습니다. 서버 ID {guild_id}가 허용되지 않습니다.")
            return False
        
        # 입력된 ID가 정수가 아니면 정수로 변환 시도
        try:
            guild_id_int = int(guild_id)
        except (ValueError, TypeError):
            logger.error(f"서버 ID {guild_id}를 정수로 변환할 수 없습니다.")
            return False
            
        # 허용 목록에 있는 서버만 허용
        is_allowed = guild_id_int in self.allowed_guild_ids
        logger.info(f"서버 ID {guild_id} (타입: {type(guild_id).__name__})가 허용 목록에 있는지 확인: {is_allowed}")
        logger.info(f"현재 허용된 서버 목록: {self.allowed_guild_ids} (타입: {type(next(iter(self.allowed_guild_ids))).__name__ if self.allowed_guild_ids else 'empty'})")
        return is_allowed
    
    def get_guild_db_manager(self, guild_id):
        """서버별 데이터베이스 매니저 가져오기
        
        Args:
            guild_id: 서버 ID
            
        Returns:
            서버 전용 DatabaseManager 인스턴스
        """
        # 캐시에 없으면 생성
        if guild_id not in self.guild_db_managers:
            from .db.database import get_db_manager
            self.guild_db_managers[guild_id] = get_db_manager(guild_id=guild_id)
            
        return self.guild_db_managers[guild_id]
    
    def setup_events(self):
        """봇 이벤트 핸들러 설정"""
        @self.event
        async def on_ready():
            """봇이 준비되었을 때 호출되는 이벤트"""
            logger.info(f"{self.user.name}({self.user.id})로 로그인했습니다.")
            
            # 봇 자신의 메시지 삭제
            bot_ids = self.config.get('BOT_ID', '')
            if bot_ids:
                logger.info(f"봇 ID 목록: {bot_ids}에 해당하는 메시지를 데이터베이스에서 삭제합니다...")
                try:
                    # 쉼표로 구분된 봇 ID 목록 처리
                    bot_id_list = [bid.strip() for bid in bot_ids.split(',') if bid.strip()]
                    total_deleted = 0
                    
                    for bot_id in bot_id_list:
                        deleted_count = await self.db_manager.delete_bot_messages(bot_id)
                        if deleted_count > 0:
                            total_deleted += deleted_count
                            logger.info(f"봇 ID {bot_id}의 메시지 {deleted_count}개를 데이터베이스에서 삭제했습니다.")
                    
                    if total_deleted > 0:
                        logger.info(f"총 {total_deleted}개의 봇 메시지를 데이터베이스에서 삭제했습니다.")
                    else:
                        logger.info("데이터베이스에 봇의 메시지가 없거나 삭제 과정에서 오류가 발생했습니다.")
                except Exception as e:
                    logger.error(f"봇 메시지 삭제 중 오류 발생: {str(e)}")
            
            # 참여 중인 서버 정보 출력
            allowed_guilds = 0
            not_allowed_guilds = 0
            
            for guild in self.guilds:
                if self.is_guild_allowed(guild.id):
                    allowed_guilds += 1
                    logger.info(f"허용된 서버에 참여 중: {guild.name}({guild.id})")
                else:
                    not_allowed_guilds += 1
                    logger.info(f"허용되지 않은 서버에 참여 중 (데이터 수집 안함): {guild.name}({guild.id})")
            
            logger.info(f"봇이 {allowed_guilds}개의 허용된 서버와 {not_allowed_guilds}개의 허용되지 않은 서버에 참여중입니다.")
            
            # Cog 설정
            await self.setup_cogs()
            
            # 봇 상태 설정
            await self.change_presence(activity=discord.Activity(
                type=discord.ActivityType.watching, 
                name="서버 채팅 수집중"
            ))
            
            # 단순화된 명령어 초기화 및 등록 프로세스
            try:
                # 명령어 등록 상태 체크를 위한 설정 파일 경로
                commands_status_file = Path("commands_registered.txt")
                
                # 이미 명령어가 성공적으로 등록되었는지 확인
                if commands_status_file.exists():
                    logger.info("명령어가 이미 등록되어 있습니다. 명령어 초기화 및 재등록 과정을 건너뜁니다.")
                else:
                    # 각 서버별로 명령어 등록 상태 확인
                    commands_missing = False
                    for guild_id in self.allowed_guild_ids:
                        guild = self.get_guild(int(guild_id))
                        if guild:
                            try:
                                existing_commands = await self.tree.fetch_commands(guild=guild)
                                needed_commands = {"질문"}
                                existing_command_names = {cmd.name for cmd in existing_commands}
                                
                                if not needed_commands.issubset(existing_command_names):
                                    commands_missing = True
                                    logger.info(f"서버 '{guild.name}'에 필요한 명령어가 등록되어 있지 않습니다.")
                                    break
                            except Exception as e:
                                logger.error(f"서버 '{guild.name}'의 명령어 확인 중 오류: {str(e)}")
                                commands_missing = True
                                break
                    
                    # 명령어가 없는 경우에만 등록 과정 수행
                    if commands_missing:
                        logger.info("일부 서버에 필요한 명령어가 없습니다. 명령어를 등록합니다...")
                        
                        # 새 명령어 등록 (초기화 없이)
                        await self.register_commands()
                        logger.info("명령어 등록이 완료되었습니다.")
                        
                        # 등록 완료 표시
                        with open(commands_status_file, "w") as f:
                            f.write(f"Commands registered successfully at {datetime.now().isoformat()}")
                    else:
                        logger.info("모든 서버에 필요한 명령어가 이미 등록되어 있습니다.")
                        # 등록 완료 표시 (기존에 없었을 경우)
                        if not commands_status_file.exists():
                            with open(commands_status_file, "w") as f:
                                f.write(f"Commands verified successfully at {datetime.now().isoformat()}")
            except Exception as e:
                logger.error(f"명령어 등록 상태 확인 중 오류 발생: {str(e)}", exc_info=True)
            
            # 수집 스케줄러 시작
            self.collector.start_collection_scheduler()
            logger.info("메시지 수집 스케줄러가 시작되었습니다.")
        
        @self.event
        async def on_guild_join(guild):
            """봇이 새로운 서버에 참여했을 때 호출되는 이벤트"""
            if self.is_guild_allowed(guild.id):
                logger.info(f"새로운 허용된 서버에 참여했습니다: {guild.name}({guild.id})")
                # 새 서버에도 명령어 등록 (필요한 경우에만)
                try:
                    # 이미 명령어가 등록되어 있는지 확인
                    existing_commands = await self.tree.fetch_commands(guild=guild)
                    needed_commands = {"질문"}
                    existing_command_names = {cmd.name for cmd in existing_commands}
                    
                    # 현재 상태 로깅
                    if existing_commands:
                        logger.info(f"서버 '{guild.name}'에 이미 {len(existing_commands)}개의 명령어가 등록되어 있습니다: {', '.join(existing_command_names)}")
                    
                    # 명령어 등록이 필요한지 확인
                    if needed_commands.issubset(existing_command_names):
                        logger.info(f"서버 '{guild.name}'에 필요한 모든 명령어가 이미 등록되어 있습니다. 동기화를 건너뜁니다.")
                    else:
                        # 명령어 변경이 필요한 경우에만 동기화 수행
                        logger.info(f"서버 '{guild.name}'에 필요한 명령어가 누락되어 있어 동기화를 수행합니다.")
                        synced = await self.tree.sync(guild=guild)
                        logger.info(f"서버 '{guild.name}'에 {len(synced)}개의 슬래시 명령어를 동기화했습니다: {', '.join(cmd.name for cmd in synced)}")
                except discord.errors.HTTPException as e:
                    logger.error(f"서버 '{guild.name}'에 명령어 동기화 중 HTTP 오류: {e}")
            else:
                logger.info(f"허용되지 않은 서버에 참여했습니다 (데이터 수집 안함): {guild.name}({guild.id})")
        
        @self.event
        async def on_message(message):
            """새로운 메시지가 생성되었을 때 호출되는 이벤트"""
            # 허용된 서버의 메시지만 처리
            if message.guild and self.is_guild_allowed(message.guild.id):
                # 명령어 처리
                await self.process_commands(message)
    
    async def on_error(self, event, *args, **kwargs):
        """봇 오류 처리"""
        logger.error(f"이벤트 {event} 처리 중 오류 발생:", exc_info=True)
    
    def run(self):
        """봇 실행"""
        # 토큰 검증
        if not self.config.get('DISCORD_TOKEN'):
            logger.error("DISCORD_TOKEN이 설정되지 않았습니다. .env 파일을 확인하세요.")
            return
        
        try:
            logger.info("봇을 시작합니다...")
            super().run(self.config.get('DISCORD_TOKEN'))
        except discord.errors.LoginFailure:
            logger.error("봇 로그인에 실패했습니다. 토큰이 유효한지 확인하세요.")
        except Exception as e:
            logger.error(f"봇 실행 중 오류 발생: {str(e)}", exc_info=True) 