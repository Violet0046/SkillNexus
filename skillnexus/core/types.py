"""Data types for skill quality tracking and evolution."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, ClassVar, Dict, List, Optional


class SkillCategory(str, Enum):
    """Skill primary category."""

    TOOL_GUIDE = "tool_guide"    # Tool guide
    WORKFLOW   = "workflow"      # End-to-end workflow
    REFERENCE  = "reference"     # Reference knowledge


class SkillVisibility(str, Enum):
    """Cloud visibility of a skill. (`Group` is managed by the cloud platform)"""

    PRIVATE = "private"  # Only visible to the creator
    PUBLIC  = "public"   # Visible to all users on the cloud


class EvolutionType(str, Enum):
    FIX      = "fix"       # Repair broken / outdated skill instructions
    DERIVED  = "derived"   # Enhance / specialize an existing skill
    CAPTURED = "captured"  # Capture a novel reusable pattern

    def to_origin(self) -> "SkillOrigin":
        """Convert this evolution action to the corresponding SkillOrigin."""
        return _EVOLUTION_TO_ORIGIN[self]


class SkillOrigin(str, Enum):
    """How this skill was created / entered the system.

    Version DAG model — every change creates a new SkillRecord node::

    Lineage rules:
      IMPORTED / CAPTURED → root node, no parent (parent_skill_ids = [])
      DERIVED             → 1+ parents, new skill name, new directory
      FIXED               → exactly 1 parent (previous version of same skill),
                            same ``name`` & ``path``, new ``skill_id``.
                            Files on disk are updated in-place; old directory
                            content (all files) is preserved via
                            ``content_snapshot`` dict in the DB.
                            Only the latest version is ``is_active=True``.
    """

    IMPORTED = "imported"  # Initial import, no parent
    CAPTURED = "captured"  # Captured from a successful execution with no parent skill involved
    DERIVED  = "derived"   # Derived from existing skill(s) (upgrade, wrap, compose, etc.)
    FIXED    = "fixed"     # Fix of existing skill — new record, parent = previous version


_EVOLUTION_TO_ORIGIN: Dict["EvolutionType", "SkillOrigin"] = {
    EvolutionType.FIX:      SkillOrigin.FIXED,
    EvolutionType.DERIVED:  SkillOrigin.DERIVED,
    EvolutionType.CAPTURED: SkillOrigin.CAPTURED,
}

_ORIGIN_TO_EVOLUTION: Dict["SkillOrigin", "EvolutionType"] = {
    v: k for k, v in _EVOLUTION_TO_ORIGIN.items()
}


@dataclass
class SkillLineage:
    """Tracks the evolutionary lineage of a skill."""

    origin: SkillOrigin
    generation: int = 0                                    # Distance from root
    parent_skill_ids: List[str] = field(default_factory=list)  # [] for IMPORTED / CAPTURED
    source_task_id: Optional[str] = None                   # Task that triggered evolution / capture
    change_summary: str = ""                               # LLM-generated description of changes
    content_diff: str = ""                                 # Combined unified diff of all files
    content_snapshot: Dict[str, str] = field(default_factory=dict)  # {relative_path: content}
    created_at: datetime = field(default_factory=datetime.now)
    created_by: str = ""                                   # "human" | model name

    def to_dict(self) -> Dict[str, Any]:
        return {
            "origin": self.origin.value,
            "generation": self.generation,
            "parent_skill_ids": self.parent_skill_ids,
            "source_task_id": self.source_task_id,
            "change_summary": self.change_summary,
            "content_diff": self.content_diff,
            "content_snapshot": self.content_snapshot,
            "created_at": self.created_at.isoformat(),
            "created_by": self.created_by,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SkillLineage":
        return cls(
            origin=SkillOrigin(data["origin"]),
            generation=data.get("generation", 0),
            parent_skill_ids=data.get("parent_skill_ids", []),
            source_task_id=data.get("source_task_id"),
            change_summary=data.get("change_summary", ""),
            content_diff=data.get("content_diff", ""),
            content_snapshot=data.get("content_snapshot", {}),
            created_at=(
                datetime.fromisoformat(data["created_at"])
                if data.get("created_at") else datetime.now()
            ),
            created_by=data.get("created_by", ""),
        )


@dataclass
class SkillJudgment:
    """Per-skill assessment within an ExecutionAnalysis."""

    skill_id: str
    skill_applied: bool = False    # Whether the skill was actually applied
    note: str = ""                 # Per-skill observation

    def to_dict(self) -> Dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "skill_applied": self.skill_applied,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SkillJudgment":
        return cls(
            skill_id=data["skill_id"],
            skill_applied=data.get("skill_applied", False),
            note=data.get("note", ""),
        )


@dataclass
class EvolutionSuggestion:
    """One evolution action suggested by the analysis LLM."""

    evolution_type: EvolutionType
    target_skill_ids: List[str] = field(default_factory=list)
    category: Optional[SkillCategory] = None
    direction: str = ""

    @property
    def target_skill_id(self) -> str:
        """Primary (or only) target skill_id. Empty string if none."""
        return self.target_skill_ids[0] if self.target_skill_ids else ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.evolution_type.value,
            "target_skills": self.target_skill_ids,
            "target_skill": self.target_skill_id,
            "category": self.category.value if self.category else None,
            "direction": self.direction,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EvolutionSuggestion":
        cat = None
        if data.get("category"):
            try:
                cat = SkillCategory(data["category"])
            except ValueError:
                pass
        raw_targets = data.get("target_skills")
        if isinstance(raw_targets, list):
            targets = [t for t in raw_targets if t]
        else:
            legacy = data.get("target_skill", "")
            targets = [legacy] if legacy else []
        return cls(
            evolution_type=EvolutionType(data["type"]),
            target_skill_ids=targets,
            category=cat,
            direction=data.get("direction", ""),
        )


@dataclass
class ExecutionAnalysis:
    """LLM-produced analysis of a single task execution."""

    task_id: str
    timestamp: datetime

    task_completed: bool = False
    execution_note: str = ""
    tool_issues: List[str] = field(default_factory=list)

    skill_judgments: List[SkillJudgment] = field(default_factory=list)

    evolution_suggestions: List[EvolutionSuggestion] = field(default_factory=list)

    analyzed_by: str = ""
    analyzed_at: datetime = field(default_factory=datetime.now)

    def get_judgment(self, skill_id: str) -> Optional[SkillJudgment]:
        """Find the judgment for a specific skill, or None."""
        for j in self.skill_judgments:
            if j.skill_id == skill_id:
                return j
        return None

    @property
    def skill_ids(self) -> List[str]:
        """List of skill_ids that were judged in this analysis."""
        return [j.skill_id for j in self.skill_judgments]

    @property
    def candidate_for_evolution(self) -> bool:
        """Whether any evolution suggestions exist."""
        return len(self.evolution_suggestions) > 0

    def suggestions_by_type(self, evo_type: EvolutionType) -> List[EvolutionSuggestion]:
        """Filter evolution suggestions by type."""
        return [s for s in self.evolution_suggestions if s.evolution_type == evo_type]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "timestamp": self.timestamp.isoformat(),
            "task_completed": self.task_completed,
            "execution_note": self.execution_note,
            "tool_issues": self.tool_issues,
            "skill_judgments": [j.to_dict() for j in self.skill_judgments],
            "evolution_suggestions": [s.to_dict() for s in self.evolution_suggestions],
            "analyzed_by": self.analyzed_by,
            "analyzed_at": self.analyzed_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExecutionAnalysis":
        return cls(
            task_id=data["task_id"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            task_completed=data.get("task_completed", False),
            execution_note=data.get("execution_note", ""),
            tool_issues=data.get("tool_issues", []),
            skill_judgments=[
                SkillJudgment.from_dict(j)
                for j in data.get("skill_judgments", [])
            ],
            evolution_suggestions=[
                EvolutionSuggestion.from_dict(s)
                for s in data.get("evolution_suggestions", [])
            ],
            analyzed_by=data.get("analyzed_by", ""),
            analyzed_at=(
                datetime.fromisoformat(data["analyzed_at"])
                if data.get("analyzed_at") else datetime.now()
            ),
        )


@dataclass
class SkillRecord:
    """Comprehensive record for a skill: identity + lineage + quality."""

    skill_id: str                            # Unique identifier
    name: str                                # Logical skill name (shared across versions)
    description: str
    path: str = ""                           # Path to SKILL.md (shared across FIXED versions)

    is_active: bool = True                   # Only the latest version is active

    # Category & tags
    category: SkillCategory = SkillCategory.WORKFLOW
    tags: List[str] = field(default_factory=list)

    # Ownership & visibility (for cloud sync)
    visibility: SkillVisibility = SkillVisibility.PRIVATE
    creator_id: str = ""                     # User ID of the skill owner / creator

    # Lineage
    lineage: SkillLineage = field(
        default_factory=lambda: SkillLineage(origin=SkillOrigin.IMPORTED)
    )

    # Tool dependencies
    tool_dependencies: List[str] = field(default_factory=list)
    critical_tools: List[str] = field(default_factory=list)

    # Execution stats
    total_selections: int = 0
    total_applied: int = 0
    total_completions: int = 0
    total_fallbacks: int = 0

    # Recent analysis history
    recent_analyses: List[ExecutionAnalysis] = field(default_factory=list)
    MAX_RECENT: ClassVar[int] = 50

    # Metadata
    first_seen: datetime = field(default_factory=datetime.now)
    last_updated: datetime = field(default_factory=datetime.now)

    @property
    def applied_rate(self) -> float:
        """Ratio of selections where the skill was actually applied."""
        return self.total_applied / self.total_selections if self.total_selections else 0.0

    @property
    def completion_rate(self) -> float:
        """Ratio of applied uses that led to task completion."""
        return self.total_completions / self.total_applied if self.total_applied else 0.0

    @property
    def effective_rate(self) -> float:
        """End-to-end effectiveness: selected -> applied -> completed."""
        return self.total_completions / self.total_selections if self.total_selections else 0.0

    @property
    def fallback_rate(self) -> float:
        """Ratio of selections that fell back (skill unusable signal)."""
        return self.total_fallbacks / self.total_selections if self.total_selections else 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "name": self.name,
            "description": self.description,
            "path": self.path,
            "is_active": self.is_active,
            "category": self.category.value,
            "tags": self.tags,
            "visibility": self.visibility.value,
            "creator_id": self.creator_id,
            "lineage": self.lineage.to_dict(),
            "tool_dependencies": self.tool_dependencies,
            "critical_tools": self.critical_tools,
            "total_selections": self.total_selections,
            "total_applied": self.total_applied,
            "total_completions": self.total_completions,
            "total_fallbacks": self.total_fallbacks,
            "recent_analyses": [a.to_dict() for a in self.recent_analyses],
            "first_seen": self.first_seen.isoformat(),
            "last_updated": self.last_updated.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SkillRecord":
        record = cls(
            skill_id=data["skill_id"],
            name=data["name"],
            description=data.get("description", ""),
            path=data.get("path", ""),
            is_active=data.get("is_active", True),
            category=SkillCategory(data["category"]) if data.get("category") else SkillCategory.WORKFLOW,
            tags=data.get("tags", []),
            visibility=(
                SkillVisibility(data["visibility"])
                if data.get("visibility") else SkillVisibility.PRIVATE
            ),
            creator_id=data.get("creator_id", ""),
            lineage=(
                SkillLineage.from_dict(data["lineage"])
                if data.get("lineage")
                else SkillLineage(origin=SkillOrigin.IMPORTED)
            ),
            tool_dependencies=data.get("tool_dependencies", []),
            critical_tools=data.get("critical_tools", []),
            total_selections=data.get("total_selections", 0),
            total_applied=data.get("total_applied", 0),
            total_completions=data.get("total_completions", 0),
            total_fallbacks=data.get("total_fallbacks", 0),
            first_seen=(
                datetime.fromisoformat(data["first_seen"])
                if data.get("first_seen") else datetime.now()
            ),
            last_updated=(
                datetime.fromisoformat(data["last_updated"])
                if data.get("last_updated") else datetime.now()
            ),
        )
        for a in data.get("recent_analyses", []):
            record.recent_analyses.append(ExecutionAnalysis.from_dict(a))
        return record
