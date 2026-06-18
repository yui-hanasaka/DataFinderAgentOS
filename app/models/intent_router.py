"""Intent routing: decide direct agent_loop vs TaskAgent mode."""

from app.models.employee import EmployeeRepository

TASK_TRIGGERS: dict[str, dict] = {
    "/task": {"max_iterations": 8, "enable_reflection": True},
    "/深度分析": {"max_iterations": 6, "enable_reflection": True},
    "/批量处理": {"max_iterations": 10, "enable_reflection": False},
}


def route_message(user_text: str, employee_id: int | None) -> dict:
    """Returns routing decision with mode, cleaned_text, task_config."""
    for prefix, config in TASK_TRIGGERS.items():
        if user_text.startswith(prefix):
            cleaned = user_text[len(prefix) :].strip()
            return {
                "mode": "task_agent",
                "cleaned_text": cleaned or user_text,
                "task_config": dict(config),
            }

    if employee_id:
        emp = EmployeeRepository.get_employee_with_tools(employee_id)
        if emp and emp.get("force_task_agent"):
            return {
                "mode": "task_agent",
                "cleaned_text": user_text,
                "task_config": emp.get("task_config") or {"max_iterations": 8},
            }

    return {"mode": "direct", "cleaned_text": user_text, "task_config": {}}
