"""TaskPlanner — 유저 요청을 순차/병렬 Phase로 분해하는 실행 계획 엔진."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

from openai import AsyncOpenAI

PLANNER_SYSTEM_PROMPT = """You are a PM (Project Manager) for an AI team.

Your job: decompose the user's request into an execution plan with phases.
- Tasks that depend on each other must be in separate sequential phases.
- Tasks that are independent can be in the same parallel phase.

Respond ONLY with valid JSON in this exact format:
{
  "summary": "brief summary of the overall plan",
  "estimated_workers": ["worker_name1", "worker_name2"],
  "phases": [
    {
      "parallel": false,
      "tasks": [
        {
          "worker_name": "worker name from the list",
          "instruction": "specific, actionable instruction",
          "depends_on": []
        }
      ]
    },
    {
      "parallel": true,
      "tasks": [
        {
          "worker_name": "worker name",
          "instruction": "specific instruction",
          "depends_on": ["phase_0_task_0"]
        }
      ]
    }
  ]
}

Rules:
- Use "parallel": true only when tasks in that phase are truly independent.
- "depends_on" lists task IDs from previous phases (format: "phase_{i}_task_{j}").
- Keep phases minimal — merge tasks into the same phase if they don't depend on each other.
"""


@dataclass
class SubTask:
    worker_name: str
    instruction: str
    depends_on: list[str] = field(default_factory=list)


@dataclass
class Phase:
    parallel: bool
    tasks: list[SubTask]


@dataclass
class ExecutionPlan:
    phases: list[Phase]
    summary: str
    estimated_workers: list[str]


class TaskPlanner:
    """유저 요청 + 워커 목록 → ExecutionPlan (순차/병렬 Phase 분해)."""

    def __init__(self) -> None:
        self.client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))
        self.model = os.environ.get("PM_MODEL", "gpt-4o")

    async def plan(self, user_request: str, workers: list[dict]) -> ExecutionPlan:
        """유저 요청을 Phase 기반 실행 계획으로 분해.

        LLM 실패 시 폴백: 단일 Phase, 모든 태스크 순차 배치.
        """
        if not workers:
            return ExecutionPlan(phases=[], summary="워커 없음", estimated_workers=[])

        try:
            return await self._plan_with_llm(user_request, workers)
        except Exception:
            return self._fallback_plan(user_request, workers)

    async def _plan_with_llm(self, user_request: str, workers: list[dict]) -> ExecutionPlan:
        worker_list = "\n".join(
            f"- {w['name']} (engine: {w['engine']}): {w['description']}"
            for w in workers
        )
        user_content = f"""Available workers:
{worker_list}

User request:
{user_request}

Create an execution plan with phases."""

        resp = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0.2,
            response_format={"type": "json_object"},
        )

        content = resp.choices[0].message.content or "{}"
        data = json.loads(content)
        return _parse_plan(data)

    def _fallback_plan(self, user_request: str, workers: list[dict]) -> ExecutionPlan:
        """LLM 없을 때: 모든 워커에게 동일 요청을 순차 단일 Phase로."""
        tasks = [
            SubTask(
                worker_name=w["name"],
                instruction=f"다음 태스크를 처리해주세요: {user_request}",
            )
            for w in workers[:1]  # 폴백은 첫 번째 워커만
        ]
        return ExecutionPlan(
            phases=[Phase(parallel=False, tasks=tasks)],
            summary="폴백 계획 (LLM 미사용)",
            estimated_workers=[workers[0]["name"]] if workers else [],
        )


def _parse_plan(data: dict) -> ExecutionPlan:
    """LLM JSON 응답 → ExecutionPlan 객체."""
    phases: list[Phase] = []
    for phase_data in data.get("phases", []):
        tasks = [
            SubTask(
                worker_name=t.get("worker_name", ""),
                instruction=t.get("instruction", ""),
                depends_on=t.get("depends_on", []),
            )
            for t in phase_data.get("tasks", [])
        ]
        phases.append(Phase(parallel=bool(phase_data.get("parallel", False)), tasks=tasks))

    return ExecutionPlan(
        phases=phases,
        summary=data.get("summary", ""),
        estimated_workers=data.get("estimated_workers", []),
    )
