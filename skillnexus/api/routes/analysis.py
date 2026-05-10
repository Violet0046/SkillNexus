"""Execution analysis endpoints."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from skillnexus.api.dependencies import get_analyzer, get_store

router = APIRouter()


# ── Request/Response models ──

class AnalyzeRequest(BaseModel):
    task_id: str
    recording_dir: str
    execution_result: Dict[str, Any]


class SkillJudgmentResponse(BaseModel):
    skill_id: str
    skill_applied: bool
    note: str


class EvolutionSuggestionResponse(BaseModel):
    evolution_type: str
    target_skill_ids: List[str]
    category: Optional[str] = None
    direction: str


class AnalysisResponse(BaseModel):
    task_id: str
    task_completed: bool
    execution_note: str
    tool_issues: List[str]
    skill_judgments: List[SkillJudgmentResponse]
    evolution_suggestions: List[EvolutionSuggestionResponse]
    analyzed_at: Optional[str] = None


# ── Endpoints ──

@router.post("/analyze", response_model=Optional[AnalysisResponse])
async def analyze_execution(req: AnalyzeRequest):
    """Run post-execution analysis on a completed task."""
    analyzer = get_analyzer()
    analysis = await analyzer.analyze_execution(
        task_id=req.task_id,
        recording_dir=req.recording_dir,
        execution_result=req.execution_result,
    )
    if analysis is None:
        return None
    return _to_response(analysis)


@router.get("/task/{task_id}", response_model=Optional[AnalysisResponse])
async def get_analysis_for_task(task_id: str):
    """Get the analysis for a specific task."""
    store = get_store()
    analysis = store.load_analyses_for_task(task_id)
    if analysis is None:
        raise HTTPException(status_code=404, detail=f"No analysis found for task: {task_id}")
    return _to_response(analysis)


@router.get("/evolution-candidates", response_model=List[AnalysisResponse])
async def get_evolution_candidates(limit: int = 20):
    """Get recent analyses flagged as evolution candidates."""
    analyzer = get_analyzer()
    candidates = await analyzer.get_evolution_candidates(limit=limit)
    return [_to_response(a) for a in candidates]


@router.get("/skill/{skill_id}", response_model=List[AnalysisResponse])
async def get_analyses_for_skill(skill_id: str, limit: int = 10):
    """Get recent analyses for a specific skill."""
    store = get_store()
    analyses = store.load_analyses(skill_id=skill_id, limit=limit)
    return [_to_response(a) for a in analyses]


def _to_response(analysis) -> AnalysisResponse:
    """Convert ExecutionAnalysis to response model."""
    return AnalysisResponse(
        task_id=analysis.task_id,
        task_completed=analysis.task_completed,
        execution_note=analysis.execution_note,
        tool_issues=analysis.tool_issues,
        skill_judgments=[
            SkillJudgmentResponse(
                skill_id=j.skill_id,
                skill_applied=j.skill_applied,
                note=j.note,
            )
            for j in analysis.skill_judgments
        ],
        evolution_suggestions=[
            EvolutionSuggestionResponse(
                evolution_type=s.evolution_type.value,
                target_skill_ids=s.target_skill_ids,
                category=s.category.value if s.category else None,
                direction=s.direction,
            )
            for s in analysis.evolution_suggestions
        ],
        analyzed_at=analysis.analyzed_at.isoformat() if analysis.analyzed_at else None,
    )
