import discord
import logging
import sys
from discord import app_commands
from discord.ext import commands

from ..utils.llm import get_llm_manager

# 로깅 설정
logger = logging.getLogger('discord.qa')

class QACog(commands.Cog):
    """질문 응답 기능을 제공하는 Cog"""
    
    def __init__(self, bot):
        self.bot = bot
        self.llm_manager = get_llm_manager()
        logger.info("QA Cog가 초기화되었습니다.")
    
    @app_commands.command(name="질문", description="당근파일럿 서버의 채팅데이터를 기반으로 질문에 답변합니다")
    @app_commands.describe(질문="궁금한 내용을 질문해주세요")
    async def ask_question(self, interaction: discord.Interaction, 질문: str):
        """질문에 대한 답변을 생성하는 슬래시 명령어
        
        Args:
            interaction: 디스코드 상호작용 객체
            질문: 사용자 질문
        """
        try:
            await interaction.response.defer(thinking=True, ephemeral=False)
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
            
            # 질문과 관련된 서버 내 메시지 검색
            relevant_messages = await self.llm_manager.find_relevant_messages(질문, limit=30)
            
            if not relevant_messages:
                logger.warning("질문과 관련된 메시지를 찾을 수 없습니다. 최근 메시지를 사용합니다.")
                relevant_messages = await self.llm_manager.get_recent_messages(limit=20)
            
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
            keywords = self.llm_manager.extract_keywords(질문)
            keyword_info = f"검색 키워드: {', '.join(keywords[:5])}" if keywords else "키워드 없음"
            logger.info(f"컨텍스트로 {len(context_messages)}개의 메시지를 사용합니다. {keyword_info}")
            
            # 사용자 질문에 찾은 컨텍스트 정보 추가
            enhanced_query = f"""질문: {질문}

참고: 이 질문에 관련된 정보가 있습니다. 답변할 때 출처나 작성자 정보는 포함하지 마세요. 어떤 형태의 참조 정보나 출처 표시도 하지 마세요."""
            
            # 비동기 메서드로 변경된 generate_response 호출 (컨텍스트 메시지 포함)
            response_data = await self.llm_manager.generate_response(enhanced_query, context_messages=context_messages)
            
            # 응답이 딕셔너리인 경우 'response' 키에서 텍스트 추출, 아니면 그대로 사용
            response = response_data['response'] if isinstance(response_data, dict) else response_data
            
            # 메시지 링크 생성
            reference_count = len(context_messages) if context_messages else 0
            message_links_text = ""
            
            if context_messages and reference_count > 0:
                displayed_count = min(3, reference_count)  # 최대 3개까지만 표시
                links = []
                
                # 숫자 이모티콘 리스트 (참조 링크용)
                number_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]
                
                for i in range(displayed_count):
                    if i < len(context_messages):
                        msg = context_messages[i]
                        # 메시지 ID와 채널 ID 추출
                        msg_id = msg.get('id')
                        channel_id = msg.get('channel_id')
                        
                        if msg_id and channel_id and interaction.guild:
                            # 숫자 이모티콘을 사용한 클릭 가능한 링크 생성
                            link_url = f"https://discord.com/channels/{interaction.guild.id}/{channel_id}/{msg_id}"
                            # 숫자 이모티콘 선택
                            number_emoji = number_emojis[i % len(number_emojis)]
                            links.append(f"[{number_emoji}]({link_url})")
                
                if links:
                    # 쉼표와 공백으로 링크 사이에 여백 추가
                    message_links_text = f"\n\n**참조한 메시지**: {',  '.join(links)}"
            
            # 응답에 링크 정보 추가
            full_response = response + message_links_text
            
            # 응답 전송 (참조 정보 없음)
            embed = discord.Embed(
                title=f"질문: {질문[:50]}{'...' if len(질문) > 50 else ''}",
                description=full_response,
                color=discord.Color.blue()
            )
            
            # 푸터에는 요청자 정보만 표시
            embed.set_footer(text=f"요청자: {interaction.user} (참조한 메시지: {reference_count}개)")
            
            # 답변 전송 (예외 처리 추가)
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

async def setup(bot):
    """Cog 설정 함수"""
    # 봇이 시작될 때 LLM API 연결 테스트
    llm_manager = get_llm_manager()
    try:
        await llm_manager.initialize_models()
        logger.info("LLM API 연결 테스트가 완료되었습니다.")
    except Exception as e:
        logger.error(f"LLM API 연결 테스트 중 오류 발생: {str(e)}", exc_info=True)
        logger.warning("LLM 관련 기능은 제한적으로 작동할 수 있습니다. 로컬 API 서버가 실행 중인지 확인하세요.")
    
    # Cog 생성 및 등록
    cog = QACog(bot)
    await bot.add_cog(cog)
    logger.info("QA Cog가 봇에 등록되었습니다.")
    
    # 명령어가 제대로 정의되었는지 확인
    commands = bot.tree.get_commands()
    logger.info(f"현재 정의된 명령어 수: {len(commands)}")
    for cmd in commands:
        logger.info(f"정의된 명령어: {cmd.name}") 