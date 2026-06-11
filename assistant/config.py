"""Assistant configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


class SettingsError(ValueError):
    """Raised when required assistant settings are missing or invalid."""


@dataclass(slots=True)
class MatrixSettings:
    """Configuration for the Matrix transport boundary."""

    homeserver_url: str = ""
    user_id: str = ""
    access_token: str = ""
    password: str = ""
    device_id: str = "assistant"
    sync_timeout_ms: int = 30000
    request_timeout_seconds: float = 15.0
    initial_sync_token: str = ""

    def validate(self) -> None:
        """Validate the Matrix configuration required to run the assistant."""
        missing: list[str] = []
        if not self.homeserver_url:
            missing.append("ASSISTANT_MATRIX_HOMESERVER_URL")
        if not self.user_id:
            missing.append("ASSISTANT_MATRIX_USER_ID")
        if not self.access_token and not self.password:
            missing.append("ASSISTANT_MATRIX_ACCESS_TOKEN or ASSISTANT_MATRIX_PASSWORD")
        if self.sync_timeout_ms <= 0:
            raise SettingsError("ASSISTANT_MATRIX_SYNC_TIMEOUT_MS must be greater than zero")
        if self.request_timeout_seconds <= 0:
            raise SettingsError(
                "ASSISTANT_MATRIX_REQUEST_TIMEOUT_SECONDS must be greater than zero"
            )
        if missing:
            raise SettingsError(f"Missing required Matrix settings: {', '.join(missing)}")


@dataclass(slots=True)
class LLMSettings:
    """Configuration for the external LLM API."""

    api_url: str = ""
    api_key: str = ""
    model: str = ""
    system_prompt: str = ""
    request_timeout_seconds: float = 30.0
    temperature: float = 0.2

    def validate(self) -> None:
        """Validate the external LLM configuration required to run the assistant."""
        missing: list[str] = []
        if not self.api_url:
            missing.append("ASSISTANT_LLM_API_URL")
        if not self.api_key:
            missing.append("ASSISTANT_LLM_API_KEY")
        if not self.model:
            missing.append("ASSISTANT_LLM_MODEL")
        if self.request_timeout_seconds <= 0:
            raise SettingsError("ASSISTANT_LLM_REQUEST_TIMEOUT_SECONDS must be greater than zero")
        if not 0 <= self.temperature <= 2:
            raise SettingsError("ASSISTANT_LLM_TEMPERATURE must be between 0 and 2")
        if missing:
            raise SettingsError(f"Missing required LLM settings: {', '.join(missing)}")


@dataclass(slots=True)
class MemorySettings:
    """Configuration for the conversational memory system."""

    working_memory_limit: int = 20
    max_facts_per_user: int = 500
    extraction_enabled: bool = True
    max_procedures_per_user: int = 200
    procedure_extraction_enabled: bool = True

    @classmethod
    def from_env(cls) -> "MemorySettings":
        return cls(
            working_memory_limit=int(
                os.getenv("ASSISTANT_MEMORY_WORKING_LIMIT", "20")
            ),
            max_facts_per_user=int(
                os.getenv("ASSISTANT_MEMORY_MAX_FACTS", "500")
            ),
            extraction_enabled=os.getenv(
                "ASSISTANT_MEMORY_EXTRACTION", "true"
            ).lower() in ("true", "1", "yes"),
            max_procedures_per_user=int(
                os.getenv("ASSISTANT_MEMORY_MAX_PROCEDURES", "200")
            ),
            procedure_extraction_enabled=os.getenv(
                "ASSISTANT_MEMORY_PROCEDURE_EXTRACTION", "true"
            ).lower() in ("true", "1", "yes"),
        )


@dataclass(slots=True)
class AssistantSettings:
    """Runtime settings for the assistant."""

    event_workers: int = 2
    queue_size: int = 1000
    log_level: str = "INFO"
    error_reply: str = "I could not complete that request."
    agent_max_steps: int = 10
    tool_modules: tuple[str, ...] = ("assistant.builtin_tools",)
    matrix: MatrixSettings = field(default_factory=MatrixSettings)
    llm: LLMSettings = field(default_factory=LLMSettings)
    memory: MemorySettings = field(default_factory=MemorySettings)

    def validate(self) -> None:
        """Validate that the assistant has the configuration needed to start."""
        if self.event_workers <= 0:
            raise SettingsError("ASSISTANT_EVENT_WORKERS must be greater than zero")
        if self.queue_size <= 0:
            raise SettingsError("ASSISTANT_QUEUE_SIZE must be greater than zero")
        self.matrix.validate()
        self.llm.validate()

    @classmethod
    def from_env(cls) -> "AssistantSettings":
        """Build settings from environment variables."""
        defaults = cls()
        matrix_defaults = MatrixSettings()
        llm_defaults = LLMSettings()

        return cls(
            event_workers=int(
                os.getenv("ASSISTANT_EVENT_WORKERS", str(defaults.event_workers))
            ),
            queue_size=int(os.getenv("ASSISTANT_QUEUE_SIZE", str(defaults.queue_size))),
            log_level=os.getenv("ASSISTANT_LOG_LEVEL", defaults.log_level),
            error_reply=os.getenv("ASSISTANT_ERROR_REPLY", defaults.error_reply),
            agent_max_steps=int(
                os.getenv("ASSISTANT_AGENT_MAX_STEPS", str(defaults.agent_max_steps))
            ),
            tool_modules=_parse_tool_modules(os.getenv("ASSISTANT_TOOL_MODULES", "")),
            matrix=MatrixSettings(
                homeserver_url=os.getenv("ASSISTANT_MATRIX_HOMESERVER_URL", ""),
                user_id=os.getenv("ASSISTANT_MATRIX_USER_ID", ""),
                access_token=os.getenv("ASSISTANT_MATRIX_ACCESS_TOKEN", ""),
                password=os.getenv("ASSISTANT_MATRIX_PASSWORD", ""),
                device_id=os.getenv("ASSISTANT_MATRIX_DEVICE_ID", matrix_defaults.device_id),
                sync_timeout_ms=int(
                    os.getenv(
                        "ASSISTANT_MATRIX_SYNC_TIMEOUT_MS",
                        str(matrix_defaults.sync_timeout_ms),
                    )
                ),
                request_timeout_seconds=float(
                    os.getenv(
                        "ASSISTANT_MATRIX_REQUEST_TIMEOUT_SECONDS",
                        str(matrix_defaults.request_timeout_seconds),
                    )
                ),
                initial_sync_token=os.getenv("ASSISTANT_MATRIX_INITIAL_SYNC_TOKEN", ""),
            ),
            llm=LLMSettings(
                api_url=os.getenv("ASSISTANT_LLM_API_URL", ""),
                api_key=os.getenv("ASSISTANT_LLM_API_KEY", ""),
                model=os.getenv("ASSISTANT_LLM_MODEL", ""),
                system_prompt=os.getenv("ASSISTANT_LLM_SYSTEM_PROMPT", ""),
                request_timeout_seconds=float(
                    os.getenv(
                        "ASSISTANT_LLM_REQUEST_TIMEOUT_SECONDS",
                        str(llm_defaults.request_timeout_seconds),
                    )
                ),
                temperature=float(
                    os.getenv("ASSISTANT_LLM_TEMPERATURE", str(llm_defaults.temperature))
                ),
            ),
            memory=MemorySettings.from_env(),
        )


def _parse_tool_modules(value: str) -> tuple[str, ...]:
    """Parse ASSISTANT_TOOL_MODULES as a comma-separated module list."""
    if not value.strip():
        return ("assistant.builtin_tools",)
    modules = [part.strip() for part in value.split(",") if part.strip()]
    return tuple(modules)
