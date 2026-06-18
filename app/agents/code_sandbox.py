import ast
import subprocess
import sys
import time
from pathlib import Path

from tornado.ioloop import IOLoop

# Modules blocked entirely — cannot be imported at all
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
    }
)
_BLOCKED_CALLS = frozenset({"exec", "eval", "compile", "__import__"})
# (module, attr) pairs blocked on any variable name
_BLOCKED_ATTRS = {
    ("os", "system"),
    ("os", "popen"),
    ("os", "remove"),
    ("os", "rmdir"),
    ("os", "unlink"),
    ("os", "removedirs"),
    ("os", "rename"),
    ("os", "chmod"),
    ("os", "chown"),
    ("os", "kill"),
    ("os", "fork"),
    ("os", "spawnl"),
    ("os", "spawnle"),
    ("os", "spawnlp"),
    ("os", "spawnv"),
    ("os", "spawnve"),
    ("os", "spawnvp"),
    ("os", "execl"),
    ("os", "execle"),
    ("os", "execlp"),
    ("os", "execlpe"),
    ("os", "execv"),
    ("os", "execve"),
    ("os", "execvp"),
    ("os", "execvpe"),
}
_DANGEROUS_IMPORT_NAMES = frozenset(
    {
        "system",
        "popen",
        "exec",
        "eval",
        "compile",
        "__import__",
        "remove",
        "rmdir",
        "unlink",
        "removedirs",
        "rename",
        "chmod",
        "chown",
        "kill",
        "fork",
        "spawnl",
        "spawnle",
        "spawnlp",
        "spawnv",
        "spawnve",
        "spawnvp",
        "execl",
        "execle",
        "execlp",
        "execlpe",
        "execv",
        "execve",
        "execvp",
        "execvpe",
    }
)
_DANGEROUS_GETATTR_TARGETS = frozenset(
    {"system", "popen", "exec", "eval", "remove", "rmdir", "unlink", "kill", "fork"}
)

_STDOUT_LIMIT = 8 * 1024
_STDERR_LIMIT = 2 * 1024

# Persistent workspace for agent scripts and files
_WORKSPACE_ROOT = Path(__file__).parent.parent.parent / "temp" / "agent_workspace"


def _ensure_workspace() -> Path:
    """Create workspace subdirectories and return root."""
    for sub in ("scripts", "downloads", "output"):
        (_WORKSPACE_ROOT / sub).mkdir(parents=True, exist_ok=True)
    return _WORKSPACE_ROOT


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

    _ensure_workspace()
    # Each execution gets a timestamped subdirectory for isolation,
    # but all under the persistent workspace so files survive across turns.
    ts = str(int(time.time() * 1_000_000))
    workdir = _WORKSPACE_ROOT / "scripts" / ts
    workdir.mkdir(parents=True, exist_ok=True)
    script = workdir / "code.py"
    script.write_text(code, encoding="utf-8")
    try:
        result = subprocess.run(
            [sys.executable, str(script)],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=workdir,
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
    if not parts:
        return "(无输出)"
    # Append the workspace path so the agent knows where files are
    parts.append(f"\n[workspace] {workdir}")
    return "\n".join(parts)


async def execute(code: str, timeout: int = 15) -> str:
    return await IOLoop.current().run_in_executor(None, _run_sync, code, timeout)
