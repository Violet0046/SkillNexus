"""Simplified LLM client for SkillNexus — text-only completion, no tool execution."""

import litellm
import json
import asyncio
import time
from pathlib import Path
from typing import List, Dict, Optional

from skillnexus.utils.logging import Logger

# Load .env from project root
try:
    from dotenv import load_dotenv
    _env_path = Path(__file__).resolve().parent.parent.parent / ".env"
    if _env_path.exists():
        load_dotenv(_env_path)
except ImportError:
    pass

litellm.set_verbose = False
litellm.suppress_debug_info = True

logger = Logger.get_logger(__name__)


class LLMClient:
    """LLM client for text-only completion (no tool execution)."""

    def __init__(
        self,
        model: str = "openrouter/anthropic/claude-sonnet-4.5",
        enable_thinking: bool = False,
        rate_limit_delay: float = 0.0,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        timeout: float = 120.0,
        **litellm_kwargs
    ):
        self.model = model
        self.enable_thinking = enable_thinking
        self.rate_limit_delay = rate_limit_delay
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.timeout = timeout
        self.litellm_kwargs = litellm_kwargs
        self._logger = Logger.get_logger(__name__)
        self._last_call_time = 0.0

    @staticmethod
    def _merge_consecutive_system_messages(messages: List[Dict]) -> List[Dict]:
        if not messages:
            return messages
        merged: List[Dict] = []
        for msg in messages:
            if (
                merged
                and msg.get("role") == "system"
                and merged[-1].get("role") == "system"
            ):
                merged[-1] = {
                    "role": "system",
                    "content": merged[-1].get("content", "") + "\n\n" + msg.get("content", ""),
                }
            else:
                merged.append(msg.copy())
        return merged

    async def _rate_limit(self):
        if self.rate_limit_delay > 0:
            current_time = time.time()
            time_since_last_call = current_time - self._last_call_time
            if time_since_last_call < self.rate_limit_delay:
                sleep_time = self.rate_limit_delay - time_since_last_call
                self._logger.debug(f"Rate limiting: waiting {sleep_time:.2f}s")
                await asyncio.sleep(sleep_time)
            self._last_call_time = time.time()

    async def _call_with_retry(self, **completion_kwargs):
        last_exception = None

        for attempt in range(self.max_retries):
            try:
                response = await asyncio.wait_for(
                    litellm.acompletion(**completion_kwargs),
                    timeout=self.timeout
                )
                return response
            except asyncio.TimeoutError:
                self._logger.error(
                    f"LLM call timed out after {self.timeout}s "
                    f"(attempt {attempt + 1}/{self.max_retries})"
                )
                last_exception = TimeoutError(f"LLM call timed out after {self.timeout}s")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay)
                    continue
                else:
                    raise last_exception
            except Exception as e:
                last_exception = e
                error_str = str(e).lower()

                is_rate_limit = any(
                    kw in error_str
                    for kw in ['rate limit', 'rate_limit', 'too many requests', '429']
                )
                is_overloaded = any(
                    kw in error_str
                    for kw in ['overloaded', '500', '502', '503', '504',
                               'internal server error', 'service unavailable']
                )
                is_connection_error = any(
                    kw in error_str
                    for kw in ['cannot connect', 'connection refused', 'connection reset',
                               'connectionerror', 'timeout', 'name resolution',
                               'temporary failure', 'network unreachable']
                )

                if attempt < self.max_retries - 1 and (
                    is_rate_limit or is_overloaded or is_connection_error
                ):
                    if is_rate_limit:
                        backoff_delay = 60 + (attempt * 30)
                        error_type = "Rate limit"
                    elif is_connection_error:
                        backoff_delay = min(10 * (2 ** attempt), 60)
                        error_type = "Connection"
                    else:
                        backoff_delay = min(5 * (2 ** attempt), 60)
                        error_type = "Server overload"

                    self._logger.warning(
                        f"{error_type} error (attempt {attempt + 1}/{self.max_retries}), "
                        f"waiting {backoff_delay}s before retry..."
                    )
                    await asyncio.sleep(backoff_delay)
                    continue
                else:
                    if attempt >= self.max_retries - 1:
                        self._logger.error(f"Max retries ({self.max_retries}) reached")
                    raise

        raise last_exception

    async def complete(
        self,
        messages: List[Dict] | str,
        **kwargs
    ) -> Dict:
        """Single-round LLM call (text only, no tool execution).

        Args:
            messages: conversation history (List[Dict] or str)
            **kwargs: additional parameters for litellm completion

        Returns:
            Dict with keys: message, messages, content
        """
        if isinstance(messages, str):
            current_messages = [{"role": "user", "content": messages}]
        elif isinstance(messages, list):
            current_messages = messages.copy()
        else:
            raise ValueError("messages must be List[Dict] or str")

        completion_kwargs = {
            "model": kwargs.get("model", self.model),
            **self.litellm_kwargs,
        }

        enable_thinking = kwargs.get("enable_thinking", self.enable_thinking)
        if enable_thinking:
            completion_kwargs["reasoning_effort"] = kwargs.get("reasoning_effort", "medium")

        current_messages = self._merge_consecutive_system_messages(current_messages)

        await self._rate_limit()

        completion_kwargs["messages"] = current_messages
        response = await self._call_with_retry(**completion_kwargs)

        if not response.choices:
            raise ValueError("LLM response has no choices")

        response_message = response.choices[0].message

        assistant_message = {
            "role": "assistant",
            "content": response_message.content or "",
        }

        current_messages.append(assistant_message)

        return {
            "message": assistant_message,
            "messages": current_messages,
            "content": response_message.content or "",
        }

    @staticmethod
    def format_messages_to_text(messages: List[Dict]) -> str:
        formatted = ""
        for msg in messages:
            role = msg.get("role", "unknown").upper()
            content = msg.get("content", "")
            formatted += f"[{role}]\n{content}\n\n"
        return formatted
