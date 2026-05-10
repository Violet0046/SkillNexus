"""SkillEvolver — execute skill evolution actions.

Three evolution types:
  FIX      — repair broken/outdated instructions (in-place, same name)
  DERIVED  — create enhanced version from existing skill (new directory)
  CAPTURED — capture novel reusable pattern from execution (brand new skill)

Three trigger sources:
  1. Post-analysis — analyzer found evolution suggestions for a specific task
  2. Metric monitor — periodic scan of skill health indicators
"""

from __future__ import annotations

import asyncio
import json
import re
import shutil
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, TYPE_CHECKING

from .types import (
    EvolutionSuggestion,
    EvolutionType,
    ExecutionAnalysis,
    SkillCategory,
    SkillLineage,
    SkillOrigin,
    SkillRecord,
)
from .patch import (
    PatchType,
    SkillEditResult,
    collect_skill_snapshot,
    create_skill,
    fix_skill,
    derive_skill,
    SKILL_FILENAME,
)
from .skill_utils import (
    extract_change_summary as _extract_change_summary,
    get_frontmatter_field as _extract_frontmatter_field,
    set_frontmatter_field as _set_frontmatter_field,
    strip_markdown_fences as _strip_markdown_fences,
    truncate as _truncate,
    validate_skill_dir as _validate_skill_dir,
)
from .registry import write_skill_id
from .store import SkillStore
from skillnexus.prompts import SkillEnginePrompts
from skillnexus.utils.logging import Logger

if TYPE_CHECKING:
    from .registry import SkillRegistry
    from skillnexus.llm import LLMClient

logger = Logger.get_logger(__name__)

EVOLUTION_COMPLETE = SkillEnginePrompts.EVOLUTION_COMPLETE
EVOLUTION_FAILED = SkillEnginePrompts.EVOLUTION_FAILED

_SKILL_CONTENT_MAX_CHARS = 12_000
_MAX_SKILL_NAME_LENGTH = 50


def _sanitize_skill_name(name: str) -> str:
    """Enforce naming rules for skill names (used as directory names)."""
    clean = re.sub(r"[^a-z0-9\-]", "-", name.lower().strip())
    clean = re.sub(r"-{2,}", "-", clean).strip("-")
    if len(clean) <= _MAX_SKILL_NAME_LENGTH:
        return clean
    truncated = clean[:_MAX_SKILL_NAME_LENGTH]
    last_hyphen = truncated.rfind("-")
    if last_hyphen > _MAX_SKILL_NAME_LENGTH // 2:
        truncated = truncated[:last_hyphen]
    return truncated.strip("-")


def _generate_name_from_direction(direction: str) -> str:
    """Generate a skill name from evolution direction when LLM omits frontmatter."""
    # Take first sentence or first 60 chars
    first_sentence = re.split(r"[。.\n]", direction)[0][:60]
    # Extract CJK and ASCII words, join with hyphens
    tokens = re.findall(r"[a-zA-Z]+|[一-鿿]+", first_sentence.lower())
    name = "-".join(tokens[:6]) or "captured-skill"
    return _sanitize_skill_name(name)


_ANALYSIS_CONTEXT_MAX = 5
_ANALYSIS_NOTE_MAX_CHARS = 500

_MAX_EVOLUTION_ATTEMPTS = 3

# Rule-based thresholds for candidate screening (relaxed — LLM confirms)
_FALLBACK_THRESHOLD = 0.4
_LOW_COMPLETION_THRESHOLD = 0.35
_HIGH_APPLIED_FOR_FIX = 0.4
_MODERATE_EFFECTIVE_THRESHOLD = 0.55
_MIN_APPLIED_FOR_DERIVED = 0.25


class EvolutionTrigger(str, Enum):
    """What initiated this evolution."""
    ANALYSIS         = "analysis"
    METRIC_MONITOR   = "metric_monitor"


@dataclass
class EvolutionContext:
    """Unified context for all evolution triggers."""
    trigger: EvolutionTrigger
    suggestion: EvolutionSuggestion

    # Parent skill context
    skill_records: List[SkillRecord] = field(default_factory=list)
    skill_contents: List[str] = field(default_factory=list)
    skill_dirs: List[Path] = field(default_factory=list)

    # Task context
    source_task_id: Optional[str] = None
    recent_analyses: List[ExecutionAnalysis] = field(default_factory=list)

    # Trigger-specific context
    tool_issue_summary: str = ""
    metric_summary: str = ""

    # For CAPTURED: preferred directory to write the new skill
    capture_dir: Optional[Path] = None


