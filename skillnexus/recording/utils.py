"""Recording utility functions — load, analyze, and format trajectory data.

Ported from OpenSpace with import path adaptations and display dependency removed.
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from skillnexus.utils.logging import Logger

logger = Logger.get_logger(__name__)


def load_trajectory_from_jsonl(jsonl_path: str) -> List[Dict[str, Any]]:
    trajectory = []
    if not os.path.exists(jsonl_path):
        logger.debug(f"No trajectory file found at {jsonl_path}")
        return []
    try:
        with open(jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    trajectory.append(json.loads(line))
        logger.info(f"Loaded {len(trajectory)} steps from {jsonl_path}")
        return trajectory
    except Exception as e:
        logger.error(f"Failed to load trajectory from {jsonl_path}: {e}")
        return []


def load_metadata(trajectory_dir: str) -> Optional[Dict[str, Any]]:
    metadata_path = os.path.join(trajectory_dir, "metadata.json")
    try:
        with open(metadata_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Failed to load metadata from {metadata_path}: {e}")
        return None


def format_trajectory_for_export(
    trajectory: List[Dict[str, Any]],
    format_type: str = "compact",
) -> str:
    if format_type == "compact":
        return _format_compact(trajectory)
    elif format_type == "detailed":
        return _format_detailed(trajectory)
    elif format_type == "markdown":
        return _format_markdown(trajectory)
    raise ValueError(f"Unknown format type: {format_type}")


def _format_compact(trajectory: List[Dict[str, Any]]) -> str:
    lines = []
    for step in trajectory:
        step_num = step.get("step", "?")
        backend = step.get("backend", "?")
        server = step.get("server")
        tool = step.get("tool", "?")
        result_status = "success" if step.get("result", {}).get("status") == "success" else "error"
        backend_str = f"{backend}@{server}" if server else backend
        lines.append(f"Step {step_num}: [{backend_str}] {tool} -> {result_status}")
    return "\n".join(lines)


def _format_detailed(trajectory: List[Dict[str, Any]]) -> str:
    lines = []
    for step in trajectory:
        step_num = step.get("step", "?")
        timestamp = step.get("timestamp", "?")
        backend = step.get("backend", "?")
        server = step.get("server")
        tool = step.get("tool", "?")
        command = step.get("command", "?")
        parameters = step.get("parameters", {})
        result = step.get("result", {})

        lines.append(f"\n{'─' * 60}")
        lines.append(f"  Step {step_num} ({timestamp})")
        lines.append(f"  Backend: {backend}" + (f"  Server: {server}" if server else ""))
        lines.append(f"  Tool: {tool}")
        lines.append(f"  Command: {command}")
        lines.append(f"{'─' * 60}")
        lines.append(f"  Parameters: {json.dumps(parameters, indent=4, ensure_ascii=False)}")
        lines.append(f"  Result: {json.dumps(result, indent=4, ensure_ascii=False)}")
    return "\n".join(lines)


def _format_markdown(trajectory: List[Dict[str, Any]]) -> str:
    lines = [
        "# Trajectory",
        "",
        "| Step | Backend | Server | Tool | Status | Screenshot |",
        "|------|---------|--------|------|--------|------------|",
    ]
    for step in trajectory:
        step_num = step.get("step", "?")
        backend = step.get("backend", "?")
        server = step.get("server", "-")
        tool = step.get("tool", "?")
        result_status = "Y" if step.get("result", {}).get("status") == "success" else "N"
        screenshot = "Y" if step.get("screenshot") else ""
        lines.append(f"| {step_num} | {backend} | {server} | {tool} | {result_status} | {screenshot} |")
    return "\n".join(lines)


def analyze_trajectory(trajectory: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not trajectory:
        return {"total_steps": 0, "success_rate": 0.0, "backends": {}, "tools": {}}
    total_steps = len(trajectory)
    success_count = 0
    backends: Dict[str, int] = {}
    tools: Dict[str, int] = {}
    for step in trajectory:
        if step.get("result", {}).get("status") == "success":
            success_count += 1
        backend = step.get("backend", "unknown")
        backends[backend] = backends.get(backend, 0) + 1
        tool = step.get("tool", "unknown")
        tools[tool] = tools.get(tool, 0) + 1
    return {
        "total_steps": total_steps,
        "success_count": success_count,
        "success_rate": success_count / total_steps if total_steps > 0 else 0.0,
        "backends": backends,
        "tools": tools,
    }


def load_recording_session(recording_dir: str) -> Dict[str, Any]:
    recording_path = Path(recording_dir)
    if not recording_path.exists():
        logger.error(f"Recording directory not found: {recording_dir}")
        return {}

    session: Dict[str, Any] = {
        "trajectory": [],
        "metadata": None,
        "plans": [],
        "decisions": [],
        "statistics": {},
    }

    traj_file = recording_path / "traj.jsonl"
    if traj_file.exists():
        session["trajectory"] = load_trajectory_from_jsonl(str(traj_file))
        session["statistics"] = analyze_trajectory(session["trajectory"])

    metadata_file = recording_path / "metadata.json"
    if metadata_file.exists():
        session["metadata"] = load_metadata(str(recording_path))

    plans_dir = recording_path / "plans"
    if plans_dir.exists():
        for plan_file in sorted(plans_dir.glob("plan_*.json")):
            try:
                with open(plan_file, "r", encoding="utf-8") as f:
                    session["plans"].append(json.load(f))
            except Exception as e:
                logger.warning(f"Failed to load plan {plan_file}: {e}")

    decisions_file = recording_path / "decisions.log"
    if decisions_file.exists():
        try:
            with open(decisions_file, "r", encoding="utf-8") as f:
                session["decisions"] = f.readlines()
        except Exception as e:
            logger.warning(f"Failed to load decisions: {e}")

    return session


def filter_trajectory(
    trajectory: List[Dict[str, Any]],
    backend: Optional[str] = None,
    tool: Optional[str] = None,
    status: Optional[str] = None,
    time_range: Optional[Tuple[str, str]] = None,
) -> List[Dict[str, Any]]:
    filtered = trajectory
    if backend:
        filtered = [s for s in filtered if s.get("backend") == backend]
    if tool:
        filtered = [s for s in filtered if s.get("tool") == tool]
    if status:
        filtered = [s for s in filtered if s.get("result", {}).get("status") == status]
    if time_range:
        start_time, end_time = time_range
        filtered = [s for s in filtered if start_time <= s.get("timestamp", "") <= end_time]
    return filtered


def extract_errors(trajectory: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [step for step in trajectory if step.get("result", {}).get("status") == "error"]


def generate_summary_report(recording_dir: str, output_file: Optional[str] = None) -> str:
    session = load_recording_session(recording_dir)
    if not session:
        return "Error: Could not load recording session"

    lines = ["# Recording Session Summary\n"]

    if session["metadata"]:
        metadata = session["metadata"]
        lines.append("## Metadata")
        lines.append(f"- **Task ID**: {metadata.get('task_id', 'N/A')}")
        lines.append(f"- **Start Time**: {metadata.get('start_time', 'N/A')}")
        lines.append(f"- **End Time**: {metadata.get('end_time', 'N/A')}")
        lines.append(f"- **Total Steps**: {metadata.get('total_steps', 0)}")
        lines.append(f"- **Backends**: {', '.join(metadata.get('backends', []))}")
        lines.append("")

    if session["statistics"]:
        stats = session["statistics"]
        lines.append("## Statistics")
        lines.append(f"- **Total Steps**: {stats.get('total_steps', 0)}")
        lines.append(f"- **Success Count**: {stats.get('success_count', 0)}")
        lines.append(f"- **Success Rate**: {stats.get('success_rate', 0):.2%}")
        lines.append("")
        lines.append("### Backend Distribution")
        for backend, count in stats.get("backends", {}).items():
            lines.append(f"- {backend}: {count}")
        lines.append("")
        lines.append("### Tool Distribution")
        for tool, count in sorted(stats.get("tools", {}).items(), key=lambda x: x[1], reverse=True):
            lines.append(f"- {tool}: {count}")
        lines.append("")

    if session["plans"]:
        lines.append(f"## Plans ({len(session['plans'])} total)")
        for i, plan in enumerate(session["plans"], 1):
            lines.append(f"### Plan {i}")
            lines.append(f"- Created: {plan.get('created_at', 'N/A')}")
            lines.append(f"- Created by: {plan.get('created_by', 'N/A')}")
            plan_data = plan.get("plan", {})
            if "task_updates" in plan_data:
                lines.append(f"- Tasks: {len(plan_data['task_updates'])}")
            lines.append("")

    if session["trajectory"]:
        errors = extract_errors(session["trajectory"])
        if errors:
            lines.append(f"## Errors ({len(errors)} total)")
            for error in errors[:5]:
                lines.append(f"- Step {error.get('step')}: {error.get('backend')} - {error.get('tool')}")
                error_msg = error.get("result", {}).get("output", "No error message")
                lines.append(f"  ```\n  {error_msg[:200]}\n  ```")
            if len(errors) > 5:
                lines.append(f"  ... and {len(errors) - 5} more errors")
            lines.append("")

    if session["decisions"]:
        lines.append(f"## Decisions ({len(session['decisions'])} total)")
        for decision in session["decisions"][:10]:
            lines.append(f"  {decision.strip()}")
        if len(session["decisions"]) > 10:
            lines.append(f"  ... and {len(session['decisions']) - 10} more decisions")
        lines.append("")

    report = "\n".join(lines)
    if output_file:
        try:
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(report)
            logger.info(f"Report saved to {output_file}")
        except Exception as e:
            logger.error(f"Failed to save report: {e}")
    return report


def compare_recordings(recording_dir1: str, recording_dir2: str) -> Dict[str, Any]:
    session1 = load_recording_session(recording_dir1)
    session2 = load_recording_session(recording_dir2)
    stats1 = session1.get("statistics", {})
    stats2 = session2.get("statistics", {})
    return {
        "session1": {
            "path": recording_dir1,
            "total_steps": stats1.get("total_steps", 0),
            "success_rate": stats1.get("success_rate", 0),
            "backends": stats1.get("backends", {}),
        },
        "session2": {
            "path": recording_dir2,
            "total_steps": stats2.get("total_steps", 0),
            "success_rate": stats2.get("success_rate", 0),
            "backends": stats2.get("backends", {}),
        },
        "differences": {
            "step_diff": stats2.get("total_steps", 0) - stats1.get("total_steps", 0),
            "success_rate_diff": stats2.get("success_rate", 0) - stats1.get("success_rate", 0),
        },
    }
