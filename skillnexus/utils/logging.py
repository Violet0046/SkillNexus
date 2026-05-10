import logging
import os
import sys
import threading
import json
from pathlib import Path
from datetime import datetime
from typing import Optional
from colorama import init

init(autoreset=True)


def _load_log_level_from_config() -> int:
    """Load log_level from settings.json."""
    try:
        config_path = Path(__file__).parent.parent / "config" / "settings.json"
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                log_level = config.get("log_level", "INFO").upper()
                level_map = {
                    "DEBUG": 2, "INFO": 1, "WARNING": 0, "ERROR": 0, "CRITICAL": 0
                }
                return level_map.get(log_level, 1)
    except Exception:
        pass
    return 1


SKILLNEXUS_DEBUG = _load_log_level_from_config()

DEFAULT_LOG_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "logs")
DEFAULT_LOG_FILE_PATTERN = "skillnexus_{timestamp}.log"


class FlushFileHandler(logging.FileHandler):
    def emit(self, record):
        super().emit(record)
        self.flush()


class ColoredFormatter(logging.Formatter):
    COLORS = {
        'DEBUG': '\033[1;36m',
        'INFO': '\033[1;32m',
        'WARNING': '\033[1;33m',
        'ERROR': '\033[1;31m',
        'CRITICAL': '\033[1;35m',
        'RESET': '\033[0m',
    }

    def format(self, record: logging.LogRecord) -> str:
        formatted = super().format(record)
        level_color = self.COLORS.get(record.levelname, self.COLORS["RESET"])
        return f"{level_color}{formatted}{self.COLORS['RESET']}"


class Logger:
    _ROOT_NAME = "skillnexus"
    _LOG_FORMAT = (
        "%(asctime)s.%(msecs)03d [%(levelname)-8s] %(filename)s:%(lineno)d - %(message)s"
    )

    _lock = threading.Lock()
    _configured = False
    _registered: dict[str, logging.Logger] = {}

    @staticmethod
    def _get_default_log_file() -> str:
        script_name = "skillnexus"
        try:
            import __main__
            if hasattr(__main__, "__file__") and __main__.__file__:
                script_path = os.path.basename(__main__.__file__)
                script_name = os.path.splitext(script_path)[0]
        except Exception:
            pass

        log_dir = os.path.join(DEFAULT_LOG_DIR, script_name)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = DEFAULT_LOG_FILE_PATTERN.format(timestamp=timestamp)
        return os.path.abspath(os.path.join(log_dir, filename))

    @classmethod
    def get_logger(cls, name: Optional[str] = None) -> logging.Logger:
        if name is None:
            name = cls._ROOT_NAME

        need_config = False
        with cls._lock:
            logger = cls._registered.get(name)
            if logger is None:
                logger = logging.getLogger(name)
                logger.propagate = True
                cls._registered[name] = logger
            if not cls._configured:
                need_config = True

        if need_config:
            cls.configure()
        return logger

    @classmethod
    def configure(
        cls,
        *,
        level: Optional[int] = None,
        fmt: Optional[str] = None,
        log_to_console: bool = True,
        log_to_file: Optional[str] = "auto",
        use_colors: bool = True,
        force_color: bool = False,
        force: bool = False,
        attach_to_root: bool = False,
    ) -> None:
        with cls._lock:
            if cls._configured and not force:
                if level is not None:
                    cls._update_level(level)
                return

            resolved_level = cls._resolve_level(level)
            fmt_str = fmt or cls._LOG_FORMAT

            actual_log_file = None
            if log_to_file == "auto":
                actual_log_file = cls._get_default_log_file()
            elif log_to_file is not None:
                actual_log_file = log_to_file

            target_logger = (
                logging.getLogger() if attach_to_root else logging.getLogger(cls._ROOT_NAME)
            )
            target_logger.setLevel(resolved_level)

            for h in target_logger.handlers[:]:
                target_logger.removeHandler(h)

            date_fmt = "%Y-%m-%d %H:%M:%S"
            color_supported = force_color or (use_colors and cls._stdout_supports_color())
            console_formatter = (
                ColoredFormatter(fmt_str, datefmt=date_fmt) if color_supported
                else logging.Formatter(fmt_str, datefmt=date_fmt)
            )
            file_formatter = logging.Formatter(fmt_str, datefmt=date_fmt)

            if log_to_console:
                ch = logging.StreamHandler(sys.stdout)
                ch.setLevel(resolved_level)
                ch.setFormatter(console_formatter)
                target_logger.addHandler(ch)

            if actual_log_file:
                dir_path = os.path.dirname(actual_log_file)
                if dir_path:
                    os.makedirs(dir_path, exist_ok=True)
                fh = FlushFileHandler(actual_log_file, encoding="utf-8")
                fh.setLevel(resolved_level)
                fh.setFormatter(file_formatter)
                target_logger.addHandler(fh)

                if not cls._configured:
                    print(f"Log file enabled: {actual_log_file}")

            cls._configured = True

    @classmethod
    def set_level(cls, level: str) -> None:
        resolved = getattr(logging, level.upper(), None)
        if resolved is None or not isinstance(resolved, int):
            raise ValueError(f"Unknown log level: {level!r}")
        if not cls._configured:
            cls.configure(level=resolved, attach_to_root=True)
            return

        root_logger = logging.getLogger()
        root_logger.setLevel(resolved)
        for handler in root_logger.handlers:
            handler.setLevel(resolved)
        cls._update_level(resolved)

    @classmethod
    def set_debug(cls, debug_level: int = 2) -> None:
        global SKILLNEXUS_DEBUG
        SKILLNEXUS_DEBUG = max(0, min(debug_level, 2))
        cls._update_level(cls._resolve_level(None))

    @classmethod
    def reset_configuration(cls) -> None:
        with cls._lock:
            for lg in cls._registered.values():
                for h in lg.handlers[:]:
                    lg.removeHandler(h)
            cls._registered.clear()
            cls._configured = False

    @staticmethod
    def _stdout_supports_color() -> bool:
        return sys.stdout.isatty() and not os.getenv("NO_COLOR")

    @classmethod
    def _resolve_level(cls, level: Optional[int]) -> int:
        if level is not None:
            return getattr(logging, str(level).upper(), level)
        return {2: logging.DEBUG, 1: logging.INFO}.get(SKILLNEXUS_DEBUG, logging.WARNING)

    @classmethod
    def _update_level(cls, level: int) -> None:
        for lg in cls._registered.values():
            lg.setLevel(level)
            for h in lg.handlers:
                h.setLevel(level)


_env_debug = os.getenv("SKILLNEXUS_DEBUG") or os.getenv("DEBUG")
if _env_debug is not None:
    try:
        Logger.set_debug(int(_env_debug))
    except ValueError:
        Logger.set_debug(2 if _env_debug.strip().lower() in {"1", "true", "yes"} else 0)

Logger.configure(attach_to_root=True)

logger = Logger.get_logger()
logger.debug("SkillNexus logging initialized")