class SkillEvolver:
    """Execute skill evolution actions.

    Single entry point: ``evolve()`` takes an EvolutionContext, runs an
    LLM call, applies the edit with retry, validates the result, and
    persists the new SkillRecord via ``SkillStore``.

    Concurrency:
        ``max_concurrent`` controls the semaphore that throttles parallel
        evolutions.
    """

    def __init__(
        self,
        store: SkillStore,
        registry: "SkillRegistry",
        llm_client: "LLMClient",
        model: Optional[str] = None,
        *,
        max_concurrent: int = 3,
    ) -> None:
        self._store = store
        self._registry = registry
        self._llm_client = llm_client
        self._model = model

        self._max_concurrent = max(1, max_concurrent)
        self._semaphore = asyncio.Semaphore(self._max_concurrent)

        self._background_tasks: Set[asyncio.Task] = set()

    async def wait_background(self) -> None:
        """Await all outstanding background evolution tasks."""
        if self._background_tasks:
            logger.info(
                f"Waiting for {len(self._background_tasks)} background "
                f"evolution task(s) to finish..."
            )
            results = await asyncio.gather(*self._background_tasks, return_exceptions=True)
            for r in results:
                if isinstance(r, BaseException):
                    logger.warning(f"Background evolution task failed during shutdown: {r}")
            self._background_tasks.clear()

    async def evolve(self, ctx: EvolutionContext) -> Optional[SkillRecord]:
        """Execute one evolution action. Returns new SkillRecord or None."""
        evo_type = ctx.suggestion.evolution_type
        try:
            if evo_type == EvolutionType.FIX:
                return await self._evolve_fix(ctx)
            elif evo_type == EvolutionType.DERIVED:
                return await self._evolve_derived(ctx)
            elif evo_type == EvolutionType.CAPTURED:
                return await self._evolve_captured(ctx)
            else:
                logger.warning(f"Unknown evolution type: {evo_type}")
                return None
        except Exception as e:
            targets = "+".join(ctx.suggestion.target_skill_ids) or "(new)"
            logger.error(f"Evolution failed [{evo_type.value}] target={targets}: {e}")
            return None

    # Trigger 1: post-analysis
    async def process_analysis(
        self,
        analysis: ExecutionAnalysis,
        capture_dir: Optional[Path] = None,
    ) -> List[SkillRecord]:
        """Process all evolution suggestions from a completed analysis."""
        if not analysis.candidate_for_evolution:
            return []

        contexts: List[EvolutionContext] = []
        for suggestion in analysis.evolution_suggestions:
            ctx = self._build_context_from_analysis(
                analysis, suggestion, capture_dir=capture_dir,
            )
            if ctx is not None:
                contexts.append(ctx)

        if not contexts:
            return []

        results = await self._execute_contexts(contexts, "analysis")

        if results:
            names = [r.name for r in results]
            logger.info(
                f"[Trigger:analysis] Evolved {len(results)} skill(s): {names} "
                f"from task {analysis.task_id}"
            )

        self._store.mark_evolution_processed(analysis.task_id)
        return results

    # Trigger 2: periodic metric check
    async def process_metric_check(
        self, min_selections: int = 5,
    ) -> List[SkillRecord]:
        """Scan active skills and evolve those with poor health metrics."""
        confirmed_contexts: List[EvolutionContext] = []
        all_active = self._store.load_active()

        for skill_id, record in all_active.items():
            if record.total_selections < min_selections:
                continue

            evo_type, direction = self._diagnose_skill_health(record)
            if evo_type is None:
                continue

            content = self._load_skill_content(record)
            if not content:
                continue

            recent = self._store.load_analyses(skill_id=record.skill_id, limit=_ANALYSIS_CONTEXT_MAX)
            metric_summary = (
                f"selections={record.total_selections}, "
                f"applied_rate={record.applied_rate:.0%}, "
                f"completion_rate={record.completion_rate:.0%}, "
                f"effective_rate={record.effective_rate:.0%}, "
                f"fallback_rate={record.fallback_rate:.0%}"
            )

            # LLM confirmation
            confirmed = await self._llm_confirm_evolution(
                skill_record=record,
                skill_content=content,
                proposed_type=evo_type,
                proposed_direction=direction,
                trigger_context=f"Metric check: {metric_summary}",
                recent_analyses=recent,
            )
            if not confirmed:
                logger.debug(
                    f"[Trigger:metric_monitor] LLM rejected evolution "
                    f"for skill '{record.name}' ({evo_type.value})"
                )
                continue

            skill_dir = Path(record.path).parent if record.path else None
            confirmed_contexts.append(EvolutionContext(
                trigger=EvolutionTrigger.METRIC_MONITOR,
                suggestion=EvolutionSuggestion(
                    evolution_type=evo_type,
                    target_skill_ids=[record.skill_id],
                    direction=direction,
                ),
                skill_records=[record],
                skill_contents=[content],
                skill_dirs=[skill_dir] if skill_dir else [],
                recent_analyses=recent,
                metric_summary=metric_summary,
            ))

        if not confirmed_contexts:
            return []

        results = await self._execute_contexts(confirmed_contexts, "metric_monitor")
        return results

    async def _execute_contexts(
        self,
        contexts: List[EvolutionContext],
        trigger_label: str,
    ) -> List[SkillRecord]:
        """Execute a list of evolution contexts in parallel (throttled)."""
        async def _throttled(c: EvolutionContext) -> Optional[SkillRecord]:
            async with self._semaphore:
                return await self.evolve(c)

        raw = await asyncio.gather(
            *[_throttled(c) for c in contexts],
            return_exceptions=True,
        )
        results: List[SkillRecord] = []
        for r in raw:
            if isinstance(r, BaseException):
                logger.error(f"[Trigger:{trigger_label}] Evolution task raised: {r}")
            elif r is not None:
                results.append(r)

        if results:
            names = [r.name for r in results]
            logger.info(
                f"[Trigger:{trigger_label}] Evolved {len(results)} skill(s): {names}"
            )
        return results

    def schedule_background(
        self,
        coro,
        *,
        label: str = "background_evolution",
    ) -> Optional[asyncio.Task]:
        """Launch a coroutine as a background asyncio.Task."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.warning(f"No running event loop — cannot schedule {label}")
            return None

        task = loop.create_task(coro, name=label)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        task.add_done_callback(self._log_background_result)
        return task

    @staticmethod
    def _log_background_result(task: asyncio.Task) -> None:
        """Log the outcome of a background evolution task."""
        if task.cancelled():
            logger.debug(f"Background task '{task.get_name()}' was cancelled")
            return
        exc = task.exception()
        if exc:
            logger.error(
                f"Background task '{task.get_name()}' failed: {exc}",
                exc_info=exc,
            )

    # LLM confirmation for Trigger 2
    async def _llm_confirm_evolution(
        self,
        *,
        skill_record: SkillRecord,
        skill_content: str,
        proposed_type: EvolutionType,
        proposed_direction: str,
        trigger_context: str,
        recent_analyses: List[ExecutionAnalysis],
    ) -> bool:
        """Ask LLM to confirm whether a rule-based evolution candidate
        truly needs evolution.

        Returns True if LLM agrees, False otherwise.
        """
        analysis_ctx = self._format_analysis_context(recent_analyses)

        prompt = SkillEnginePrompts.evolution_confirm(
            skill_id=skill_record.skill_id,
            skill_content=_truncate(skill_content, _SKILL_CONTENT_MAX_CHARS // 2),
            proposed_type=proposed_type.value,
            proposed_direction=proposed_direction,
            trigger_context=trigger_context,
            recent_analyses=analysis_ctx,
        )

        model = self._model or self._llm_client.model
        try:
            result = await self._llm_client.complete(
                messages=[{"role": "user", "content": prompt}],
                model=model,
            )
            content = result.get("content", "").strip().lower()
            return self._parse_confirmation(content)
        except Exception as e:
            logger.warning(f"LLM confirmation failed, defaulting to skip: {e}")
            return False

    @staticmethod
    def _parse_confirmation(response: str) -> bool:
        """Parse LLM confirmation response (expects JSON with 'proceed' field)."""
        try:
            cleaned = response.strip()
            if cleaned.startswith("```"):
                cleaned = re.sub(r"^```(?:json)?\s*\n?", "", cleaned)
                cleaned = re.sub(r"\n?```\s*$", "", cleaned)
            data = json.loads(cleaned)
            if isinstance(data, dict):
                return bool(data.get("proceed", False))
        except (json.JSONDecodeError, ValueError):
            pass
        _wb = re.search
        if any(w in response for w in ("\"proceed\": true", "proceed: true")) \
                or _wb(r"\byes\b", response) \
                or _wb(r"\bconfirm\w*\b", response):
            return True
        if any(w in response for w in ("\"proceed\": false", "proceed: false")) \
                or _wb(r"\bno\b", response) \
                or _wb(r"\breject\w*\b", response) \
                or _wb(r"\bskip\w*\b", response):
            return False
        logger.debug("LLM confirmation response was ambiguous, defaulting to skip")
        return False

    async def _evolve_fix(self, ctx: EvolutionContext) -> Optional[SkillRecord]:
        """In-place fix: same name, same directory, new version record."""
        if not ctx.skill_records or not ctx.skill_contents or not ctx.skill_dirs:
            logger.warning("FIX requires exactly 1 parent (skill_records/contents/dirs)")
            return None

        parent = ctx.skill_records[0]
        parent_content = ctx.skill_contents[0]
        parent_dir = ctx.skill_dirs[0]

        dir_content = self._format_skill_dir_content(parent_dir)
        prompt = SkillEnginePrompts.evolution_fix(
            current_content=_truncate(dir_content or parent_content, _SKILL_CONTENT_MAX_CHARS),
            direction=ctx.suggestion.direction,
            failure_context=self._format_analysis_context(ctx.recent_analyses),
            tool_issue_summary=ctx.tool_issue_summary,
            metric_summary=ctx.metric_summary,
        )

        new_content = await self._run_evolution_call(prompt)
        if not new_content:
            return None

        new_content, change_summary = _extract_change_summary(new_content)

        edit_result = await self._apply_with_retry(
            apply_fn=lambda content: fix_skill(parent_dir, content, PatchType.AUTO),
            initial_content=new_content,
            skill_dir=parent_dir,
            ctx=ctx,
            prompt=prompt,
        )
        if edit_result is None or not edit_result.ok:
            return None

        updated_skill_md = edit_result.content_snapshot.get(SKILL_FILENAME, "")
        fixed_name = _extract_frontmatter_field(updated_skill_md, "name") or parent.name
        fixed_desc = _extract_frontmatter_field(updated_skill_md, "description") or parent.description

        new_id = f"{fixed_name}__v{parent.lineage.generation + 1}_{uuid.uuid4().hex[:8]}"
        model = self._model or self._llm_client.model

        new_record = SkillRecord(
            skill_id=new_id,
            name=fixed_name,
            description=fixed_desc,
            path=parent.path,
            category=parent.category,
            tags=list(parent.tags),
            visibility=parent.visibility,
            creator_id=parent.creator_id,
            lineage=SkillLineage(
                origin=SkillOrigin.FIXED,
                generation=parent.lineage.generation + 1,
                parent_skill_ids=[parent.skill_id],
                source_task_id=ctx.source_task_id,
                change_summary=change_summary or ctx.suggestion.direction,
                content_diff=edit_result.content_diff,
                content_snapshot=edit_result.content_snapshot,
                created_by=model,
            ),
            tool_dependencies=list(parent.tool_dependencies),
            critical_tools=list(parent.critical_tools),
        )

        await self._store.evolve_skill(new_record, [parent.skill_id])
        write_skill_id(parent_dir, new_id)

        from .registry import SkillMeta
        new_meta = SkillMeta(
            skill_id=new_id,
            name=fixed_name,
            description=fixed_desc,
            path=Path(parent.path),
        )
        self._registry.update_skill(parent.skill_id, new_meta)

        logger.info(
            f"FIX: {parent.name} gen{parent.lineage.generation} → "
            f"gen{new_record.lineage.generation} [{new_id}]"
        )
        return new_record

    async def _evolve_derived(self, ctx: EvolutionContext) -> Optional[SkillRecord]:
        """Create enhanced version in a new directory."""
        if not ctx.skill_records or not ctx.skill_contents or not ctx.skill_dirs:
            logger.warning("DERIVED requires at least one parent skill_record + content + dir")
            return None

        first_parent = ctx.skill_records[0]
        is_merge = len(ctx.skill_records) > 1

        if is_merge:
            parent_sections = []
            for i, (rec, sd) in enumerate(zip(ctx.skill_records, ctx.skill_dirs)):
                dir_content = self._format_skill_dir_content(sd)
                label = f"Parent {i + 1}: {rec.name}"
                parent_sections.append(
                    f"## {label}\n{_truncate(dir_content or ctx.skill_contents[i], _SKILL_CONTENT_MAX_CHARS)}"
                )
            combined_content = "\n\n---\n\n".join(parent_sections)
        else:
            dir_content = self._format_skill_dir_content(ctx.skill_dirs[0])
            combined_content = _truncate(dir_content or ctx.skill_contents[0], _SKILL_CONTENT_MAX_CHARS)

        prompt = SkillEnginePrompts.evolution_derived(
            parent_content=combined_content,
            direction=ctx.suggestion.direction,
            execution_insights=self._format_analysis_context(ctx.recent_analyses),
            metric_summary=ctx.metric_summary,
        )

        new_content = await self._run_evolution_call(prompt)
        if not new_content:
            return None

        new_content, change_summary = _extract_change_summary(new_content)

        new_name = _extract_frontmatter_field(new_content, "name")
        if not new_name or new_name == first_parent.name:
            suffix = "-merged" if is_merge else "-enhanced"
            new_name = f"{first_parent.name}{suffix}"
            new_content = _set_frontmatter_field(new_content, "name", new_name)

        new_name = _sanitize_skill_name(new_name)
        new_content = _set_frontmatter_field(new_content, "name", new_name)

        target_dir = ctx.skill_dirs[0].parent / new_name
        if target_dir.exists():
            new_name = f"{new_name}-{uuid.uuid4().hex[:6]}"
            new_name = _sanitize_skill_name(new_name)
            target_dir = ctx.skill_dirs[0].parent / new_name
            new_content = _set_frontmatter_field(new_content, "name", new_name)

        edit_result = await self._apply_with_retry(
            apply_fn=lambda content: derive_skill(ctx.skill_dirs, target_dir, content, PatchType.AUTO),
            initial_content=new_content,
            skill_dir=target_dir,
            ctx=ctx,
            prompt=prompt,
            cleanup_on_retry=target_dir,
        )
        if edit_result is None or not edit_result.ok:
            return None

        new_desc = _extract_frontmatter_field(new_content, "description") or first_parent.description

        parent_ids = [r.skill_id for r in ctx.skill_records]
        max_gen = max(r.lineage.generation for r in ctx.skill_records)
        all_tool_deps: set = set()
        all_critical: set = set()
        all_tags: set = set()
        for rec in ctx.skill_records:
            all_tool_deps.update(rec.tool_dependencies)
            all_critical.update(rec.critical_tools)
            all_tags.update(rec.tags)

        new_id = f"{new_name}__v0_{uuid.uuid4().hex[:8]}"
        model = self._model or self._llm_client.model

        new_record = SkillRecord(
            skill_id=new_id,
            name=new_name,
            description=new_desc,
            path=str(target_dir / SKILL_FILENAME),
            category=ctx.suggestion.category or first_parent.category,
            tags=sorted(all_tags),
            visibility=first_parent.visibility,
            creator_id=first_parent.creator_id,
            lineage=SkillLineage(
                origin=SkillOrigin.DERIVED,
                generation=max_gen + 1,
                parent_skill_ids=parent_ids,
                source_task_id=ctx.source_task_id,
                change_summary=change_summary or ctx.suggestion.direction,
                content_diff=edit_result.content_diff,
                content_snapshot=edit_result.content_snapshot,
                created_by=model,
            ),
            tool_dependencies=sorted(all_tool_deps),
            critical_tools=sorted(all_critical),
        )

        await self._store.evolve_skill(new_record, parent_ids)
        write_skill_id(target_dir, new_id)

        from .registry import SkillMeta
        new_meta = SkillMeta(
            skill_id=new_id,
            name=new_name,
            description=new_desc,
            path=target_dir / SKILL_FILENAME,
        )
        self._registry.add_skill(new_meta)

        parent_names = " + ".join(r.name for r in ctx.skill_records)
        logger.info(f"DERIVED: {parent_names} → {new_name} [{new_id}]")
        return new_record

    async def _evolve_captured(self, ctx: EvolutionContext) -> Optional[SkillRecord]:
        """Capture a novel pattern as a brand-new skill."""
        task_descriptions = []
        for a in ctx.recent_analyses[:_ANALYSIS_CONTEXT_MAX]:
            if a.execution_note:
                task_descriptions.append(
                    f"- task={a.task_id}: {a.execution_note[:200]}"
                )

        prompt = SkillEnginePrompts.evolution_captured(
            direction=ctx.suggestion.direction,
            category=(ctx.suggestion.category or SkillCategory.WORKFLOW).value,
            execution_highlights="\n".join(task_descriptions) if task_descriptions else "(no task context available)",
        )

        new_content = await self._run_evolution_call(prompt)
        if not new_content:
            return None

        new_content, change_summary = _extract_change_summary(new_content)

        new_name = _extract_frontmatter_field(new_content, "name")
        new_desc = _extract_frontmatter_field(new_content, "description")

        # Fallback: if LLM didn't produce valid frontmatter, generate name
        # from direction and inject frontmatter into the content.
        if not new_name:
            logger.info("CAPTURED: LLM did not produce frontmatter, generating from direction")
            new_name = _generate_name_from_direction(ctx.suggestion.direction)
            if not new_desc:
                new_desc = ctx.suggestion.direction[:200]
            new_content = _set_frontmatter_field(new_content, "name", new_name)
            new_content = _set_frontmatter_field(new_content, "description", new_desc)

        new_name = _sanitize_skill_name(new_name)
        new_content = _set_frontmatter_field(new_content, "name", new_name)

        base_dir: Optional[Path] = None
        if ctx.capture_dir and ctx.capture_dir.is_dir():
            base_dir = ctx.capture_dir
        else:
            base_dir = self._infer_capture_dir_from_analysis(ctx)

        if base_dir is None:
            skill_dirs = self._registry._skill_dirs
            if not skill_dirs:
                logger.warning("CAPTURED: no skill directories configured")
                return None
            base_dir = skill_dirs[0]
        target_dir = base_dir / new_name
        if target_dir.exists():
            new_name = f"{new_name}-{uuid.uuid4().hex[:6]}"
            new_name = _sanitize_skill_name(new_name)
            target_dir = base_dir / new_name
            new_content = _set_frontmatter_field(new_content, "name", new_name)

        edit_result = await self._apply_with_retry(
            apply_fn=lambda content: create_skill(target_dir, content, PatchType.AUTO),
            initial_content=new_content,
            skill_dir=target_dir,
            ctx=ctx,
            prompt=prompt,
            cleanup_on_retry=target_dir,
        )
        if edit_result is None or not edit_result.ok:
            return None

        snapshot = edit_result.content_snapshot
        add_all_diff = edit_result.content_diff

        new_id = f"{new_name}__v0_{uuid.uuid4().hex[:8]}"
        model = self._model or self._llm_client.model

        new_record = SkillRecord(
            skill_id=new_id,
            name=new_name,
            description=new_desc or new_name,
            path=str(target_dir / SKILL_FILENAME),
            category=ctx.suggestion.category or SkillCategory.WORKFLOW,
            lineage=SkillLineage(
                origin=SkillOrigin.CAPTURED,
                generation=0,
                parent_skill_ids=[],
                source_task_id=ctx.source_task_id,
                change_summary=change_summary or ctx.suggestion.direction,
                content_diff=add_all_diff,
                content_snapshot=snapshot,
                created_by=model,
            ),
        )

        await self._store.save_record(new_record)
        write_skill_id(target_dir, new_id)

        from .registry import SkillMeta
        new_meta = SkillMeta(
            skill_id=new_id,
            name=new_name,
            description=new_desc or new_name,
            path=target_dir / SKILL_FILENAME,
        )
        self._registry.add_skill(new_meta)

        logger.info(f"CAPTURED: {new_name} [{new_id}]")
        return new_record

    def _infer_capture_dir_from_analysis(
        self, ctx: EvolutionContext,
    ) -> Optional[Path]:
        """Infer the best skill root for a CAPTURED skill from analysis context."""
        if not ctx.recent_analyses:
            return None

        registry_roots = self._registry._skill_dirs
        if not registry_roots:
            return None

        for analysis in ctx.recent_analyses:
            for judgment in analysis.skill_judgments:
                if not judgment.skill_applied:
                    continue
                rec = self._store.load_record(judgment.skill_id)
                if not rec or not rec.path:
                    continue
                skill_path = Path(rec.path).parent
                for root in registry_roots:
                    try:
                        skill_path.relative_to(root)
                        logger.debug(
                            "CAPTURED: inferred capture dir %s from "
                            "applied skill %s", root, judgment.skill_id,
                        )
                        return root
                    except ValueError:
                        continue

        return None

    async def _run_evolution_call(self, prompt: str) -> Optional[str]:
        """Run evolution as a single LLM call (text only).

        Returns the edit content if EVOLUTION_COMPLETE is found, None otherwise.
        """
        model = self._model or self._llm_client.model

        try:
            result = await self._llm_client.complete(
                messages=[{"role": "user", "content": prompt}],
                model=model,
            )
        except Exception as e:
            logger.error(f"Evolution LLM call failed: {e}")
            return None

        content = result.get("content", "")
        if not content:
            logger.warning("Evolution LLM returned empty content")
            return None

        # Check for completion/failure tokens
        if EVOLUTION_COMPLETE in content or EVOLUTION_FAILED in content:
            edit_content, failure_reason = self._parse_evolution_output(content)
            if failure_reason is not None:
                logger.warning(f"Evolution LLM signalled failure: {failure_reason}")
                return None
            return edit_content

        # No token found — try to use the content anyway (strip fences)
        logger.debug("Evolution LLM did not output completion token, treating content as edit")
        clean = _strip_markdown_fences(content)
        clean, _ = _extract_change_summary(clean)
        return clean

    @staticmethod
    def _parse_evolution_output(content: str) -> tuple[Optional[str], Optional[str]]:
        """Extract edit content or failure reason from LLM output."""
        stripped = content.strip()

        if EVOLUTION_FAILED in stripped:
            idx = stripped.index(EVOLUTION_FAILED)
            reason_part = stripped[idx + len(EVOLUTION_FAILED):].strip()
            if reason_part.lower().startswith("reason:"):
                reason_part = reason_part[len("reason:"):].strip()
            reason = reason_part[:500] if reason_part else "LLM declined to produce edit (no reason given)"
            return None, reason

        if EVOLUTION_COMPLETE in stripped:
            clean = stripped.replace(EVOLUTION_COMPLETE, "").strip()
            clean = _strip_markdown_fences(clean)
            return clean, None

        return None, "No completion token found (unexpected)"

    async def _apply_with_retry(
        self,
        *,
        apply_fn,
        initial_content: str,
        skill_dir: Path,
        ctx: EvolutionContext,
        prompt: str,
        cleanup_on_retry: Optional[Path] = None,
    ) -> Optional[SkillEditResult]:
        """Apply an edit with retry on failure."""
        current_content = initial_content
        msg_history: List[Dict[str, Any]] = [
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": initial_content},
        ]

        for attempt in range(_MAX_EVOLUTION_ATTEMPTS):
            if attempt > 0 and cleanup_on_retry and cleanup_on_retry.exists():
                shutil.rmtree(cleanup_on_retry, ignore_errors=True)

            edit_result = apply_fn(current_content)

            if edit_result.ok:
                validation_error = _validate_skill_dir(skill_dir)
                if validation_error is None:
                    if attempt > 0:
                        logger.info(
                            f"Apply-retry succeeded on attempt {attempt + 1}/{_MAX_EVOLUTION_ATTEMPTS}"
                        )
                    return edit_result
                else:
                    error_msg = f"Validation failed: {validation_error}"
                    logger.warning(
                        f"Apply succeeded but validation failed "
                        f"(attempt {attempt + 1}/{_MAX_EVOLUTION_ATTEMPTS}): "
                        f"{validation_error}"
                    )
            else:
                error_msg = edit_result.error or "Unknown apply error"
                logger.warning(
                    f"Apply failed (attempt {attempt + 1}/{_MAX_EVOLUTION_ATTEMPTS}): "
                    f"{error_msg}"
                )

            if attempt >= _MAX_EVOLUTION_ATTEMPTS - 1:
                logger.error(
                    f"Apply-retry exhausted after {_MAX_EVOLUTION_ATTEMPTS} attempts. "
                    f"Last error: {error_msg}"
                )
                if cleanup_on_retry and cleanup_on_retry.exists():
                    shutil.rmtree(cleanup_on_retry, ignore_errors=True)
                return None

            # Retry: ask LLM to fix the edit
            current_on_disk = self._format_skill_dir_content(skill_dir) if skill_dir.is_dir() else ""
            retry_prompt = (
                f"The previous edit was not successful. "
                f"This was the error:\n\n{error_msg}\n\n"
            )
            if current_on_disk:
                retry_prompt += (
                    f"Here is the CURRENT content of the skill files on disk:\n\n"
                    f"{_truncate(current_on_disk, _SKILL_CONTENT_MAX_CHARS)}\n\n"
                )
            retry_prompt += (
                f"Please fix the issue and generate the edit again. "
                f"Follow the same output format as before."
            )
            msg_history.append({"role": "user", "content": retry_prompt})

            model = self._model or self._llm_client.model
            try:
                result = await self._llm_client.complete(
                    messages=msg_history,
                    model=model,
                )
                new_content = result.get("content", "")
                if not new_content:
                    logger.warning("Retry LLM returned empty content")
                    continue

                new_content = _strip_markdown_fences(new_content)
                new_content = new_content.replace(EVOLUTION_COMPLETE, "").replace(EVOLUTION_FAILED, "").strip()
                new_content, _ = _extract_change_summary(new_content)
                msg_history.append({"role": "assistant", "content": new_content})
                current_content = new_content

            except Exception as e:
                logger.error(f"Retry LLM call failed: {e}")
                continue

        return None

    def _build_context_from_analysis(
        self,
        analysis: ExecutionAnalysis,
        suggestion: EvolutionSuggestion,
        capture_dir: Optional[Path] = None,
    ) -> Optional[EvolutionContext]:
        """Build EvolutionContext from a single analysis suggestion."""
        records: List[SkillRecord] = []
        contents: List[str] = []
        dirs: List[Path] = []

        if suggestion.evolution_type in (EvolutionType.FIX, EvolutionType.DERIVED):
            if not suggestion.target_skill_ids:
                logger.warning("FIX/DERIVED suggestion missing target_skill_ids")
                return None

            for target_id in suggestion.target_skill_ids:
                rec = self._store.load_record(target_id)
                if not rec:
                    logger.warning(f"Target skill not found: {target_id}")
                    return None
                content = self._load_skill_content(rec)
                if not content:
                    logger.warning(f"Cannot load content for skill: {target_id}")
                    return None
                skill_dir = Path(rec.path).parent if rec.path else None

                records.append(rec)
                contents.append(content)
                if skill_dir:
                    dirs.append(skill_dir)

            if suggestion.evolution_type == EvolutionType.FIX and len(records) != 1:
                logger.warning(
                    f"FIX requires exactly 1 target, got {len(records)}: "
                    f"{suggestion.target_skill_ids}"
                )
                return None

        return EvolutionContext(
            trigger=EvolutionTrigger.ANALYSIS,
            suggestion=suggestion,
            skill_records=records,
            skill_contents=contents,
            skill_dirs=dirs,
            source_task_id=analysis.task_id,
            recent_analyses=[analysis],
            capture_dir=capture_dir,
        )

    def _load_skill_content(self, record: SkillRecord) -> str:
        """Load SKILL.md content from disk via registry or direct read."""
        content = self._registry.load_skill_content(record.skill_id)
        if content:
            return content
        if record.path:
            p = Path(record.path)
            if p.exists():
                try:
                    return p.read_text(encoding="utf-8")
                except Exception:
                    pass
        return ""

    @staticmethod
    def _format_skill_dir_content(skill_dir: Path) -> str:
        """Format all text files in a skill directory for prompt inclusion."""
        files = collect_skill_snapshot(skill_dir)
        if not files:
            return ""

        if len(files) == 1 and SKILL_FILENAME in files:
            return files[SKILL_FILENAME]

        parts: list[str] = []
        if SKILL_FILENAME in files:
            parts.append(f"### File: {SKILL_FILENAME}\n```markdown\n{files[SKILL_FILENAME]}\n```")
        for name, content in sorted(files.items()):
            if name == SKILL_FILENAME:
                continue
            parts.append(f"### File: {name}\n```\n{content}\n```")

        return "\n\n".join(parts)

    @staticmethod
    def _format_analysis_context(analyses: List[ExecutionAnalysis]) -> str:
        """Format recent analyses into a concise context block for prompts."""
        if not analyses:
            return "(no execution history available)"

        parts: List[str] = []
        for a in analyses[:_ANALYSIS_CONTEXT_MAX]:
            completed = "completed" if a.task_completed else "failed"

            skill_notes = []
            for j in a.skill_judgments:
                applied = "applied" if j.skill_applied else "NOT applied"
                note = f"  - {j.skill_id}: {applied}"
                if j.note:
                    note += f" — {j.note[:_ANALYSIS_NOTE_MAX_CHARS]}"
                skill_notes.append(note)

            tool_lines = []
            for issue in a.tool_issues[:3]:
                tool_lines.append(f"  - {issue[:200]}")

            block = f"### Task: {a.task_id} ({completed})\n"
            if a.execution_note:
                block += f"{a.execution_note[:_ANALYSIS_NOTE_MAX_CHARS]}\n"
            if skill_notes:
                block += "Skills:\n" + "\n".join(skill_notes) + "\n"
            if tool_lines:
                block += "Tool issues:\n" + "\n".join(tool_lines) + "\n"
            parts.append(block)

        return "\n".join(parts)

    @staticmethod
    def _diagnose_skill_health(
        record: SkillRecord,
    ) -> tuple[Optional[EvolutionType], str]:
        """Diagnose what type of evolution a skill needs based on metrics."""
        if record.fallback_rate > _FALLBACK_THRESHOLD:
            return EvolutionType.FIX, (
                f"High fallback rate ({record.fallback_rate:.0%}): "
                f"skill is frequently selected but not applied, "
                f"suggesting instructions are unclear or outdated."
            )

        if (record.applied_rate > _HIGH_APPLIED_FOR_FIX
                and record.completion_rate < _LOW_COMPLETION_THRESHOLD):
            return EvolutionType.FIX, (
                f"Low completion rate ({record.completion_rate:.0%}) despite "
                f"high applied rate ({record.applied_rate:.0%}): "
                f"skill instructions may be incorrect or incomplete."
            )

        if (record.effective_rate < _MODERATE_EFFECTIVE_THRESHOLD
                and record.applied_rate > _MIN_APPLIED_FOR_DERIVED):
            return EvolutionType.DERIVED, (
                f"Moderate effectiveness ({record.effective_rate:.0%}): "
                f"skill works sometimes but could be enhanced with "
                f"better error handling or alternative approaches."
            )

        return None, ""
