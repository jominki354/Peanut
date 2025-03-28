import os
import asyncio
import logging
from datetime import datetime
from pathlib import Path

from sqlalchemy import Column, Integer, String, Text, DateTime, create_engine, select, func, delete, Table, MetaData, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool

# 로깅 설정
logger = logging.getLogger('discord.database')

# Base 클래스 정의
Base = declarative_base()

class DiscordMessage(Base):
    """디스코드 메시지를 저장하는 모델"""
    __tablename__ = 'discord_messages'
    
    id = Column(String, primary_key=True)
    message_id = Column(String, index=True)
    channel_id = Column(String, index=True)
    guild_id = Column(String, index=True)
    author_id = Column(String, index=True)
    author_name = Column(String)
    content = Column(Text)
    created_at = Column(DateTime)
    attachments_count = Column(Integer, default=0)
    attachments_urls = Column(Text)
    collected_at = Column(DateTime, default=datetime.now)
    
    # 채널, 서버 이름 (조회 편의를 위해 저장)
    channel_name = Column(String)
    guild_name = Column(String)
    
    # 메시지 링크
    message_url = Column(String)
    
    # 스레드 관련 필드
    is_thread = Column(Boolean, default=False)
    thread_name = Column(String)
    parent_channel_id = Column(String)
    parent_channel_name = Column(String)
    
    # 분석 정보
    topics = Column(Text)
    message_type = Column(String)
    content_structure = Column(Text)
    markdown_used = Column(Text)
    sections = Column(Text)

