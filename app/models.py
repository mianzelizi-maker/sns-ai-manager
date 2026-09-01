import enum
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.database import Base


class Platform(str, enum.Enum):
    X = "x"
    INSTAGRAM = "instagram"


class PostStatus(str, enum.Enum):
    DRAFT = "draft"
    APPROVED = "approved"
    POSTED = "posted"


class Article(Base):
    __tablename__ = "articles"

    id = Column(Integer, primary_key=True)
    wp_post_id = Column(Integer, unique=True, nullable=False)
    title = Column(String(255), nullable=False)
    body = Column(Text, nullable=False)
    featured_image_url = Column(String(500), nullable=True)
    fetched_at = Column(DateTime, default=datetime.utcnow)

    generated_posts = relationship("GeneratedPost", back_populates="article")


class GeneratedPost(Base):
    __tablename__ = "generated_posts"

    id = Column(Integer, primary_key=True)
    article_id = Column(Integer, ForeignKey("articles.id"), nullable=False)
    platform = Column(Enum(Platform), nullable=False)
    content = Column(Text, nullable=False)
    status = Column(Enum(PostStatus), default=PostStatus.DRAFT)
    ai_image_path = Column(String(500), nullable=True)  # AI生成画像の保存先(未生成ならNone)
    created_at = Column(DateTime, default=datetime.utcnow)

    article = relationship("Article", back_populates="generated_posts")
    post_log = relationship("PostLog", back_populates="generated_post", uselist=False)
    schedules = relationship("Schedule", back_populates="generated_post")


class RepeatType(str, enum.Enum):
    NONE = "none"
    DAILY = "daily"
    WEEKLY = "weekly"
    WEEKDAYS = "weekdays"
    MONTHLY = "monthly"
    YEARLY = "yearly"
    CUSTOM = "custom"


class Schedule(Base):
    __tablename__ = "schedules"

    id = Column(Integer, primary_key=True)
    generated_post_id = Column(Integer, ForeignKey("generated_posts.id"), nullable=False)
    scheduled_at = Column(DateTime, nullable=False)
    repeat = Column(Enum(RepeatType), default=RepeatType.NONE, nullable=False)
    repeat_until = Column(DateTime, nullable=True)  # 繰り返しの終了日時(未設定なら無期限)
    custom_weekdays = Column(String(20), nullable=True)  # repeat=customの時のみ使用。例: "0,2,4"(月水金)
    custom_interval = Column(Integer, default=1, nullable=True)  # repeat=customの時のみ使用
    custom_unit = Column(String(10), nullable=True)  # day/week/month/year (repeat=customの時のみ使用)
    custom_end_type = Column(String(10), default="none", nullable=True)  # none/until/count
    custom_count = Column(Integer, nullable=True)  # custom_end_type=countの時の回数
    occurrence_count = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    generated_post = relationship("GeneratedPost", back_populates="schedules")


class RecommendedTime(Base):
    __tablename__ = "recommended_times"
    __table_args__ = (UniqueConstraint("platform", "weekday", name="uq_platform_weekday"),)

    id = Column(Integer, primary_key=True)
    platform = Column(Enum(Platform), nullable=False)
    weekday = Column(Integer, nullable=False)  # 0=月 ... 6=日 (Pythonのdate.weekday()と同じ)
    start_time = Column(String(10), nullable=False)
    end_time = Column(String(10), nullable=False)


class RecommendationRepeat(Base):
    __tablename__ = "recommendation_repeats"

    id = Column(Integer, primary_key=True)
    weekday = Column(Integer, unique=True, nullable=False)
    repeat = Column(String(20), default="weekly", nullable=False)
    custom_interval = Column(Integer, default=1, nullable=True)
    custom_unit = Column(String(10), default="week", nullable=True)  # day/week/month/year
    enabled = Column(Boolean, default=True, nullable=False)


class SnsAccount(Base):
    __tablename__ = "sns_accounts"

    id = Column(Integer, primary_key=True)
    platform = Column(Enum(Platform), nullable=False, unique=True)
    access_token = Column(String(500), nullable=False)
    refresh_token = Column(String(500), nullable=True)
    expires_at = Column(DateTime, nullable=True)


class PostLog(Base):
    __tablename__ = "post_logs"

    id = Column(Integer, primary_key=True)
    generated_post_id = Column(Integer, ForeignKey("generated_posts.id"), unique=True, nullable=False)
    posted_at = Column(DateTime, default=datetime.utcnow)
    external_post_id = Column(String(255), nullable=True)
    engagement_json = Column(Text, nullable=True)

    generated_post = relationship("GeneratedPost", back_populates="post_log")
