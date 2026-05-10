"""Mid-execution skill retrieval.

Provides a function to search for relevant skills during task execution
when the initial skill set is insufficient. Reuses the same pipeline as
initial skill selection: quality filter → BM25+embedding pre-filter →
LLM plan-then-select.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TYPE_CHECKING

from skillnexus.utils.logging import Logger

if TYPE_CHECKING:
    from skillnexus.llm import LLMClient
    from .registry import SkillRegistry, SkillMeta
    from .store import SkillStore

logger = Logger.get_logger(__name__)


async def retrieve_skill(
    query: str,
    skill_registry: "SkillRegistry",
    llm_client: "LLMClient",
    skill_store: Optional["SkillStore"] = None,
    max_skills: int = 1,
) -> Optional[str]:
    """Search for relevant skills and return injected context.

    Args:
        query: The task description or search query.
        skill_registry: The skill registry to search.
        llm_client: LLM client for plan-then-select.
        skill_store: Optional store for quality data.
        max_skills: Maximum skills to return.

    Returns:
        Injected skill context string, or None if no relevant skill found.
    """
    quality = _load_skill_quality(skill_store) if skill_store else None

    selected, record = await skill_registry.select_skills_with_llm(
        query,
        llm_client=llm_client,
        max_skills=max_skills,
        skill_quality=quality,
    )

    if record:
        plan = record.get("brief_plan", "")
        if plan:
            logger.info(f"retrieve_skill plan: {plan}")

    if not selected:
        logger.info("retrieve_skill: no relevant skills found")
        return None

    logger.info(f"retrieve_skill matched: {[s.skill_id for s in selected]}")
    return skill_registry.build_context_injection(selected)


async def retrieve_skill_bm25(
    query: str,
    skill_registry: "SkillRegistry",
    top_k: int = 3,
) -> List["SkillMeta"]:
    """BM25-only skill retrieval (no LLM call).

    Useful for quick lookups or when no LLM client is available.

    Args:
        query: Search query.
        skill_registry: The skill registry to search.
        top_k: Number of results to return.

    Returns:
        List of SkillMeta objects ranked by relevance.
    """
    from .skill_ranker import SkillRanker, SkillCandidate
    from .skill_utils import strip_frontmatter

    skills = skill_registry.list_skills()
    if not skills:
        return []

    # Build candidates
    candidates: List[SkillCandidate] = []
    for s in skills:
        body = ""
        raw = skill_registry._content_cache.get(s.skill_id, "")
        if raw:
            body = strip_frontmatter(raw)
        candidates.append(SkillCandidate(
            skill_id=s.skill_id,
            name=s.name,
            description=s.description,
            body=body,
        ))

    ranker = SkillRanker()
    ranked = ranker.bm25_only(query, candidates, top_k=top_k)

    # Map back to SkillMeta
    meta_map = {s.skill_id: s for s in skills}
    return [meta_map[c.skill_id] for c in ranked if c.skill_id in meta_map]


def _load_skill_quality(
    skill_store: "SkillStore",
) -> Optional[Dict[str, Dict[str, Any]]]:
    """Load skill quality metrics from the store."""
    try:
        rows = skill_store.get_summary(active_only=True)
        return {
            r["skill_id"]: {
                "total_selections": r.get("total_selections", 0),
                "total_applied": r.get("total_applied", 0),
                "total_completions": r.get("total_completions", 0),
                "total_fallbacks": r.get("total_fallbacks", 0),
            }
            for r in rows
        }
    except Exception:
        return None
