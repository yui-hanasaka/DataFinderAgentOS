import ast
import subprocess
import sys
import tempfile
from pathlib import Path

from tornado.ioloop import IOLoop

_BLOCKED_IMPORTS = frozenset(
    {
        "subprocess",
        "socket",
        "ctypes",
        "multiprocessing",
        "threading",
        "pickle",
        "shutil",
        "importlib",
        "inspect",
        "code",
        "sys",
        "os",
    }
)
_BLOCKED_CALLS = frozenset({"exec", "eval", "compile", "__import__"})
_BLOCKED_ATTRS = {("os", "system"), ("os", "popen")}
_DANGEROUS_IMPORT_NAMES = frozenset(
    {"system", "popen", "exec", "eval", "compile", "__import__"}
)
_DANGEROUS_GETATTR_TARGETS = frozenset({"system", "popen", "exec", "eval"})

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
            module_root = (node.module or "").split(".")[0]
            if module_root in _BLOCKED_IMPORTS:
                return f"禁止导入: {node.module}"
            # Block `from X import Y` where Y is a dangerous function name
            for alias in node.names:
                if alias.name in _DANGEROUS_IMPORT_NAMES:
                    return f"禁止导入危险名称: {alias.name} (from {node.module})"
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in _BLOCKED_CALLS:
                return f"禁止调用: {node.func.id}"
            if (
                isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and (node.func.value.id, node.func.attr) in _BLOCKED_ATTRS
            ):
                return f"禁止调用: {node.func.value.id}.{node.func.attr}"
            # Block getattr(blocked_module, 'dangerous_attr') pattern
            if isinstance(node.func, ast.Name) and node.func.id == "getattr":
                if len(node.args) >= 2:
                    first_arg = node.args[0]
                    second_arg = node.args[1]
                    if (
                        isinstance(first_arg, ast.Name)
                        and first_arg.id in _BLOCKED_IMPORTS
                        and isinstance(second_arg, ast.Constant)
                        and isinstance(second_arg.value, str)
                        and second_arg.value in _DANGEROUS_GETATTR_TARGETS
                    ):
                        return (
                            f"禁止调用: getattr({first_arg.id}, {second_arg.value!r})"
                        )
            # Block call via sys.modules[...].dangerous_function() pattern
            if (
                isinstance(node.func, ast.Attribute)
                and node.func.attr in _DANGEROUS_IMPORT_NAMES
                and isinstance(node.func.value, ast.Subscript)
                and isinstance(node.func.value.value, ast.Attribute)
                and node.func.value.value.attr == "modules"
                and isinstance(node.func.value.value.value, ast.Name)
                and node.func.value.value.value.id == "sys"
            ):
                return f"禁止调用: sys.modules[...]{node.func.attr}()"
        # Block globals()['__builtins__'] pattern
        if isinstance(node, ast.Subscript):
            if (
                isinstance(node.value, ast.Call)
                and isinstance(node.value.func, ast.Name)
                and node.value.func.id in ("globals", "locals")
                and isinstance(node.slice, ast.Constant)
                and isinstance(node.slice.value, str)
                and node.slice.value in ("__builtins__", "__builtin__")
            ):
                return f"禁止访问: {node.value.func.id}()[{node.slice.value!r}]"
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
