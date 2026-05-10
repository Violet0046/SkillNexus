"""TrajectoryRecorder — low-level writer for tool execution trajectories.

Produces ``traj.jsonl`` and ``metadata.json`` in a per-task recording directory.

Ported from OpenSpace with platform-specific screenshot/video dependencies removed.
SkillNexus is a pure API service — screen capture is not applicable.
"""

import datetime
import json
from typing import Any, Dict, List, Optional
from pathlib import Path

from skillnexus.utils.logging import Logger

logger = Logger.get_logger(__name__)


class TrajectoryRecorder:
    def __init__(
        self,
        task_name: str = "",
        log_dir: str = "./logs/recordings",
    ):
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        folder_name = f"{task_name}_{timestamp}" if task_name else timestamp

        self.trajectory_dir = Path(log_dir) / folder_name
        self.trajectory_dir.mkdir(parents=True, exist_ok=True)

        self.task_name = task_name
        self.steps: List[Dict] = []
        self.step_counter = 0

        self.metadata: Dict[str, Any] = {
            "task_name": task_name,
            "start_time": datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        }

        self._save_metadata()

    async def record_step(
        self,
        backend: str,
        tool: str,
        command: str,
        result: Optional[Dict[str, Any]] = None,
        parameters: Optional[Dict[str, Any]] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        self.step_counter += 1
        timestamp = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

        step_info: Dict[str, Any] = {
            "step": self.step_counter,
            "timestamp": timestamp,
            "backend": backend,
        }

        if extra and "server" in extra:
            step_info["server"] = extra.pop("server")

        step_info["tool"] = tool
        step_info["command"] = command

        if parameters:
            step_info["parameters"] = parameters
        elif extra and "parameters" in extra:
            step_info["parameters"] = extra.pop("parameters")

        step_info["result"] = result or {}

        if extra:
            step_info.update(extra)

        self.steps.append(step_info)
        await self._append_to_traj_file(step_info)
        return step_info

    async def _append_to_traj_file(self, step_info: Dict[str, Any]):
        traj_file = self.trajectory_dir / "traj.jsonl"
        try:
            line = json.dumps(step_info, ensure_ascii=False, default=str)
            with open(traj_file, "a", encoding="utf-8") as f:
                f.write(line)
                f.write("\n")
        except Exception as e:
            logger.warning(f"Failed to append step {step_info.get('step', '?')} to traj.jsonl: {e}")

    def _save_metadata(self):
        metadata_file = self.trajectory_dir / "metadata.json"
        with open(metadata_file, "w", encoding="utf-8") as f:
            json.dump(self.metadata, f, indent=2, ensure_ascii=False)

    async def add_metadata(self, key: str, value: Any):
        self.metadata[key] = value
        self._save_metadata()

    async def finalize(self):
        self.metadata["end_time"] = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        self.metadata["total_steps"] = self.step_counter

        backend_counts: Dict[str, int] = {}
        for step in self.steps:
            backend = step.get("backend", "unknown")
            backend_counts[backend] = backend_counts.get(backend, 0) + 1
        self.metadata["backend_counts"] = backend_counts

        self._save_metadata()
        logger.info(f"Recording completed: {self.trajectory_dir} (steps: {self.step_counter})")

    def get_trajectory_dir(self) -> str:
        return str(self.trajectory_dir)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.finalize()
        return False


async def record_shell_step(
    recorder: TrajectoryRecorder,
    command: str,
    exit_code: int,
    stdout: Optional[str] = None,
    stderr: Optional[str] = None,
    tool: str = "shell_agent",
) -> Dict[str, Any]:
    stdout_brief = stdout[:200] + "..." if stdout and len(stdout) > 200 else stdout
    stderr_brief = stderr[:200] + "..." if stderr and len(stderr) > 200 else stderr
    result = {
        "status": "success" if exit_code == 0 else "error",
        "exit_code": exit_code,
        "stdout": stdout_brief,
        "stderr": stderr_brief,
    }
    return await recorder.record_step(backend="shell", tool=tool, command=command, result=result)


async def record_mcp_step(
    recorder: TrajectoryRecorder,
    server: str,
    tool_name: str,
    parameters: Dict[str, Any],
    result: Any,
) -> Dict[str, Any]:
    command = f"{server}.{tool_name}"
    result_str = str(result)
    result_brief = result_str[:200] + "..." if len(result_str) > 200 else result_str
    return await recorder.record_step(
        backend="mcp",
        tool=tool_name,
        command=command,
        result={"status": "success", "output": result_brief},
        parameters=parameters,
        extra={"server": server},
    )
