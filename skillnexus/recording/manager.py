"""RecordingManager — global singleton orchestrating all recording activity.

Manages:
  - TrajectoryRecorder  (traj.jsonl)
  - ActionRecorder      (agent_actions.jsonl)
  - Conversation log    (conversations.jsonl)

Ported from OpenSpace.  Video/screenshot platform clients removed —
SkillNexus is a pure API service without local GUI access.
"""

import datetime
import json
import ast
import types
from typing import Any, Dict, List, Optional
from pathlib import Path

from skillnexus.utils.logging import Logger
from .recorder import TrajectoryRecorder
from .action_recorder import ActionRecorder

logger = Logger.get_logger(__name__)


class RecordingManager:
    _global_instance: Optional["RecordingManager"] = None

    def __init__(
        self,
        enabled: bool = True,
        task_id: str = "",
        log_dir: str = "./logs/recordings",
        backends: Optional[List[str]] = None,
        enable_conversation_log: bool = True,
        auto_save_interval: int = 10,
        agent_name: str = "GroundingAgent",
    ):
        self.enabled = enabled
        self.task_id = task_id
        self.log_dir = log_dir
        self.backends = set(backends) if backends else {"mcp", "gui", "shell", "system", "web"}
        self.enable_conversation_log = enable_conversation_log
        self.auto_save_interval = auto_save_interval
        self.agent_name = agent_name

        self._recorder: Optional[TrajectoryRecorder] = None
        self._action_recorder: Optional[ActionRecorder] = None
        self._is_started = False
        self._step_counter = 0

        self._registered_llm_clients: list = []
        self._original_methods: dict = {}

        RecordingManager._global_instance = self

    # ── Status ──

    @classmethod
    def is_recording(cls) -> bool:
        return cls._global_instance is not None and cls._global_instance._is_started

    # ── Start / Stop ──

    async def start(self, task_id: Optional[str] = None):
        if task_id:
            self.task_id = task_id
        if not self.enabled or self._is_started:
            return

        try:
            self._recorder = TrajectoryRecorder(
                task_name=self.task_id,
                log_dir=self.log_dir,
            )
            self._action_recorder = ActionRecorder(
                trajectory_dir=Path(self._recorder.get_trajectory_dir())
            )

            await self._recorder.add_metadata("task_id", self.task_id)
            await self._recorder.add_metadata("backends", list(self.backends))
            await self._recorder.add_metadata("start_time", datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S"))

            self._is_started = True
            logger.info(f"Recording started: {self._recorder.get_trajectory_dir()}")

        except Exception as e:
            logger.error(f"Recording failed to start: {e}")
            raise

    async def stop(self):
        if not self.enabled or not self._is_started:
            return

        try:
            if self._recorder:
                await self._recorder.add_metadata("end_time", datetime.datetime.now().isoformat())
                await self._recorder.add_metadata("total_steps", self._step_counter)
                await self.generate_summary()
                await self._recorder.finalize()
                logger.info(f"Recording completed: {self._recorder.get_trajectory_dir()}")

            for client in self._registered_llm_clients:
                client_id = id(client)
                if client_id in self._original_methods:
                    try:
                        client.complete = self._original_methods[client_id]
                    except Exception as e:
                        logger.debug(f"Failed to restore original method for LLM client: {e}")
            self._registered_llm_clients.clear()
            self._original_methods.clear()

            self._is_started = False
            self._recorder = None
            self._action_recorder = None

        except Exception as e:
            logger.error(f"Recording failed to stop: {e}")

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.stop()
        return False

    # ── Properties ──

    @property
    def recording_status(self) -> bool:
        return self._is_started

    @property
    def trajectory_dir(self) -> Optional[str]:
        if self._recorder:
            return str(self._recorder.get_trajectory_dir())
        return None

    @property
    def step_count(self) -> int:
        return self._step_counter

    # ── Class-level recording methods (called via global instance) ──

    @classmethod
    async def record_retrieved_tools(
        cls,
        task_instruction: str,
        tools: List[Any],
        search_debug_info: Optional[Dict[str, Any]] = None,
    ):
        instance = cls._global_instance
        if not instance or not instance._is_started or not instance._recorder:
            return

        tool_info = []
        for tool in tools:
            info: Dict[str, Any] = {"name": getattr(tool, "name", str(tool))}
            runtime_info = getattr(tool, "_runtime_info", None)
            if runtime_info and hasattr(runtime_info, "backend"):
                info["backend"] = runtime_info.backend.value if hasattr(runtime_info.backend, "value") else str(runtime_info.backend)
                info["server_name"] = runtime_info.server_name
            elif hasattr(tool, "backend_type"):
                info["backend"] = tool.backend_type.value if hasattr(tool.backend_type, "value") else str(tool.backend_type)
            tool_info.append(info)

        metadata: Dict[str, Any] = {
            "instruction": task_instruction[:500],
            "count": len(tools),
            "tools": tool_info,
        }
        if search_debug_info:
            metadata["search_debug"] = {
                "search_mode": search_debug_info.get("search_mode", ""),
                "total_candidates": search_debug_info.get("total_candidates", 0),
                "mcp_count": search_debug_info.get("mcp_count", 0),
                "non_mcp_count": search_debug_info.get("non_mcp_count", 0),
                "llm_filter": search_debug_info.get("llm_filter", {}),
                "tool_scores": search_debug_info.get("tool_scores", []),
            }

        await instance._recorder.add_metadata("retrieved_tools", metadata)
        logger.info(f"Recorded {len(tools)} retrieved tools")

    @classmethod
    async def record_skill_selection(
        cls,
        selection_record: Dict[str, Any],
    ):
        instance = cls._global_instance
        if not instance or not instance._is_started or not instance._recorder:
            return

        await instance._recorder.add_metadata("skill_selection", selection_record)
        selected = selection_record.get("selected", [])
        method = selection_record.get("method", "unknown")
        logger.info(
            f"Recorded skill selection: {len(selected)} selected via {method} "
            f"(from {len(selection_record.get('available_skills', []))} available)"
        )

    @staticmethod
    def _truncate_messages(
        messages: List[Dict[str, Any]],
        max_content_length: int = 5000,
    ) -> List[Dict[str, Any]]:
        result = []
        for msg in messages:
            new_msg: Dict[str, Any] = {"role": msg.get("role", "unknown")}
            content = msg.get("content", "")

            if isinstance(content, str):
                if len(content) > max_content_length:
                    new_msg["content"] = content[:max_content_length] + f"... [truncated, total {len(content)} chars]"
                else:
                    new_msg["content"] = content
            elif isinstance(content, list):
                new_content = []
                for item in content:
                    if isinstance(item, dict):
                        if item.get("type") == "image":
                            new_content.append({"type": "image", "note": "[image data omitted]"})
                        elif item.get("type") == "text":
                            text = item.get("text", "")
                            if len(text) > max_content_length:
                                new_content.append({"type": "text", "text": text[:max_content_length] + f"... [truncated, total {len(text)} chars]"})
                            else:
                                new_content.append(item)
                        else:
                            new_content.append(item)
                    else:
                        new_content.append(item)
                new_msg["content"] = new_content
            else:
                new_msg["content"] = str(content)[:max_content_length]

            if "tool_calls" in msg:
                new_msg["tool_calls"] = msg["tool_calls"]
            result.append(new_msg)
        return result

    @classmethod
    async def record_conversation_setup(
        cls,
        setup_messages: List[Dict[str, Any]],
        tools: Optional[List] = None,
        max_content_length: int = 5000,
        agent_name: str = "GroundingAgent",
        extra: Optional[Dict[str, Any]] = None,
    ):
        instance = cls._global_instance
        if not instance or not instance._is_started or not instance._recorder:
            return
        if not getattr(instance, "enable_conversation_log", True):
            return

        record: Dict[str, Any] = {
            "type": "setup",
            "agent_name": agent_name,
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "messages": cls._truncate_messages(setup_messages, max_content_length),
        }
        if extra:
            record["extra"] = extra

        if tools:
            _BACKEND_LABELS = {
                "mcp": "MCP", "shell": "Shell", "gui": "GUI",
                "web": "Web", "system": "System",
            }
            tool_defs = []
            for t in tools:
                schema = getattr(t, "schema", None)
                if schema:
                    backend_val = getattr(schema, "backend_type", None)
                    backend_str = (
                        backend_val.value if hasattr(backend_val, "value")
                        else str(backend_val) if backend_val else None
                    )
                    entry: Dict[str, Any] = {"name": schema.name, "backend": backend_str}
                    if schema.description:
                        desc = schema.description
                        if backend_str and backend_str not in ("not_set",):
                            label = _BACKEND_LABELS.get(backend_str, backend_str)
                            desc = f"[{label}] {desc}"
                        if len(desc) > 200:
                            desc = desc[:200] + "..."
                        entry["description"] = desc
                else:
                    entry = {"name": getattr(t, "name", str(t))}
                tool_defs.append(entry)
            record["tools"] = tool_defs

        conv_file = instance._recorder.trajectory_dir / "conversations.jsonl"
        try:
            with open(conv_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False))
                f.write("\n")
        except Exception as e:
            logger.debug(f"Failed to write conversation setup: {e}")

    @classmethod
    async def record_iteration_context(
        cls,
        iteration: int,
        delta_messages: List[Dict[str, Any]],
        response_metadata: Dict[str, Any],
        max_content_length: int = 5000,
        agent_name: str = "GroundingAgent",
        extra: Optional[Dict[str, Any]] = None,
    ):
        instance = cls._global_instance
        if not instance or not instance._is_started or not instance._recorder:
            return
        if not getattr(instance, "enable_conversation_log", True):
            return

        record = {
            "type": "iteration",
            "agent_name": agent_name,
            "iteration": iteration,
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "response_metadata": response_metadata,
            "delta_messages": cls._truncate_messages(delta_messages, max_content_length),
        }
        if extra:
            record["extra"] = extra

        conv_file = instance._recorder.trajectory_dir / "conversations.jsonl"
        try:
            with open(conv_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False))
                f.write("\n")
        except Exception as e:
            logger.debug(f"Failed to write conversation log: {e}")

    @classmethod
    async def record_tool_execution(
        cls,
        tool_name: str,
        backend: str,
        parameters: Dict[str, Any],
        result: Any,
        server_name: Optional[str] = None,
        is_success: bool = True,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        if not cls._global_instance or not cls._global_instance._is_started:
            return

        instance = cls._global_instance

        if backend == "not_set" or backend not in instance.backends:
            inferred = cls._infer_backend_from_tool_name(tool_name)
            if inferred and inferred in instance.backends:
                backend = inferred
            elif backend not in instance.backends:
                logger.debug(
                    f"Backend '{backend}' not in recording backends {instance.backends}, "
                    f"skipping recording for tool '{tool_name}'"
                )
                return

        class MockFunctionCall:
            def __init__(self, name, arguments):
                self.name = name
                self.arguments = arguments

        class MockToolCall:
            def __init__(self, name, arguments):
                self.function = MockFunctionCall(name, arguments)

        class MockResult:
            def __init__(self, content, is_success=True, metadata=None):
                self.content = content
                self.is_success = is_success
                self.is_error = not is_success
                self.error = content if not is_success else None
                self.metadata = metadata or {}

        tool_call = MockToolCall(tool_name, parameters)
        mock_result = MockResult(result, is_success=is_success, metadata=metadata)

        try:
            if backend == "mcp":
                server = server_name or "unknown"
                await instance._record_mcp(tool_call, mock_result, server)
            elif backend == "gui":
                await instance._record_gui(tool_call, mock_result)
            elif backend == "shell":
                await instance._record_shell(tool_call, mock_result)
            elif backend == "system":
                await instance._record_system(tool_call, mock_result)
            elif backend == "web":
                await instance._record_web(tool_call, mock_result)
            else:
                logger.warning(f"No recording handler for backend '{backend}', tool '{tool_name}'")
                return

            instance._step_counter += 1
        except Exception as e:
            logger.warning(f"Failed to record tool execution for {tool_name}: {e}")

    # ── Argument parsing ──

    @staticmethod
    def _parse_arguments(arg_data):
        if not isinstance(arg_data, str):
            return arg_data or {}
        try:
            return json.loads(arg_data)
        except json.JSONDecodeError:
            pass
        try:
            return ast.literal_eval(arg_data)
        except Exception:
            logger.debug("Failed to parse arguments, returning raw string")
            return {"raw": arg_data}

    @staticmethod
    def _infer_backend_from_tool_name(tool_name: str) -> Optional[str]:
        if not tool_name or not isinstance(tool_name, str):
            return None
        name = tool_name.strip()
        if "__" in name:
            name = name.rsplit("__", 1)[-1]
        shell_tools = {"shell_agent", "read_file", "write_file", "list_dir", "run_shell"}
        if name in shell_tools:
            return "shell"
        if name in ("gui_agent",) or "gui" in name.lower():
            return "gui"
        if "mcp" in name.lower() or ("." in name and "__" not in name):
            return "mcp"
        if name in ("deep_research_agent", "deep_research"):
            return "web"
        return None

    # ── LLM client registration (auto-record tool results) ──

    def register_to_llm(self, llm_client):
        if not self.enabled:
            return
        if id(llm_client) in self._original_methods:
            return
        original_complete = llm_client.complete
        self._original_methods[id(llm_client)] = original_complete

        async def wrapped_complete(self_client, *args, **kwargs):
            response = await original_complete(*args, **kwargs)
            if response.get("tool_results"):
                await self._auto_record_tool_results(response["tool_results"])
            return response

        llm_client.complete = types.MethodType(wrapped_complete, llm_client)
        self._registered_llm_clients.append(llm_client)

    async def _auto_record_tool_results(self, tool_results: List[Dict]):
        if not self._recorder or not self._is_started:
            return
        for tool_result in tool_results:
            tool_call = tool_result.get("tool_call")
            result = tool_result.get("result")
            backend = tool_result.get("backend")
            server_name = tool_result.get("server_name")

            if not tool_call or not result:
                continue
            if not backend:
                _name = getattr(getattr(tool_call, "function", None), "name", None) or str(tool_result.get("tool_call", ""))
                backend = self._infer_backend_from_tool_name(_name)
                if not backend:
                    logger.warning(f"Tool result missing 'backend', cannot infer for '{_name}', skipping")
                    continue

            result_metadata = result.metadata if hasattr(result, "metadata") else None
            await RecordingManager.record_tool_execution(
                tool_name=tool_call.function.name,
                backend=backend,
                parameters=self._parse_arguments(tool_call.function.arguments),
                result=result.content if hasattr(result, "content") else str(result),
                server_name=server_name,
                is_success=result.is_success if hasattr(result, "is_success") else True,
                metadata=result_metadata,
            )

    # ── Backend-specific recording ──

    async def _record_mcp(self, tool_call, result, server: str):
        tool_name = tool_call.function.name
        parameters = self._parse_arguments(tool_call.function.arguments)
        command = f"{server}.{tool_name}"
        result_str = str(result.content) if result.is_success else str(result.error)
        result_brief = result_str[:200] + "..." if len(result_str) > 200 else result_str
        is_actual_success = result.is_success and not result_str.startswith("ERROR:")

        step_info = await self._recorder.record_step(
            backend="mcp",
            tool=tool_name,
            command=command,
            result={"status": "success" if is_actual_success else "error", "output": result_brief},
            parameters=parameters,
            extra={"server": server},
        )
        step_info["agent_name"] = self.agent_name

    async def _record_gui(self, tool_call, result):
        tool_name = tool_call.function.name
        parameters = self._parse_arguments(tool_call.function.arguments)
        command = "gui_agent"
        if result.is_success and hasattr(result, "metadata") and result.metadata:
            action_history = result.metadata.get("action_history", [])
            if action_history:
                for action in reversed(action_history):
                    planned_action = action.get("planned_action", {})
                    execution_result = action.get("execution_result", {})
                    if planned_action.get("action_type") == "PYAUTOGUI_COMMAND":
                        cmd = planned_action.get("command", "")
                        if cmd and execution_result.get("status") == "success":
                            command = cmd
                            break
                    elif execution_result.get("status") == "success":
                        action_type = planned_action.get("action_type", "")
                        if action_type and action_type not in ["WAIT", "DONE", "FAIL"]:
                            params = planned_action.get("parameters", {})
                            if params:
                                param_str = ", ".join([f"{k}={v}" for k, v in list(params.items())[:2]])
                                command = f"{action_type}({param_str})"
                            else:
                                command = action_type
                            break

        result_str = str(result.content) if result.is_success else str(result.error)
        is_actual_success = result.is_success
        if result.is_success:
            first_200_chars = result_str[:200] if result_str else ""
            critical_failure_patterns = ["Task failed", "CRITICAL ERROR:", "FATAL:"]
            is_actual_success = not any(p in first_200_chars for p in critical_failure_patterns)

        extra = {}
        if hasattr(result, "metadata") and result.metadata:
            intermediate_steps = result.metadata.get("intermediate_steps")
            if intermediate_steps:
                extra["intermediate_steps"] = intermediate_steps

        step_info = await self._recorder.record_step(
            backend="gui",
            tool="gui_agent",
            command=command,
            result={"status": "success" if is_actual_success else "error", "output": result_str},
            parameters=parameters,
            extra=extra if extra else None,
        )
        step_info["agent_name"] = self.agent_name

    async def _record_shell(self, tool_call, result):
        tool_name = tool_call.function.name
        parameters = self._parse_arguments(tool_call.function.arguments)
        task = parameters.get("task", tool_name)
        exit_code = 0 if result.is_success else 1
        stdout = str(result.content) if result.is_success else ""
        stderr = str(result.error) if result.is_error else ""
        command = task

        if hasattr(result, "metadata") and result.metadata:
            code_history = result.metadata.get("code_history", [])
            if code_history:
                found_success = False
                for code_info in reversed(code_history):
                    if code_info.get("status") == "success":
                        lang = code_info.get("lang", "bash")
                        code = code_info.get("code", "")
                        command = f"```{lang}\n{code}\n```"
                        found_success = True
                        break
                if not found_success and code_history:
                    last_code = code_history[-1]
                    lang = last_code.get("lang", "bash")
                    code = last_code.get("code", "")
                    command = f"```{lang}\n{code}\n```"

        stdout_brief = stdout[:200] + "..." if len(stdout) > 200 else stdout
        stderr_brief = stderr[:200] + "..." if len(stderr) > 200 else stderr

        is_actual_success = result.is_success
        if result.is_success:
            first_500_chars = stdout[:500] if stdout else ""
            critical_failure_patterns = ["Task failed after", "[TASK_FAILED:", "EXECUTION ERROR", "timed out"]
            is_actual_success = not any(p in first_500_chars for p in critical_failure_patterns)

        step_info = await self._recorder.record_step(
            backend="shell",
            tool="shell_agent",
            command=command,
            result={
                "status": "success" if is_actual_success else "error",
                "exit_code": exit_code,
                "stdout": stdout_brief,
                "stderr": stderr_brief,
            },
        )
        step_info["agent_name"] = self.agent_name

    async def _record_system(self, tool_call, result):
        tool_name = tool_call.function.name
        parameters = self._parse_arguments(tool_call.function.arguments)
        command = tool_name
        if parameters:
            key_params = []
            for key in ["path", "file", "directory", "name", "provider", "backend"]:
                if key in parameters and parameters[key]:
                    key_params.append(f"{parameters[key]}")
            if key_params:
                command = f"{tool_name}({', '.join(key_params[:2])})"

        result_str = str(result.content) if result.is_success else str(result.error)
        result_brief = result_str[:200] + "..." if len(result_str) > 200 else result_str
        is_actual_success = result.is_success
        if result.is_success and result_str:
            is_actual_success = not result_str.startswith("ERROR:")

        step_info = await self._recorder.record_step(
            backend="system",
            tool=tool_name,
            command=command,
            result={"status": "success" if is_actual_success else "error", "output": result_brief},
        )
        step_info["agent_name"] = self.agent_name

    async def _record_web(self, tool_call, result):
        tool_name = tool_call.function.name
        parameters = self._parse_arguments(tool_call.function.arguments)
        query = parameters.get("query", "")
        command = query if query else "deep_research"
        result_str = str(result.content) if result.is_success else str(result.error)
        is_actual_success = result.is_success
        if result.is_success and result_str:
            is_actual_success = not result_str.startswith("ERROR:")

        step_info = await self._recorder.record_step(
            backend="web",
            tool="deep_research_agent",
            command=command,
            result={"status": "success" if is_actual_success else "error", "output": result_str},
        )
        step_info["agent_name"] = self.agent_name

    # ── Metadata / plans / decisions ──

    async def add_metadata(self, key: str, value: Any):
        if self._recorder:
            await self._recorder.add_metadata(key, value)

    async def save_execution_outcome(
        self,
        status: str,
        iterations: int,
        execution_time: float = 0,
    ) -> None:
        if self._recorder:
            await self._recorder.add_metadata("execution_outcome", {
                "status": status,
                "iterations": iterations,
                "execution_time": round(execution_time, 2),
            })

    async def save_plan(self, plan: Dict[str, Any], agent_name: str = "GroundingAgent"):
        if not self._recorder or not self._is_started:
            logger.warning("Cannot save plan: recording not started")
            return
        try:
            plan_dir = Path(self._recorder.get_trajectory_dir()) / "plans"
            plan_dir.mkdir(exist_ok=True)
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            plan_data = {
                "version": timestamp,
                "created_at": datetime.datetime.now().isoformat(),
                "created_by": agent_name,
                "plan": plan,
            }
            plan_file = plan_dir / f"plan_{timestamp}.json"
            with open(plan_file, "w", encoding="utf-8") as f:
                json.dump(plan_data, f, indent=2, ensure_ascii=False)
            current_plan_file = plan_dir / "current_plan.json"
            with open(current_plan_file, "w", encoding="utf-8") as f:
                json.dump(plan_data, f, indent=2, ensure_ascii=False)
            logger.debug(f"Saved plan to recording: {plan_file.name}")
        except Exception as e:
            logger.error(f"Failed to save plan: {e}")

    async def log_decision(
        self,
        agent_name: str,
        decision: str,
        context: Optional[Dict[str, Any]] = None,
    ):
        if not self._recorder or not self._is_started:
            logger.warning("Cannot log decision: recording not started")
            return
        try:
            traj_dir = Path(self._recorder.get_trajectory_dir())
            log_file = traj_dir / "decisions.log"
            timestamp = datetime.datetime.now().isoformat()
            log_entry = f"[{timestamp}] {agent_name}: {decision}"
            if context:
                log_entry += f"\n  Context: {json.dumps(context, ensure_ascii=False)}"
            log_entry += "\n"
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(log_entry)
            logger.debug(f"Logged decision from {agent_name}")
        except Exception as e:
            logger.error(f"Failed to log decision: {e}")

    async def record_agent_action(
        self,
        agent_name: str,
        action_type: str,
        input_data: Optional[Dict[str, Any]] = None,
        reasoning: Optional[Dict[str, Any]] = None,
        output_data: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        related_tool_steps: Optional[list] = None,
        correlation_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        if not self._action_recorder or not self._is_started:
            logger.debug("Cannot record agent action: recording not started")
            return None
        try:
            action_info = await self._action_recorder.record_action(
                agent_name=agent_name,
                action_type=action_type,
                input_data=input_data,
                reasoning=reasoning,
                output_data=output_data,
                metadata=metadata,
                related_tool_steps=related_tool_steps,
                correlation_id=correlation_id,
            )
            logger.debug(f"Recorded agent action: {agent_name} - {action_type}")
            return action_info
        except Exception as e:
            logger.error(f"Failed to record agent action: {e}")
            return None

    # ── Summary ──

    async def generate_summary(self) -> Dict[str, Any]:
        if not self._recorder or not self._is_started:
            logger.warning("Cannot generate summary: recording not started")
            return {}
        try:
            from .action_recorder import load_agent_actions, analyze_agent_actions
            from .utils import load_trajectory_from_jsonl, analyze_trajectory

            traj_dir = self._recorder.get_trajectory_dir()
            trajectory = load_trajectory_from_jsonl(f"{traj_dir}/traj.jsonl")
            agent_actions = load_agent_actions(traj_dir)
            traj_stats = analyze_trajectory(trajectory)
            action_stats = analyze_agent_actions(agent_actions)

            summary = {
                "task_id": self.task_id,
                "start_time": self._recorder.metadata.get("start_time", ""),
                "end_time": self._recorder.metadata.get("end_time", ""),
                "trajectory": {
                    "total_steps": traj_stats.get("total_steps", 0),
                    "success_count": traj_stats.get("success_count", 0),
                    "success_rate": traj_stats.get("success_rate", 0),
                    "by_backend": traj_stats.get("backends", {}),
                    "by_tool": traj_stats.get("tools", {}),
                },
                "agent_actions": {
                    "total_actions": action_stats.get("total_actions", 0),
                    "by_agent": action_stats.get("by_agent", {}),
                    "by_type": action_stats.get("by_type", {}),
                },
            }

            summary_file = Path(traj_dir) / "summary.json"
            with open(summary_file, "w", encoding="utf-8") as f:
                json.dump(summary, f, indent=2, ensure_ascii=False)

            logger.info(f"Generated summary: {summary_file}")
            return summary
        except Exception as e:
            logger.error(f"Failed to generate summary: {e}")
            return {}


__all__ = ["RecordingManager"]
