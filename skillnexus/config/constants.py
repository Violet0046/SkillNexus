from pathlib import Path

LOG_LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

# Project root directory (SkillNexus/)
PROJECT_ROOT = Path(__file__).parent.parent.parent


__all__ = [
    "LOG_LEVELS",
    "PROJECT_ROOT",
]
