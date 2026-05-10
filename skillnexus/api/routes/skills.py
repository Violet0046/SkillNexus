"""Skill CRUD and search endpoints."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from skillnexus.api.dependencies import get_registry, get_store, get_llm_client

router = APIRouter()


# ── Response models ──

class SkillMetaResponse(BaseModel):
    skill_id: str
    name: str
    description: str
    path: str


class SkillRecordResponse(BaseModel):
    skill_id: str
    name: str
    description: str
    path: str
    category: str
    tags: List[str]
    visibility: str
    is_active: bool
    total_selections: int
    total_applied: int
    total_completions: int
    total_fallbacks: int
    applied_rate: float
    completion_rate: float
    effective_rate: float
    fallback_rate: float


class SkillContentResponse(BaseModel):
    skill_id: str
    content: str


class SkillSelectRequest(BaseModel):
    task_description: str
    max_skills: int = 2
    model: Optional[str] = None


class SkillSelectResponse(BaseModel):
    selected: List[SkillMetaResponse]
    selection_record: Optional[Dict[str, Any]] = None


# ── Endpoints ──

@router.get("/", response_model=List[SkillMetaResponse])
async def list_skills():
    """List all discovered skills."""
    registry = get_registry()
    skills = registry.list_skills()
    return [
        SkillMetaResponse(
            skill_id=s.skill_id,
            name=s.name,
            description=s.description,
            path=str(s.path),
        )
        for s in skills
    ]


@router.get("/records", response_model=List[SkillRecordResponse])
async def list_skill_records(active_only: bool = True):
    """List all skill records from the store with quality metrics."""
    store = get_store()
    records = store.load_all() if not active_only else list(store.load_active().values())
    return [
        SkillRecordResponse(
            skill_id=r.skill_id,
            name=r.name,
            description=r.description,
            path=r.path or "",
            category=r.category.value,
            tags=r.tags,
            visibility=r.visibility.value,
            is_active=r.is_active,
            total_selections=r.total_selections,
            total_applied=r.total_applied,
            total_completions=r.total_completions,
            total_fallbacks=r.total_fallbacks,
            applied_rate=r.applied_rate,
            completion_rate=r.completion_rate,
            effective_rate=r.effective_rate,
            fallback_rate=r.fallback_rate,
        )
        for r in records
    ]


@router.get("/{skill_id}", response_model=SkillMetaResponse)
async def get_skill(skill_id: str):
    """Get a skill by ID (checks registry first, then store)."""
    registry = get_registry()
    meta = registry.get_skill(skill_id)
    if meta:
        return SkillMetaResponse(
            skill_id=meta.skill_id,
            name=meta.name,
            description=meta.description,
            path=str(meta.path),
        )
    # Fallback: try store
    store = get_store()
    record = store.load_record(skill_id)
    if record:
        return SkillMetaResponse(
            skill_id=record.skill_id,
            name=record.name,
            description=record.description,
            path=record.path or "",
        )
    raise HTTPException(status_code=404, detail=f"Skill not found: {skill_id}")


@router.get("/{skill_id}/content", response_model=SkillContentResponse)
async def get_skill_content(skill_id: str):
    """Get the SKILL.md content (frontmatter stripped) for a skill."""
    registry = get_registry()
    content = registry.load_skill_content(skill_id)
    if content is not None:
        return SkillContentResponse(skill_id=skill_id, content=content)
    # Fallback: read from disk using store record path
    store = get_store()
    record = store.load_record(skill_id)
    if record and record.path:
        from pathlib import Path
        skill_path = Path(record.path)
        if skill_path.exists():
            raw = skill_path.read_text(encoding="utf-8")
            # Strip frontmatter
            from skillnexus.core.skill_utils import strip_frontmatter
            content = strip_frontmatter(raw)
            return SkillContentResponse(skill_id=skill_id, content=content)
    raise HTTPException(status_code=404, detail=f"Skill not found: {skill_id}")


@router.post("/select", response_model=SkillSelectResponse)
async def select_skills(req: SkillSelectRequest):
    """Use LLM to select the most relevant skills for a task."""
    registry = get_registry()
    llm_client = get_llm_client()
    store = get_store()

    # Load quality data
    quality = None
    try:
        rows = store.get_summary(active_only=True)
        quality = {
            r["skill_id"]: {
                "total_selections": r.get("total_selections", 0),
                "total_applied": r.get("total_applied", 0),
                "total_completions": r.get("total_completions", 0),
                "total_fallbacks": r.get("total_fallbacks", 0),
            }
            for r in rows
        }
    except Exception:
        pass

    selected, record = await registry.select_skills_with_llm(
        task_description=req.task_description,
        llm_client=llm_client,
        max_skills=req.max_skills,
        model=req.model,
        skill_quality=quality,
    )

    return SkillSelectResponse(
        selected=[
            SkillMetaResponse(
                skill_id=s.skill_id,
                name=s.name,
                description=s.description,
                path=str(s.path),
            )
            for s in selected
        ],
        selection_record=record,
    )


@router.post("/discover")
async def discover_skills():
    """Trigger skill discovery from configured directories."""
    registry = get_registry()
    discovered = registry.discover()
    return {
        "discovered": len(discovered),
        "skills": [
            {"skill_id": s.skill_id, "name": s.name}
            for s in discovered
        ],
    }


@router.post("/register")
async def register_skill_dir(dir_path: str):
    """Register a single skill directory."""
    registry = get_registry()
    meta = registry.register_skill_dir(Path(dir_path))
    if meta is None:
        raise HTTPException(status_code=400, detail="Failed to register skill directory")
    return {
        "skill_id": meta.skill_id,
        "name": meta.name,
        "description": meta.description,
    }


@router.get("/stats/summary")
async def get_stats():
    """Get overall skill statistics."""
    store = get_store()
    return store.get_stats()
