from datetime import datetime, timedelta, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def default_expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=30)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    plan = Column(String(20), nullable=False, default="free")
    monthly_message_count = Column(Integer, nullable=False, default=0)
    usage_reset_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)

    subscription = relationship("Subscription", back_populates="user", uselist=False, cascade="all, delete-orphan")
    usage = relationship("Usage", back_populates="user", uselist=False, cascade="all, delete-orphan")


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True, nullable=False)
    plan = Column(String(20), nullable=False, default="free")
    status = Column(String(30), nullable=False, default="active")
    provider = Column(String(30), nullable=True)
    provider_ref = Column(String(255), nullable=True, index=True)
    expiry = Column(DateTime(timezone=True), nullable=False, default=default_expiry)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)

    user = relationship("User", back_populates="subscription")


class Usage(Base):
    __tablename__ = "usage"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True, nullable=False)
    requests_count = Column(Integer, nullable=False, default=0)
    last_reset_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)

    user = relationship("User", back_populates="usage")


class PaymentTransaction(Base):
    __tablename__ = "payment_transactions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    method = Column(String(30), nullable=False)
    reference = Column(String(255), unique=True, index=True, nullable=False)
    amount_pkr = Column(Integer, nullable=False)
    status = Column(String(30), nullable=False, default="pending")
    provider_txn_id = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
