import enum
from datetime import datetime, date

from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    Text,
    Boolean,
    DateTime,
    Date,
    Enum,
    ForeignKey,
    JSON,
    Index,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from db.database import Base


class PostStatus(str, enum.Enum):
    draft = "draft"
    producing = "producing"
    ready = "ready"
    scheduled = "scheduled"
    published = "published"
    failed = "failed"
    deleted = "deleted"


class ProductionStatus(str, enum.Enum):
    uploaded = "uploaded"
    analyzing = "analyzing"
    ready = "ready"
    rendering = "rendering"
    done = "done"
    failed = "failed"


class RenderStatus(str, enum.Enum):
    pending = "pending"
    rendering = "rendering"
    done = "done"
    failed = "failed"


class ExperimentStatus(str, enum.Enum):
    draft = "draft"
    running = "running"
    paused = "paused"
    completed = "completed"
    cancelled = "cancelled"


class InsightType(str, enum.Enum):
    briefing = "briefing"
    alert = "alert"
    suggestion = "suggestion"
    experiment_result = "experiment_result"


class InsightPriority(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class HealthStatus(str, enum.Enum):
    healthy = "healthy"
    warning = "warning"
    error = "error"
    disconnected = "disconnected"


# --- Core Tables ---


class Account(Base):
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    zernio_id = Column(String, unique=True, nullable=False)
    profile_id = Column(String, nullable=True)
    display_name = Column(String, nullable=False)
    username = Column(String, nullable=True)
    avatar_url = Column(String, nullable=True)
    niche = Column(String, nullable=True)
    health_status = Column(Enum(HealthStatus), default=HealthStatus.healthy)
    connected_at = Column(DateTime, server_default=func.now())
    last_synced_at = Column(DateTime, nullable=True)

    posts = relationship("Post", back_populates="account", cascade="all, delete-orphan")
    follower_snapshots = relationship(
        "FollowerSnapshot", back_populates="account", cascade="all, delete-orphan"
    )


class Post(Base):
    __tablename__ = "posts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    zernio_post_id = Column(String, nullable=True, unique=True)
    tiktok_post_id = Column(String, nullable=True)
    status = Column(Enum(PostStatus), default=PostStatus.draft, nullable=False)
    caption = Column(Text, nullable=True)
    media_path = Column(String, nullable=True)
    tiktok_settings = Column(JSON, nullable=True)  # privacy, comments, duet, stitch
    scheduled_at = Column(DateTime, nullable=True)
    published_at = Column(DateTime, nullable=True)
    failure_reason = Column(Text, nullable=True)
    retry_count = Column(Integer, default=0)
    production_id = Column(String, nullable=True)  # OpenMontage ref (Phase 6)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    account = relationship("Account", back_populates="posts")
    metric_snapshots = relationship(
        "MetricSnapshot", back_populates="post", cascade="all, delete-orphan"
    )
    experiment_assignment = relationship(
        "ExperimentAssignment", back_populates="post", uselist=False
    )


class MetricSnapshot(Base):
    __tablename__ = "metric_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    post_id = Column(Integer, ForeignKey("posts.id"), nullable=False)
    captured_at = Column(DateTime, server_default=func.now(), nullable=False)
    views = Column(Integer, default=0)
    likes = Column(Integer, default=0)
    comments = Column(Integer, default=0)
    shares = Column(Integer, default=0)
    engagement_rate = Column(Float, default=0.0)  # (likes+comments+shares)/views*100

    post = relationship("Post", back_populates="metric_snapshots")

    __table_args__ = (Index("ix_metric_post_captured", "post_id", "captured_at"),)


class FollowerSnapshot(Base):
    __tablename__ = "follower_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    date = Column(Date, nullable=False)
    count = Column(Integer, nullable=False)
    growth_abs = Column(Integer, default=0)
    growth_pct = Column(Float, default=0.0)

    account = relationship("Account", back_populates="follower_snapshots")

    __table_args__ = (
        Index("ix_follower_account_date", "account_id", "date", unique=True),
    )


# --- Experiment Tables ---


class Experiment(Base):
    __tablename__ = "experiments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    hypothesis = Column(Text, nullable=True)
    variable = Column(String, nullable=False)  # hook_style, posting_time, etc.
    variants = Column(JSON, nullable=False)  # ["variant_a", "variant_b"]
    metric_target = Column(String, default="engagement_rate")
    min_sample_size = Column(Integer, default=10)
    status = Column(Enum(ExperimentStatus), default=ExperimentStatus.draft)
    result_summary = Column(Text, nullable=True)
    confidence = Column(Float, nullable=True)  # p-value from Mann-Whitney U
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    completed_at = Column(DateTime, nullable=True)

    assignments = relationship(
        "ExperimentAssignment", back_populates="experiment", cascade="all, delete-orphan"
    )


class ExperimentAssignment(Base):
    __tablename__ = "experiment_assignments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    post_id = Column(Integer, ForeignKey("posts.id"), nullable=False, unique=True)
    experiment_id = Column(Integer, ForeignKey("experiments.id"), nullable=False)
    variant_name = Column(String, nullable=False)

    post = relationship("Post", back_populates="experiment_assignment")
    experiment = relationship("Experiment", back_populates="assignments")


# --- Agent Tables ---


class AgentInsight(Base):
    __tablename__ = "agent_insights"

    id = Column(Integer, primary_key=True, autoincrement=True)
    type = Column(Enum(InsightType), nullable=False)
    title = Column(String, nullable=False)
    body = Column(Text, nullable=False)
    priority = Column(Enum(InsightPriority), default=InsightPriority.medium)
    is_read = Column(Boolean, default=False)
    is_acted_on = Column(Boolean, default=False)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class AgentConversation(Base):
    __tablename__ = "agent_conversations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    role = Column(String, nullable=False)  # user, assistant
    content = Column(Text, nullable=False)
    tool_calls = Column(JSON, nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class AgentContextSummary(Base):
    __tablename__ = "agent_context_summaries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    week = Column(Date, nullable=False)  # Monday of the summary week
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    summary_text = Column(Text, nullable=False)
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("ix_context_week_account", "week", "account_id", unique=True),
    )


# --- Production Tables (Phase 6) ---


class VariablePreset(Base):
    __tablename__ = "variable_presets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    variable_type = Column(String, nullable=False)  # captions, color_grade, speed, etc.
    remotion_composition = Column(String, nullable=False)  # VariableCaptions, etc.
    params = Column(JSON, nullable=False, default=dict)  # Remotion composition props
    pre_process = Column(JSON, nullable=True)  # OpenMontage tool steps [{tool, inputs}]
    preview_thumbnail = Column(String, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    variants = relationship("ProductionVariant", back_populates="preset")


class Production(Base):
    __tablename__ = "productions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_video_path = Column(String, nullable=False)
    analysis = Column(JSON, nullable=True)  # transcript, scenes, duration, resolution
    status = Column(Enum(ProductionStatus), default=ProductionStatus.uploaded)
    created_at = Column(DateTime, server_default=func.now())

    variants = relationship(
        "ProductionVariant", back_populates="production", cascade="all, delete-orphan"
    )


class ProductionVariant(Base):
    __tablename__ = "production_variants"

    id = Column(Integer, primary_key=True, autoincrement=True)
    production_id = Column(Integer, ForeignKey("productions.id"), nullable=False)
    preset_id = Column(Integer, ForeignKey("variable_presets.id"), nullable=True)
    variant_label = Column(String, nullable=False)  # A, B, C
    tool_config = Column(JSON, nullable=False, default=dict)  # full render spec
    render_status = Column(Enum(RenderStatus), default=RenderStatus.pending)
    output_path = Column(String, nullable=True)
    error_message = Column(Text, nullable=True)
    post_id = Column(Integer, ForeignKey("posts.id"), nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    production = relationship("Production", back_populates="variants")
    preset = relationship("VariablePreset", back_populates="variants")
    post = relationship("Post")


