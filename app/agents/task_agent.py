"""TaskAgent — autonomous multi-step agent with planning + concurrent execution."""

import asyncio
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.models.errors import log_error


class TaskState(Enum):
    PLANNING = "planning"
    EXECUTING = "executing"
    VALIDATING = "validating"
    REFLECTING = "reflecting"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class SubTask:
    id: str
    description: str
    tool_name: str
    args: dict[str, Any]
    dependencies: list[str] = field(default_factory=list)
    status: str = "pending"
    result: Any = None
    error: str | None = None


class TaskAgent:
    def __init__(
        self,
        user_text: str,
        model_row: dict[str, Any],
        allowed_tools: list[str] | None = None,
        max_iterations: int = 8,
        enable_reflection: bool = True,
        stream_cb: Any = None,
    ) -> None:
        self.user_text = user_text
        self.model_row = model_row
        self.allowed_tools = allowed_tools
        self.max_iterations = max_iterations
        self.enable_reflection = enable_reflection
        self.stream_cb = stream_cb
        self.state = TaskState.PLANNING
        self.tasks: list[SubTask] = []
        self.iteration = 0

    async def _emit(self, event_type: str, data: Any) -> None:
        if self.stream_cb:
            try:
                await self.stream_cb(event_type, data)
            except Exception:
                pass

    async def run(self) -> str:
        while self.iteration < self.max_iterations:
            self.iteration += 1
            if self.state == TaskState.PLANNING:
                await self._planning_phase()
            elif self.state == TaskState.EXECUTING:
                await self._executing_phase()
            elif self.state == TaskState.VALIDATING:
                await self._validating_phase()
            elif self.state == TaskState.REFLECTING:
                await self._reflecting_phase()
            elif self.state == TaskState.COMPLETED:
                return self._format_result()
            elif self.state == TaskState.FAILED:
                failed = [t for t in self.tasks if t.status == "failed"]
                reasons = "; ".join(t.error or "未知" for t in failed[:3])
                return f"任务失败: {reasons}"
            await asyncio.sleep(0.05)
        return "任务达到最大迭代次数限制"

    def _build_tools_desc(self) -> str:
        from app.agents.tool_registry import TOOLS

        tools = TOOLS
        if self.allowed_tools is not None:
            tools = [t for t in TOOLS if t["function"]["name"] in self.allowed_tools]
        lines = [
            f"- {t['function']['name']}: {t['function']['description']}" for t in tools
        ]
        return "\n".join(lines)

    async def _planning_phase(self) -> None:
        await self._emit("planning", "分析任务并制定执行计划...")
        tools_desc = self._build_tools_desc()
        prompt = (
            f"你是任务规划专家。用户需求:\n{self.user_text}\n\n"
            f"可用工具:\n{tools_desc}\n\n"
            "请将需求分解为子任务，返回纯JSON（不要markdown标记）:\n"
            '{"tasks":[{"id":"task_1","description":"...","tool_name":"...","args":{...},"dependencies":[]}]}'
        )
        try:
            from app.models.model_client import chat_complete, parse_chat_response

            resp = await chat_complete(
                str(self.model_row["base_url"]),
                str(self.model_row["api_key"]),
                str(self.model_row["model_id"]),
                [{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=2048,
                stream=False,
            )
            raw = await resp.aread()
            parsed = parse_chat_response(raw)
            content = str(parsed.get("content", "{}")).strip()
            content = (
                content.removeprefix("```json")
                .removeprefix("```")
                .removesuffix("```")
                .strip()
            )
            plan: dict = json.loads(content)
            for td in plan.get("tasks", []):
                tname = td.get("tool_name", "")
                if self.allowed_tools and tname not in self.allowed_tools:
                    continue
                self.tasks.append(
                    SubTask(
                        id=td.get("id", f"task_{len(self.tasks) + 1}"),
                        description=td.get("description", ""),
                        tool_name=tname,
                        args=td.get("args", {}),
                        dependencies=td.get("dependencies", []),
                    )
                )
            await self._emit("plan_ready", f"计划完成: {len(self.tasks)}个子任务")
            self.state = TaskState.EXECUTING
        except Exception as e:
            log_error("TaskAgent._planning_phase", e)
            await self._emit("error", f"规划失败: {e}")
            self.state = TaskState.FAILED

    async def _executing_phase(self) -> None:
        await self._emit("executing", f"执行{len(self.tasks)}个子任务...")
        from app.agents.concurrent_executor import ConcurrentExecutor
        from app.agents.tool_executor import execute as tool_execute

        executor = ConcurrentExecutor("dynamic")
        completed_ids: set[str] = set()
        pending = list(self.tasks)

        while pending:
            ready = [
                t for t in pending if all(d in completed_ids for d in t.dependencies)
            ]
            if not ready:
                for t in pending:
                    t.status = "failed"
                    t.error = "依赖无法满足"
                break

            async def _run_one(t: SubTask) -> dict:
                t.status = "running"
                await self._emit("task_start", f"开始: {t.description}")
                try:
                    t.result = await tool_execute(t.tool_name, t.args)
                    t.status = "completed"
                    await self._emit("task_done", f"完成: {t.description}")
                except Exception as e:
                    t.status = "failed"
                    t.error = str(e)
                    await self._emit("task_fail", f"失败: {t.description} - {e}")
                return {"ok": t.status == "completed", "error": t.error}

            await executor.run_concurrent([_run_one(t) for t in ready])
            for t in ready:
                completed_ids.add(t.id)
                pending.remove(t)

        failed = [t for t in self.tasks if t.status == "failed"]
        self.state = (
            TaskState.REFLECTING
            if (failed and self.enable_reflection)
            else TaskState.VALIDATING
        )

    async def _validating_phase(self) -> None:
        failed = [t for t in self.tasks if t.status == "failed"]
        if failed:
            await self._emit("validation", f"{len(failed)}个子任务失败")
            self.state = (
                TaskState.REFLECTING if self.enable_reflection else TaskState.FAILED
            )
        else:
            completed = [t for t in self.tasks if t.status == "completed"]
            await self._emit("validation", f"所有{len(completed)}个子任务完成")
            self.state = TaskState.COMPLETED

    async def _reflecting_phase(self) -> None:
        if self.iteration >= self.max_iterations - 1:
            await self._emit("reflection", "已达最大迭代次数")
            self.state = TaskState.COMPLETED
            return
        for t in self.tasks:
            if t.status == "failed":
                t.status = "pending"
                t.error = None
        await self._emit("reflection", "重试失败的任务")
        self.state = TaskState.EXECUTING

    def _format_result(self) -> str:
        parts: list[str] = []
        for t in self.tasks:
            if t.status == "completed":
                parts.append(f"## {t.description}\n{str(t.result)[:500]}")
        return "\n\n".join(parts) if parts else "任务完成，但无有效结果"
