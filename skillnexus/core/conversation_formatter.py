"""Conversation log formatting for execution analysis.

Converts ``conversations.jsonl`` entries into a priority-based text block
suitable for LLM analysis prompts. All functions are pure (stateless).
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

TOOL_ERROR_MAX_CHARS = 1000
TOOL_SUCCESS_MAX_CHARS = 800
TOOL_ARGS_MAX_CHARS = 500
TOOL_SUMMARY_MAX_CHARS = 1500


def format_conversations(
    conversations: List[Dict[str, Any]],
    budget: int,
) -> str:
    """Format ``conversations.jsonl`` entries into a readable text block."""
    total_iters = sum(
        1 for c in conversations if c.get("type") == "iteration"
    )

    segments: List[Dict[str, Any]] = []

    for conv in conversations:
        conv_type = conv.get("type", "")
        if conv_type == "setup":
            _collect_setup_segments(conv, segments)
        elif conv_type == "iteration":
            _collect_iteration_segments(conv, total_iters, segments)

    return _assemble_with_budget(segments, budget)

def _collect_setup_segments(
    conv: Dict[str, Any],
    segments: List[Dict[str, Any]],
) -> None:
    for msg in conv.get("messages", []):
        role = msg.get("role", "")
        content = msg.get("content", "")
        if not isinstance(content, str):
            content = str(content)

        if role == "user":
            segments.append({
                "priority": 0,
                "text": f"[USER INSTRUCTION]\n{content}",
                "iteration": 0,
                "role": "user",
                "truncatable_to": None,
            })

def _collect_iteration_segments(
    conv: Dict[str, Any],
    total_iters: int,
    segments: List[Dict[str, Any]],
) -> None:
    iteration = conv.get("iteration", "?")
    is_last = (iteration == total_iters) if isinstance(iteration, int) else False

    for msg in conv.get("delta_messages", []):
        role = msg.get("role", "")
        content = msg.get("content", "")
        if not isinstance(content, str):
            content = str(content)

        if role == "assistant":
            if content:
                priority = 1 if is_last else 3
                segments.append({
                    "priority": priority,
                    "text": f"[Iter {iteration}] ASSISTANT: {content}",
                    "iteration": iteration,
                    "role": "assistant",
                    "truncatable_to": None,
                })

            for tc in msg.get("tool_calls", []):
                fn = tc.get("function", {})
                fn_name = fn.get("name", "?")
                fn_args = fn.get("arguments", "")
                if isinstance(fn_args, str) and len(fn_args) > TOOL_ARGS_MAX_CHARS:
                    fn_args = fn_args[:TOOL_ARGS_MAX_CHARS] + "..."
                segments.append({
                    "priority": 2,
                    "text": f"[Iter {iteration}] TOOL_CALL: {fn_name}({fn_args})",
                    "iteration": iteration,
                    "role": "tool_call",
                    "truncatable_to": None,
                })

        elif role == "tool":
            is_error = _is_error_result(content)

            if is_error:
                truncated = content[:TOOL_ERROR_MAX_CHARS]
                if len(content) > TOOL_ERROR_MAX_CHARS:
                    truncated += f"... [truncated, total {len(content)} chars]"
                segments.append({
                    "priority": 2,
                    "text": f"[Iter {iteration}] TOOL_ERROR: {truncated}",
                    "iteration": iteration,
                    "role": "tool_error",
                    "truncatable_to": None,
                })
            else:
                summary = _extract_embedded_summary(content)
                if summary:
                    segments.append({
                        "priority": 3,
                        "text": f"[Iter {iteration}] TOOL_RESULT (with summary):\n{summary}",
                        "iteration": iteration,
                        "role": "tool_result",
                        "truncatable_to": 500,
                    })
                else:
                    truncated = content[:TOOL_SUCCESS_MAX_CHARS]
                    if len(content) > TOOL_SUCCESS_MAX_CHARS:
                        truncated += f"... [truncated, total {len(content)} chars]"
                    segments.append({
                        "priority": 4,
                        "text": f"[Iter {iteration}] TOOL_RESULT: {truncated}",
                        "iteration": iteration,
                        "role": "tool_result",
                        "truncatable_to": 300,
                    })

        elif role == "system":
            if content:
                segments.append({
                    "priority": 5,
                    "text": f"[Iter {iteration}] SYSTEM: {content}",
                    "iteration": iteration,
                    "role": "system",
                    "truncatable_to": 150,
                })

def _assemble_with_budget(
    segments: List[Dict[str, Any]],
    budget: int,
) -> str:
    essential = [s for s in segments if s["priority"] <= 3]
    essential_chars = sum(len(s["text"]) for s in essential)

    remaining_budget = budget - essential_chars

    if remaining_budget < 0:
        return _assemble_essential_only(segments, budget)

    output_parts: List[str] = []
    used_chars = 0
    skipped_count = 0

    for seg in segments:
        text = seg["text"]
        priority = seg["priority"]

        if priority <= 3:
            output_parts.append(text)
            used_chars += len(text) + 1
        elif used_chars + len(text) + 1 <= budget:
            output_parts.append(text)
            used_chars += len(text) + 1
        else:
            truncatable_to = seg.get("truncatable_to")
            if truncatable_to and len(text) > truncatable_to:
                truncated = text[:truncatable_to] + "... [budget-truncated]"
                if used_chars + len(truncated) + 1 <= budget:
                    output_parts.append(truncated)
                    used_chars += len(truncated) + 1
                    continue
            skipped_count += 1

    if skipped_count > 0:
        output_parts.append(
            f"\n[... {skipped_count} lower-priority segment(s) omitted due to length ...]"
        )

    return "\n\n".join(output_parts)


def _assemble_essential_only(
    segments: List[Dict[str, Any]],
    budget: int,
) -> str:
    output_parts: List[str] = []
    used_chars = 0

    for seg in segments:
        if seg["priority"] <= 1:
            output_parts.append(seg["text"])
            used_chars += len(seg["text"]) + 1

    remaining = budget - used_chars

    tool_segments = [s for s in segments if s["priority"] == 2]
    if tool_segments:
        per_segment_budget = max(400, remaining // (len(tool_segments) + 1))
        for seg in tool_segments:
            text = seg["text"]
            if len(text) > per_segment_budget:
                text = text[:per_segment_budget] + "... [budget-truncated]"
            if used_chars + len(text) + 1 <= budget:
                output_parts.append(text)
                used_chars += len(text) + 1

    assistants = [s for s in segments if s["priority"] == 3]
    if assistants and used_chars < budget:
        output_parts.append("\n--- Older iteration summaries ---")
        for seg in assistants:
            first_line = seg["text"].split("\n", 1)[0][:200]
            if used_chars + len(first_line) + 1 > budget:
                output_parts.append("[... remaining iterations omitted ...]")
                break
            output_parts.append(first_line)
            used_chars += len(first_line) + 1

    return "\n\n".join(output_parts)

def _is_error_result(content: str) -> bool:
    if not content:
        return False
    head = content[:200].lower()
    return (
        content.startswith("[ERROR]")
        or content.startswith("ERROR")
        or "error" in head[:50]
        or "task failed" in head
        or "connection refused" in head
        or "timed out" in head
        or "traceback" in head
    )


def _extract_embedded_summary(content: str) -> Optional[str]:
    match = re.search(
        r"(Execution Summary \(\d+ steps?\):.*?)(?:={10,}|$)",
        content,
        re.DOTALL,
    )
    if match:
        summary = match.group(1).strip()
        summary_match = re.search(r"\nSummary:\s*(.+)", content)
        if summary_match:
            summary += f"\nConclusion: {summary_match.group(1).strip()}"
        return summary[:TOOL_SUMMARY_MAX_CHARS]

    return None
