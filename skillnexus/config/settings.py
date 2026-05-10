"""Configuration for SkillNexus."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from skillnexus.config.constants import PROJECT_ROOT
from skillnexus.utils.logging import Logger

logger = Logger.get_logger(__name__)

_DEFAULT_CONFIG_PATH = PROJECT_ROOT / "skillnexus" / "config" / "settings.json"


@dataclass
class SkillConfig:
    """Skill engine configuration."""
    enabled: bool = True
    skill_dirs: List[str] = field(default_factory=list)
    max_select: int = 2


@dataclass
class LLMConfig:
    """LLM configuration."""
    model: str = "openrouter/anthropic/claude-sonnet-4.5"
    enable_thinking: bool = False
    rate_limit_delay: float = 0.0
    max_retries: int = 3
    retry_delay: float = 1.0
    timeout: float = 120.0


@dataclass
class EmbeddingConfig:
    """Embedding configuration."""
    api_base: str = ""
    api_key: str = ""
    model: str = "BAAI/bge-small-en-v1.5"


@dataclass
class RecordingConfig:
    """Recording subsystem configuration."""
    enabled: bool = True
    log_dir: str = "./logs/recordings"
    enable_conversation_log: bool = True
    backends: List[str] = field(default_factory=lambda: ["mcp", "gui", "shell", "system", "web"])


@dataclass
class Settings:
    """Top-level settings for SkillNexus."""
    log_level: str = "INFO"
    skills: SkillConfig = field(default_factory=SkillConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    recording: RecordingConfig = field(default_factory=RecordingConfig)

    @classmethod
    def load(cls, config_path: Optional[Path] = None) -> "Settings":
        """Load settings from JSON file, with env var overrides."""
        path = config_path or _DEFAULT_CONFIG_PATH

        data: dict = {}
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load config from {path}: {e}")

        skills_data = data.get("skills", {})
        llm_data = data.get("llm", {})
        embedding_data = data.get("embedding", {})
        recording_data = data.get("recording", {})

        settings = cls(
            log_level=data.get("log_level", "INFO"),
            skills=SkillConfig(
                enabled=skills_data.get("enabled", True),
                skill_dirs=skills_data.get("skill_dirs", []),
                max_select=skills_data.get("max_select", 2),
            ),
            llm=LLMConfig(
                model=llm_data.get("model", "openrouter/anthropic/claude-sonnet-4.5"),
                enable_thinking=llm_data.get("enable_thinking", False),
                rate_limit_delay=llm_data.get("rate_limit_delay", 0.0),
                max_retries=llm_data.get("max_retries", 3),
                retry_delay=llm_data.get("retry_delay", 1.0),
                timeout=llm_data.get("timeout", 120.0),
            ),
            embedding=EmbeddingConfig(
                api_base=embedding_data.get("api_base", ""),
                api_key=embedding_data.get("api_key", ""),
                model=embedding_data.get("model", "BAAI/bge-small-en-v1.5"),
            ),
            recording=RecordingConfig(
                enabled=recording_data.get("enabled", True),
                log_dir=recording_data.get("log_dir", "./logs/recordings"),
                enable_conversation_log=recording_data.get("enable_conversation_log", True),
                backends=recording_data.get("backends", ["mcp", "gui", "shell", "system", "web"]),
            ),
        )

        # Env var overrides
        if os.getenv("SKILLNEXUS_LLM_MODEL"):
            settings.llm.model = os.getenv("SKILLNEXUS_LLM_MODEL")
        if os.getenv("SKILLNEXUS_LOG_LEVEL"):
            settings.log_level = os.getenv("SKILLNEXUS_LOG_LEVEL")

        return settings