class CollectionMetadata(Base):
    """메시지 수집 메타데이터 저장 모델"""
    __tablename__ = 'collection_metadata'
    
    id = Column(Integer, primary_key=True)
    key = Column(String(100), unique=True, nullable=False, index=True)
    value = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class DatabaseManager:
    """데이터베이스 관리 클래스"""
    def __init__(self, db_path='db/discord_messages.db', guild_id=None):
        # 서버 ID가 제공된 경우 서버별 DB 파일 사용
        if guild_id:
            # 서버 ID에서 서버명 추출하기 위한 더미 변수 (실제로는 get_guild_name 함수 필요)
            guild_name = f"guild_{guild_id}"
            # 파일명에 서버 ID 포함
            db_filename = f"discord_messages_{guild_name}.db"
            # 경로와 파일명 결합
            if os.path.dirname(db_path):
                self.db_path = os.path.join(os.path.dirname(db_path), db_filename)
            else:
                self.db_path = db_filename
        else:
            self.db_path = db_path
            
        # 경로가 상대 경로인 경우 절대 경로로 변환
        if not os.path.isabs(self.db_path):
            base_dir = Path(__file__).resolve().parent.parent
            self.db_path = os.path.join(base_dir, self.db_path)
            
        # 디렉토리가 없는 경우 생성
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            
        # SQLite 데이터베이스 URL 생성
        self.db_url = f"sqlite:///{self.db_path}"
        self.async_db_url = f"sqlite+aiosqlite:///{self.db_path}"
        
        # 동기 엔진 (주로 초기화와 마이그레이션에 사용)
        self.engine = create_engine(
            self.db_url,
            # SQLite에서는 pool 관련 매개변수가 지원되지 않아 제거
            pool_recycle=1800
        )
        
        # 비동기 엔진 (주요 데이터 작업에 사용)
        self.async_engine = create_async_engine(
            self.async_db_url,
            # SQLite+aiosqlite에서는 pool 관련 매개변수가 지원되지 않아 제거
            pool_recycle=1800
        )
        
        self.SessionLocal = sessionmaker(
            bind=self.engine, 
            autocommit=False, 
            autoflush=False
        )
        
        self.AsyncSessionLocal = sessionmaker(
            bind=self.async_engine,
            class_=AsyncSession,
            autocommit=False,
            autoflush=False
        )
        
        # 테이블 생성
        self.create_tables()
        logger.info(f"데이터베이스가 초기화되었습니다: {self.db_path}")
    
    def create_tables(self):
        """테이블 생성"""
        Base.metadata.create_all(self.engine)
        
    async def get_latest_message_date(self, guild_id, channel_id=None):
        """지정된 길드와 채널의 가장 최근 메시지 날짜를 조회"""
        async with self.AsyncSessionLocal() as session:
            query = select(func.max(DiscordMessage.created_at))
            
            if channel_id:
                query = query.where(
                    DiscordMessage.guild_id == str(guild_id),
                    DiscordMessage.channel_id == str(channel_id)
                )
            else:
                query = query.where(DiscordMessage.guild_id == str(guild_id))
                
            result = await session.execute(query)
            latest_date = result.scalar()
            
            return latest_date
    
    async def message_exists(self, message_id):
        """메시지 ID로 메시지 존재 여부 확인"""
        async with self.AsyncSessionLocal() as session:
            query = select(DiscordMessage).where(DiscordMessage.message_id == str(message_id))
            result = await session.execute(query)
            return result.scalar() is not None
    
    async def save_messages(self, messages):
        """디스코드 메시지 저장 (배치)
        
        Args:
            messages: 저장할 메시지 딕셔너리 목록
            
        Returns:
            저장된 메시지 수
        """
        if not messages:
            return 0
            
        saved_count = 0
        async with self.AsyncSessionLocal() as session:
            for msg_data in messages:
                if not msg_data:  # None인 경우 건너뜀
                    continue
                    
                # id 필드 설정 (message_id와 동일)
                if 'id' not in msg_data and 'message_id' in msg_data:
                    msg_data['id'] = msg_data['message_id']
                    
                # 필드 검증 및 변환
                for field, value in list(msg_data.items()):
                    # 존재하지 않는 필드는 제거
                    if not hasattr(DiscordMessage, field):
                        msg_data.pop(field, None)
                        
                try:
                    # 기존 메시지가 있는지 확인
                    msg_id = msg_data.get('message_id')
                    query = select(DiscordMessage).where(DiscordMessage.message_id == msg_id)
                    result = await session.execute(query)
                    existing_message = result.scalar_one_or_none()
                    
                    if existing_message:
                        # 기존 메시지 업데이트
                        for field, value in msg_data.items():
                            if hasattr(existing_message, field):
                                setattr(existing_message, field, value)
                    else:
                        # 새 메시지 생성
                        new_message = DiscordMessage(**msg_data)
                        session.add(new_message)
                        
                    saved_count += 1
                except Exception as e:
                    logger.error(f"메시지 저장 중 오류 발생: {str(e)}")
                    logger.error(f"문제가 된 메시지 데이터: {msg_data}")
                    continue
                    
            # 커밋
            try:
                await session.commit()
                return saved_count
            except Exception as e:
                logger.error(f"데이터베이스 커밋 중 오류 발생: {str(e)}")
                await session.rollback()
                return 0
    
    async def get_message_count(self, guild_id=None, channel_id=None):
        """저장된 메시지 수 조회"""
        async with self.AsyncSessionLocal() as session:
            query = select(func.count()).select_from(DiscordMessage)
            
            if guild_id and channel_id:
                query = query.where(
                    DiscordMessage.guild_id == str(guild_id),
                    DiscordMessage.channel_id == str(channel_id)
                )
            elif guild_id:
                query = query.where(DiscordMessage.guild_id == str(guild_id))
                
            result = await session.execute(query)
            count = result.scalar()
            
            return count
            
    async def delete_bot_messages(self, bot_id):
        """봇 자신의 메시지를 데이터베이스에서 삭제"""
        if not bot_id:
            logger.warning("봇 ID가 제공되지 않아 메시지를 삭제할 수 없습니다.")
            return 0
            
        try:
            async with self.AsyncSessionLocal() as session:
                # 삭제 전 메시지 수 확인
                count_before = await self.get_message_count()
                
                # 봇 ID에 해당하는 메시지 삭제
                delete_stmt = delete(DiscordMessage).where(
                    DiscordMessage.author_id == str(bot_id)
                )
                
                result = await session.execute(delete_stmt)
                await session.commit()
                
                # 삭제 후 메시지 수 확인
                count_after = await self.get_message_count()
                deleted_count = count_before - count_after
                
                logger.info(f"봇 ID {bot_id}에 해당하는 메시지 {deleted_count}개를 삭제했습니다.")
                return deleted_count
                
        except Exception as e:
            logger.error(f"봇 메시지 삭제 중 오류 발생: {str(e)}")
            return 0
            
    async def save_collection_metadata(self, key, value):
        """수집 메타데이터 저장"""
        try:
            async with self.AsyncSessionLocal() as session:
                # 기존 메타데이터 조회
                query = select(CollectionMetadata).where(
                    CollectionMetadata.key == key
                )
                result = await session.execute(query)
                metadata = result.scalar()
                
                if metadata:
                    # 기존 메타데이터 업데이트
                    metadata.value = str(value)
                    metadata.updated_at = datetime.utcnow()
                else:
                    # 새 메타데이터 생성
                    metadata = CollectionMetadata(
                        key=key,
                        value=str(value),
                        updated_at=datetime.utcnow()
                    )
                    session.add(metadata)
                
                await session.commit()
                logger.debug(f"메타데이터 저장 완료: {key}={value}")
                return True
                
        except Exception as e:
            logger.error(f"메타데이터 저장 중 오류 발생: {str(e)}")
            return False
    
    async def get_collection_metadata(self, key, default=None):
        """수집 메타데이터 조회"""
        try:
            async with self.AsyncSessionLocal() as session:
                query = select(CollectionMetadata).where(
                    CollectionMetadata.key == key
                )
                result = await session.execute(query)
                metadata = result.scalar()
                
                if metadata and metadata.value:
                    logger.debug(f"메타데이터 조회 결과: {key}={metadata.value}")
                    return metadata.value
                else:
                    logger.debug(f"메타데이터 없음: {key}, 기본값 {default} 반환")
                    return default
                    
        except Exception as e:
            logger.error(f"메타데이터 조회 중 오류 발생: {str(e)}")
            return default
            
    async def save_last_collection_time(self, time=None):
        """마지막 메시지 수집 시간 저장"""
        if time is None:
            time = datetime.utcnow()
        
        time_str = time.strftime('%Y-%m-%d %H:%M:%S')
        return await self.save_collection_metadata('last_collection_time', time_str)
    
    async def get_last_collection_time(self):
        """마지막 메시지 수집 시간 조회"""
        time_str = await self.get_collection_metadata('last_collection_time')
        if time_str:
            try:
                return datetime.strptime(time_str, '%Y-%m-%d %H:%M:%S')
            except ValueError:
                logger.error(f"저장된 날짜 형식이 올바르지 않습니다: {time_str}")
                return None
        return None

    async def get_last_message_id(self, channel_id):
        """지정된 채널의 가장 최근 메시지 ID를 조회
        
        Args:
            channel_id: 채널 ID
            
        Returns:
            가장 최근 메시지 ID 또는 None
        """
        try:
            async with self.AsyncSessionLocal() as session:
                # 생성 시간순으로 정렬하여 가장 최근 메시지 조회
                query = select(DiscordMessage.message_id).where(
                    DiscordMessage.channel_id == str(channel_id)
                ).order_by(
                    DiscordMessage.created_at.desc()
                ).limit(1)
                
                result = await session.execute(query)
                last_message_id = result.scalar()
                
                return last_message_id
        except Exception as e:
            logger.error(f"마지막 메시지 ID 조회 중 오류 발생: {str(e)}")
            return None

# 데이터베이스 매니저 인스턴스 생성 - 딕셔너리로 여러 인스턴스 관리
db_managers = {}

def get_db_manager(db_path=None, guild_id=None):
    """데이터베이스 매니저 인스턴스 반환
    
    Args:
        db_path: 데이터베이스 경로, 없으면 환경 변수에서 가져옴
        guild_id: 서버 ID, 있으면 서버별 DB 사용
        
    Returns:
        DatabaseManager 인스턴스
    """
    global db_managers
    
    # 기본 DB 경로 설정
    if db_path is None:
        # 환경 변수에서 데이터베이스 경로 가져오기
        from ..utils.config import get_config
        config = get_config()
        db_path = config.get('DATABASE_PATH', 'db/discord_messages.db')
    
    # 서버별 DB 사용 시 캐시 키 설정
    cache_key = f"guild_{guild_id}" if guild_id else "default"
    
    # 해당 서버의 DB 매니저가 없으면 생성
    if cache_key not in db_managers:
        db_managers[cache_key] = DatabaseManager(db_path, guild_id)
        logger.info(f"서버 {guild_id or '기본'} 데이터베이스 매니저 생성: {db_managers[cache_key].db_path}")
    
    return db_managers[cache_key] 