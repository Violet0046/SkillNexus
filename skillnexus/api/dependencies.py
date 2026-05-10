"""Shared API dependencies — singleton instances for store, registry, LLM client."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from skillnexus.config.settings import Settings
from skillnexus.core.store import SkillStore
from skillnexus.core.registry import SkillRegistry
from skillnexus.llm.client import LLMClient
from skillnexus.core.analyzer import ExecutionAnalyzer
from skillnexus.core.evolver import SkillEvolver
from skillnexus.recording.manager import RecordingManager
from skillnexus.utils.logging import Logger

logger = Logger.get_logger(__name__)

# Module-level singletons (initialized on first access or via initialize())
_store: Optional[SkillStore] = None
_registry: Optional[SkillRegistry] = None
_llm_client: Optional[LLMClient] = None
_analyzer: Optional[ExecutionAnalyzer] = None
_evolver: Optional[SkillEvolver] = None
_settings: Optional[Settings] = None
_recording_manager: Optional[RecordingManager] = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings.load()
    return _settings


def get_store() -> SkillStore:
    global _store
    if _store is None:
        _store = SkillStore()
    return _store


def get_registry() -> SkillRegistry:
    global _registry
    if _registry is None:
        settings = get_settings()
        skill_dirs = [Path(d) for d in settings.skills.skill_dirs]
        _registry = SkillRegistry(skill_dirs=skill_dirs)
    return _registry


def get_llm_client() -> LLMClient:
    global _llm_client
    if _llm_client is None:
        settings = get_settings()
        _llm_client = LLMClient(
            model=settings.llm.model,
            enable_thinking=settings.llm.enable_thinking,
            rate_limit_delay=settings.llm.rate_limit_delay,
            max_retries=settings.llm.max_retries,
            retry_delay=settings.llm.retry_delay,
            timeout=settings.llm.timeout,
        )
    return _llm_client


def get_analyzer() -> ExecutionAnalyzer:
    global _analyzer
    if _analyzer is None:
        _analyzer = ExecutionAnalyzer(
            store=get_store(),
            llm_client=get_llm_client(),
            skill_registry=get_registry(),
        )
    return _analyzer


def get_evolver() -> SkillEvolver:
    global _evolver
    if _evolver is None:
        _evolver = SkillEvolver(
            store=get_store(),
            registry=get_registry(),
            llm_client=get_llm_client(),
        )
    return _evolver


def get_recording_manager() -> RecordingManager:
    global _recording_manager
    if _recording_manager is None:
        settings = get_settings()
        _recording_manager = RecordingManager(
            enabled=settings.recording.enabled,
            log_dir=settings.recording.log_dir,
            backends=settings.recording.backends,
            enable_conversation_log=settings.recording.enable_conversation_log,
        )
    return _recording_manager


def initialize(
    settings: Optional[Settings] = None,
    skill_dirs: Optional[list[Path]] = None,
) -> None:
    """Initialize all singletons. Call once at startup."""
    global _settings, _store, _registry, _llm_client, _analyzer, _evolver, _recording_manager

    _settings = settings or Settings.load()
    _store = SkillStore()

    dirs = skill_dirs or [Path(d) for d in _settings.skills.skill_dirs]
    _registry = SkillRegistry(skill_dirs=dirs)
    _registry.discover()

    _llm_client = LLMClient(
        model=_settings.llm.model,
        enable_thinking=_settings.llm.enable_thinking,
        rate_limit_delay=_settings.llm.rate_limit_delay,
        max_retries=_settings.llm.max_retries,
        retry_delay=_settings.llm.retry_delay,
        timeout=_settings.llm.timeout,
    )

    _analyzer = ExecutionAnalyzer(
        store=_store,
        llm_client=_llm_client,
        skill_registry=_registry,
    )

    _evolver = SkillEvolver(
        store=_store,
        registry=_registry,
        llm_client=_llm_client,
    )

    _recording_manager = RecordingManager(
        enabled=_settings.recording.enabled,
        log_dir=_settings.recording.log_dir,
        backends=_settings.recording.backends,
        enable_conversation_log=_settings.recording.enable_conversation_log,
    )

    logger.info("SkillNexus initialized")
