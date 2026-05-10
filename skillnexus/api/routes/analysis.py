"""Execution analysis and recording endpoints."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from skillnexus.api.dependencies import get_analyzer, get_store, get_recording_manager

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


# ── Recording request models ──

class RecordingStartRequest(BaseModel):
    task_id: str
    agent_name: str = "GroundingAgent"


class RecordingStartResponse(BaseModel):
    recording_dir: str
    task_id: str


class ConversationSetupRequest(BaseModel):
    setup_messages: List[Dict[str, Any]]
    tools: Optional[List[Dict[str, Any]]] = None
    agent_name: str = "GroundingAgent"
    extra: Optional[Dict[str, Any]] = None


class IterationContextRequest(BaseModel):
    iteration: int
    delta_messages: List[Dict[str, Any]]
    response_metadata: Dict[str, Any] = {}
    agent_name: str = "GroundingAgent"
    extra: Optional[Dict[str, Any]] = None


class ToolExecutionRequest(BaseModel):
    tool_name: str
    backend: str
    parameters: Dict[str, Any] = {}
    result: Any = None
    server_name: Optional[str] = None
    is_success: bool = True
    metadata: Optional[Dict[str, Any]] = None


class SkillSelectionRequest(BaseModel):
    selection_record: Dict[str, Any]


class RetrievedToolsRequest(BaseModel):
    task_instruction: str
    tools: List[Dict[str, Any]]
    search_debug_info: Optional[Dict[str, Any]] = None


class ExecutionOutcomeRequest(BaseModel):
    status: str
    iterations: int
    execution_time: float = 0


class RecordingStopResponse(BaseModel):
    recording_dir: str
    total_steps: int


# ── Analysis endpoints ──

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


# ── Recording control endpoints ──

@router.post("/recording/start", response_model=RecordingStartResponse)
async def start_recording(req: RecordingStartRequest):
    """Start a new recording session. Returns the recording directory path."""
    manager = get_recording_manager()
    manager.task_id = req.task_id
    manager.agent_name = req.agent_name
    await manager.start(task_id=req.task_id)
    recording_dir = manager.trajectory_dir
    if not recording_dir:
        raise HTTPException(status_code=500, detail="Failed to start recording")
    return RecordingStartResponse(recording_dir=recording_dir, task_id=req.task_id)


@router.post("/recording/stop", response_model=RecordingStopResponse)
async def stop_recording():
    """Stop the active recording session."""
    manager = get_recording_manager()
    recording_dir = manager.trajectory_dir or ""
    total_steps = manager.step_count
    await manager.stop()
    return RecordingStopResponse(recording_dir=recording_dir, total_steps=total_steps)


@router.post("/recording/conversation-setup")
async def record_conversation_setup(req: ConversationSetupRequest):
    """Record initial conversation context (system prompt + user instruction)."""
    manager = get_recording_manager()
    await manager.record_conversation_setup(
        setup_messages=req.setup_messages,
        tools=req.tools,
        agent_name=req.agent_name,
        extra=req.extra,
    )
    return {"status": "ok"}


@router.post("/recording/iteration-context")
async def record_iteration_context(req: IterationContextRequest):
    """Record a single iteration's delta messages."""
    manager = get_recording_manager()
    await manager.record_iteration_context(
        iteration=req.iteration,
        delta_messages=req.delta_messages,
        response_metadata=req.response_metadata,
        agent_name=req.agent_name,
        extra=req.extra,
    )
    return {"status": "ok"}


@router.post("/recording/tool-execution")
async def record_tool_execution(req: ToolExecutionRequest):
    """Record a tool execution step."""
    manager = get_recording_manager()
    await manager.record_tool_execution(
        tool_name=req.tool_name,
        backend=req.backend,
        parameters=req.parameters,
        result=req.result,
        server_name=req.server_name,
        is_success=req.is_success,
        metadata=req.metadata,
    )
    return {"status": "ok"}


@router.post("/recording/skill-selection")
async def record_skill_selection(req: SkillSelectionRequest):
    """Record skill selection decision."""
    manager = get_recording_manager()
    await manager.record_skill_selection(req.selection_record)
    return {"status": "ok"}


@router.post("/recording/retrieved-tools")
async def record_retrieved_tools(req: RetrievedToolsRequest):
    """Record retrieved tools for a task."""
    manager = get_recording_manager()
    await manager.record_retrieved_tools(
        task_instruction=req.task_instruction,
        tools=req.tools,
        search_debug_info=req.search_debug_info,
    )
    return {"status": "ok"}


@router.post("/recording/execution-outcome")
async def record_execution_outcome(req: ExecutionOutcomeRequest):
    """Record task execution outcome (status, iterations, time)."""
    manager = get_recording_manager()
    await manager.save_execution_outcome(
        status=req.status,
        iterations=req.iterations,
        execution_time=req.execution_time,
    )
    return {"status": "ok"}


# ── Helpers ──

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
