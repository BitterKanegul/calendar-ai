import enum
from typing import Optional
from sqlalchemy import String, Integer, DateTime, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
import uuid
from datetime import datetime

from .base import Base


class EventPriority(str, enum.Enum):
    MANDATORY = "mandatory"
    OPTIONAL = "optional"


class EventFlexibility(str, enum.Enum):
    FIXED = "fixed"
    MOVABLE = "movable"


class EventCategory(str, enum.Enum):
    WORK = "work"
    STUDY = "study"
    PERSONAL = "personal"
    LEISURE = "leisure"


# Event model using mapped approach
class EventModel(Base):
    __tablename__ = "events"

    # 🔹 Internal primary key for performance
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # 🔸 Public-facing ID for APIs
    event_id: Mapped[str] = mapped_column(String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    startDate: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    endDate: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=False)
    location: Mapped[Optional[str]] = mapped_column(String(255))

    priority: Mapped[EventPriority] = mapped_column(
        SQLEnum(EventPriority), default=EventPriority.OPTIONAL, nullable=False, server_default=EventPriority.OPTIONAL.value
    )
    flexibility: Mapped[EventFlexibility] = mapped_column(
        SQLEnum(EventFlexibility), default=EventFlexibility.MOVABLE, nullable=False, server_default=EventFlexibility.MOVABLE.value
    )
    category: Mapped[EventCategory] = mapped_column(
        SQLEnum(EventCategory), default=EventCategory.PERSONAL, nullable=False, server_default=EventCategory.PERSONAL.value
    )

    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["UserModel"] = relationship("UserModel", back_populates="events")

    def __repr__(self):
        return f"<EventModel(id={self.id}, event_id='{self.event_id}', title='{self.title}')>"
