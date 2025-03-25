import discord
import asyncio
import logging
from discord.ext import commands
from discord import app_commands
import aiohttp
from pathlib import Path

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
        try:
            @self.tree.command(name="질문", description="수집된 데이터를 기반으로 질문에 답변합니다")
            async def question_command(interaction: discord.Interaction, 질문: str):
                """질문에 답변하는 명령어"""
                try:
                    await interaction.response.defer(thinking=True)
                except discord.errors.NotFound:
                    # 상호작용이 이미 만료된 경우 조용히 실패
                    logger.warning(f"사용자 {interaction.user}의 상호작용이 만료되었습니다. 응답을 보낼 수 없습니다.")
                    return
                except Exception as e:
                    # 기타 오류 처리
                    logger.error(f"defer 중 예상치 못한 오류 발생: {str(e)}")
                    return
                
                try:
                    logger.info(f"사용자 {interaction.user}의 질문: {질문}")
                    
                    # LLM 매니저 가져오기
                    llm_manager = get_llm_manager()
                    
                    # 응답 생성 (비동기 또는 동기 메서드에 따라 처리)
                    if hasattr(llm_manager, 'generate_response'):
                        # 질문에 추가 지시사항 포함
                        enhanced_query = f"""질문: {질문}
                        
참고: 답변할 때 출처나 작성자 정보는 포함하지 마세요. 어떤 형태의 참조 정보나 출처 표시도 하지 마세요."""
                        
                        # 비동기 메소드 지원 여부 확인
                        if asyncio.iscoroutinefunction(llm_manager.generate_response):
                            response_data = await llm_manager.generate_response(enhanced_query)
                        else:
                            response_data = llm_manager.generate_response(enhanced_query)
                            
                        # 예전 반환 형식 호환성: 문자열 반환 또는 딕셔너리에서 응답 추출
                        response = response_data['response'] if isinstance(response_data, dict) else response_data
                    else:
                        logger.error("llm_manager에 generate_response 메서드가 없습니다.")
                        response = "질문 처리 중 오류가 발생했습니다. LLM 모듈이 올바르게 초기화되지 않았습니다."
                    
                    # 응답 전송 (참조 정보 없음)
                    embed = discord.Embed(
                        title=f"질문: {질문[:50]}{'...' if len(질문) > 50 else ''}",
                        description=response,
                        color=discord.Color.blue()
                    )
                    
                    # 푸터에 참조 정보 추가 
                    # 직접 호출에서는 context_messages가 직접 접근 불가능하므로
                    # 단순히 참조한 메시지 수만 표시 (0개로 표시)
                    embed.set_footer(text=f"요청자: {interaction.user} (참조한 메시지: 0개)")
                    
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
        except Exception as e:
            logger.error(f"질문 명령어 직접 등록 중 오류 발생: {str(e)}", exc_info=True)
    
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
            
            # Cog에서 등록된 명령어 동기화
            if self.allowed_guild_ids:
                for guild_id in self.allowed_guild_ids:
                    try:
                        guild = self.get_guild(int(guild_id))
                        if guild:
                            # 서버별 명령어 동기화
                            synced = await self.tree.sync(guild=guild)
                            logger.info(f"서버 '{guild.name}'에 {len(synced)}개의 슬래시 명령어를 동기화했습니다.")
                            for cmd in synced:
                                logger.info(f"서버 '{guild.name}'에 등록된 명령어: {cmd.name}")
                        else:
                            logger.warning(f"서버 ID {guild_id}를 찾을 수 없습니다.")
                    except Exception as e:
                        logger.error(f"서버 {guild_id} 명령어 동기화 오류: {str(e)}")
            
            # 글로벌 명령어도 동기화
            global_commands = await self.tree.sync()
            logger.info(f"글로벌 명령어 {len(global_commands)}개를 동기화했습니다.")
            for cmd in global_commands:
                logger.info(f"글로벌에 등록된 명령어: {cmd.name}")
            
            logger.info("명령어 등록 프로세스가 완료되었습니다.")
        
        except Exception as e:
            logger.error(f"슬래시 명령어 등록 중 오류 발생: {str(e)}", exc_info=True)
    
    def is_guild_allowed(self, guild_id):
        """서버 ID가 허용 목록에 있는지 확인"""
        # 허용 목록이 비어있으면 모든 서버 허용
        if not self.allowed_guild_ids:
            return True
        
        # 허용 목록에 있는 서버만 허용
        return int(guild_id) in self.allowed_guild_ids
    
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
            bot_id = str(self.user.id)
            logger.info(f"봇 ID {bot_id}에 해당하는 메시지를 데이터베이스에서 삭제합니다...")
            try:
                deleted_count = await self.db_manager.delete_bot_messages(bot_id)
                if deleted_count > 0:
                    logger.info(f"봇 자신의 메시지 {deleted_count}개를 데이터베이스에서 삭제했습니다.")
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
                # 명령어 초기화는 필요한 경우만 사용 (지금은 넘어갑니다)
                # await self.clear_all_commands()
                # logger.info("명령어 초기화가 완료되었습니다.")
                
                # 대기 시간 추가
                await asyncio.sleep(1)
                
                # 새 명령어 등록
                await self.register_commands()
                logger.info("명령어 등록이 완료되었습니다.")
            except Exception as e:
                logger.error(f"명령어 초기화/등록 중 오류 발생: {str(e)}", exc_info=True)
            
            # 수집 스케줄러 시작
            self.collector.start_collection_scheduler()
            logger.info("메시지 수집 스케줄러가 시작되었습니다.")
        
        @self.event
        async def on_guild_join(guild):
            """봇이 새로운 서버에 참여했을 때 호출되는 이벤트"""
            if self.is_guild_allowed(guild.id):
                logger.info(f"새로운 허용된 서버에 참여했습니다: {guild.name}({guild.id})")
                # 새 서버에도 명령어 등록
                try:
                    synced = await self.tree.sync(guild=guild)
                    logger.info(f"서버 '{guild.name}'에 {len(synced)}개의 슬래시 명령어를 동기화했습니다.")
                    for cmd in synced:
                        logger.info(f"서버 '{guild.name}'에 등록된 명령어: {cmd.name}")
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