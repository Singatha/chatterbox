from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = (
        CheckConstraint("type IN ('direct')", name="ck_conversations_type"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    type: Mapped[str] = mapped_column(String(16), default="direct")
    name: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    direct_key: Mapped[Optional[str]] = mapped_column(String(73), unique=True, nullable=True)
    created_by: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    members: Mapped[list["ConversationMember"]] = relationship(  # noqa: F821, UP037
        back_populates="conversation",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    messages: Mapped[list["Message"]] = relationship(  # noqa: F821, UP037
        back_populates="conversation", cascade="all, delete-orphan"
    )

