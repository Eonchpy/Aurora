from __future__ import annotations

from datetime import datetime
import uuid

from sqlalchemy import JSON, Column, String, Text, TIMESTAMP, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase
from pgvector.sqlalchemy import Vector


class Base(DeclarativeBase):
    """Base class for ORM models."""


class Document(Base):
    __tablename__ = "documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    content = Column(Text, nullable=False)
    embedding_vector = Column(Vector(1536), nullable=False)
    metadata_json = Column("metadata", JSON, default=dict)
    namespace = Column(String(100), default="default", index=True)
    document_type = Column(String(50), nullable=False, index=True)
    source = Column(String(100), nullable=False, index=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
