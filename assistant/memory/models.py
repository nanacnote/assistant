"""Domain models for the memory system."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ConversationMessage(BaseModel):
    """A single message in a conversation."""

    model_config = ConfigDict(extra="forbid")

    id: str
    conversation_id: str
    actor_id: str
    role: Literal["user", "assistant"]
    content: str
    created_at: datetime


class MemoryFact(BaseModel):
    """An extracted long-term memory about a user."""

    model_config = ConfigDict(extra="forbid")

    id: str
    user_id: str
    fact_text: str
    category: str = "general"
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    source_conv_id: str = ""
    access_count: int = 0
    last_accessed: datetime
    created_at: datetime


class ExtractedFact(BaseModel):
    """A fact extracted from a conversation turn by the LLM."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1)
    category: str = "general"
    importance: float = Field(default=0.5, ge=0.0, le=1.0)


FACT_CATEGORIES = ("preference", "fact", "event", "relationship", "instruction", "general")


class ProcedureMemory(BaseModel):
    """A stored procedure for accomplishing a task."""

    model_config = ConfigDict(extra="forbid")

    id: str
    user_id: str
    description: str
    steps: list[str]
    category: str = "general"
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    source_conv_id: str = ""
    execution_count: int = 0
    success_count: int = 0
    access_count: int = 0
    last_accessed: datetime
    created_at: datetime


class ExtractedProcedure(BaseModel):
    """A procedure extracted from an execution trace by the LLM."""

    model_config = ConfigDict(extra="forbid")

    description: str = Field(min_length=1)
    steps: list[str] = Field(min_length=1)
    category: str = "general"
    importance: float = Field(default=0.5, ge=0.0, le=1.0)


PROCEDURE_CATEGORIES = ("calendar", "wellbeing", "general")
