import ast
import subprocess
import sys
import tempfile
from pathlib import Path

from tornado.ioloop import IOLoop

_BLOCKED_IMPORTS = frozenset(
    {"subprocess", "socket", "ctypes", "multiprocessing", "threading"}
)
_BLOCKED_CALLS = frozenset({"exec", "eval", "compile", "__import__"})
_BLOCKED_ATTRS = {("os", "system"), ("os", "popen")}

_STDOUT_LIMIT = 8 * 1024
_STDERR_LIMIT = 2 * 1024


def _check_ast(code: str) -> str | None:
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return f"语法错误: {exc}"

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in _BLOCKED_IMPORTS:
                    return f"禁止导入: {alias.name}"
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] in _BLOCKED_IMPORTS:
                return f"禁止导入: {node.module}"
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in _BLOCKED_CALLS:
                return f"禁止调用: {node.func.id}"
            if (
                isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and (node.func.value.id, node.func.attr) in _BLOCKED_ATTRS
            ):
                return f"禁止调用: {node.func.value.id}.{node.func.attr}"
    return None


def _run_sync(code: str, timeout: int) -> str:
    err = _check_ast(code)
    if err:
        return f"代码检查未通过: {err}"

    with tempfile.TemporaryDirectory() as tmpdir:
        script = Path(tmpdir) / "code.py"
        script.write_text(code, encoding="utf-8")
        try:
            result = subprocess.run(
                [sys.executable, str(script)],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=tmpdir,
            )
        except subprocess.TimeoutExpired:
            return f"执行超时（>{timeout}s）"

    stdout = result.stdout[:_STDOUT_LIMIT]
    stderr = result.stderr[:_STDERR_LIMIT]
    parts = []
    if stdout:
        parts.append(stdout)
    if stderr:
        parts.append(f"[stderr]\n{stderr}")
    return "\n".join(parts) if parts else "(无输出)"


async def execute(code: str, timeout: int = 15) -> str:
    return await IOLoop.current().run_in_executor(None, _run_sync, code, timeout)
