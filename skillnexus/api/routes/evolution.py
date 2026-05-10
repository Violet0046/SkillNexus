"""Skill evolution endpoints."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from skillnexus.api.dependencies import get_evolver, get_store, get_analyzer
from skillnexus.core.evolver import EvolutionContext, EvolutionTrigger
from skillnexus.core.types import EvolutionSuggestion, EvolutionType

router = APIRouter()


# ── Request/Response models ──

class EvolutionRequest(BaseModel):
    evolution_type: str  # "fix" | "derived" | "captured"
    target_skill_ids: List[str] = []
    direction: str
    category: Optional[str] = None
    source_task_id: Optional[str] = None


class EvolutionResponse(BaseModel):
    skill_id: str
    name: str
    description: str
    origin: str
    generation: int
    parent_skill_ids: List[str]


class MetricCheckResponse(BaseModel):
    evolved: int
    skills: List[EvolutionResponse]


# ── Endpoints ──

@router.post("/trigger", response_model=Optional[EvolutionResponse])
async def trigger_evolution(req: EvolutionRequest):
    """Manually trigger a skill evolution.

    Use for FIX (repair existing skill), DERIVED (create enhanced version),
    or CAPTURED (capture a new pattern).
    """
    evolver = get_evolver()
    store = get_store()

    try:
        evo_type = EvolutionType(req.evolution_type)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid evolution_type: {req.evolution_type}. Must be fix, derived, or captured.",
        )

    # Build context
    from skillnexus.core.types import SkillCategory

    category = None
    if req.category:
        try:
            category = SkillCategory(req.category)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid category: {req.category}",
            )

    suggestion = EvolutionSuggestion(
        evolution_type=evo_type,
        target_skill_ids=req.target_skill_ids,
        category=category,
        direction=req.direction,
    )

    # Load skill records for FIX/DERIVED
    records = []
    contents = []
    dirs = []
    if evo_type in (EvolutionType.FIX, EvolutionType.DERIVED):
        from pathlib import Path
        for sid in req.target_skill_ids:
            rec = store.load_record(sid)
            if not rec:
                raise HTTPException(status_code=404, detail=f"Skill not found: {sid}")
            records.append(rec)
            # Load content via registry
            from skillnexus.api.dependencies import get_registry
            content = get_registry().load_skill_content(sid) or ""
            contents.append(content)
            if rec.path:
                dirs.append(Path(rec.path).parent)

    ctx = EvolutionContext(
        trigger=EvolutionTrigger.ANALYSIS,
        suggestion=suggestion,
        skill_records=records,
        skill_contents=contents,
        skill_dirs=dirs,
        source_task_id=req.source_task_id,
    )

    result = await evolver.evolve(ctx)
    if result is None:
        raise HTTPException(status_code=500, detail="Evolution failed")

    return EvolutionResponse(
        skill_id=result.skill_id,
        name=result.name,
        description=result.description,
        origin=result.lineage.origin.value,
        generation=result.lineage.generation,
        parent_skill_ids=result.lineage.parent_skill_ids,
    )


@router.post("/process-analysis/{task_id}", response_model=List[EvolutionResponse])
async def process_analysis_evolution(task_id: str):
    """Process evolution suggestions from a completed analysis."""
    analyzer = get_analyzer()
    evolver = get_evolver()
    store = get_store()

    analysis = store.load_analyses_for_task(task_id)
    if analysis is None:
        raise HTTPException(status_code=404, detail=f"No analysis found for task: {task_id}")

    if not analysis.candidate_for_evolution:
        return []

    results = await evolver.process_analysis(analysis)
    return [
        EvolutionResponse(
            skill_id=r.skill_id,
            name=r.name,
            description=r.description,
            origin=r.lineage.origin.value,
            generation=r.lineage.generation,
            parent_skill_ids=r.lineage.parent_skill_ids,
        )
        for r in results
    ]


@router.post("/metric-check", response_model=MetricCheckResponse)
async def run_metric_check(min_selections: int = 5):
    """Run periodic metric-based health check on all active skills."""
    evolver = get_evolver()
    results = await evolver.process_metric_check(min_selections=min_selections)
    return MetricCheckResponse(
        evolved=len(results),
        skills=[
            EvolutionResponse(
                skill_id=r.skill_id,
                name=r.name,
                description=r.description,
                origin=r.lineage.origin.value,
                generation=r.lineage.generation,
                parent_skill_ids=r.lineage.parent_skill_ids,
            )
            for r in results
        ],
    )


@router.get("/lineage/{skill_id}")
async def get_skill_lineage(skill_id: str):
    """Get the evolution lineage tree for a skill."""
    store = get_store()
    tree = store.get_lineage_tree(skill_id)
    if not tree:
        raise HTTPException(status_code=404, detail=f"No lineage found for skill: {skill_id}")
    return tree


@router.get("/ancestry/{skill_id}")
async def get_skill_ancestry(skill_id: str):
    """Get the full ancestry chain for a skill."""
    store = get_store()
    ancestry = store.get_ancestry(skill_id)
    return {
        "skill_id": skill_id,
        "ancestry": [
            {
                "skill_id": r.skill_id,
                "name": r.name,
                "generation": r.lineage.generation,
                "origin": r.lineage.origin.value,
                "is_active": r.is_active,
            }
            for r in ancestry
        ],
    }


@router.get("/top-skills")
async def get_top_skills(limit: int = 10):
    """Get the top-performing skills by effectiveness."""
    store = get_store()
    return store.get_top_skills(limit=limit)
