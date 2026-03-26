"""路径白名单守卫 — 拦截 Agent 向非法路径写入文件"""

from __future__ import annotations

import logging
import os
import re
import shlex
from pathlib import Path

logger = logging.getLogger(__name__)

# write_file / append_file 中需要校验的参数名
_FILE_PATH_PARAMS: dict[str, list[str]] = {
    "write_file": ["path"],
    "append_file": ["path"],
    "edit_file": ["path"],
    "clone_repo": ["target_dir"],
    "claude_write_module": ["working_dir"],
    "claude_fix_error": ["working_dir"],
    "claude_review": ["working_dir"],
}

# run_command 类工具（需要从命令字符串中提取写目标）
_COMMAND_TOOLS: set[str] = {"run_command"}

# 从 shell 命令中提取写目标路径的正则
_WRITE_PATH_PATTERNS: list[re.Pattern] = [
    # >file, >>file, > file, >> file
    re.compile(r">{1,2}\s*([^\s;&|]+)"),
    # tee file, tee -a file
    re.compile(r"\btee\s+(?:-[a-z]+\s+)*([^\s;&|]+)"),
    # mkdir -p path（可能创建到错误位置）
    re.compile(r"\bmkdir\s+(?:-[a-z]+\s+)*(.+?)(?:\s*[;&|]|$)"),
    # wget -O path, curl -o path
    re.compile(r"\b(?:wget|curl)\b.*?-[oO]\s*([^\s;&|]+)"),
    # cp/mv ... dest（取最后一个参数）
    re.compile(r"\b(?:cp|mv)\s+(?:-[a-z]+\s+)*(?:\S+\s+)+(\S+)"),
    # touch path
    re.compile(r"\btouch\s+([^\s;&|]+)"),
]


class PathGuard:
    """路径白名单校验器。所有写操作路径必须位于 allowed_dirs 之下。"""

    def __init__(self, allowed_dirs: list[str | Path]):
        self._allowed = [Path(d).resolve() for d in allowed_dirs if d]

    @property
    def allowed(self) -> list[Path]:
        return list(self._allowed)

    def is_allowed(self, path: str | Path) -> bool:
        """检查路径是否在白名单目录下"""
        if not self._allowed:
            return True  # 无白名单 = 不限制
        resolved = Path(path).resolve()
        return any(
            resolved == d or resolved.is_relative_to(d)
            for d in self._allowed
        )

    def check(self, path: str | Path) -> tuple[bool, str]:
        """校验单个路径。返回 (通过, 错误信息)。"""
        if not path:
            return True, ""
        if self.is_allowed(path):
            return True, ""
        return False, self._violation_msg(str(path))

    def check_command(self, command: str) -> tuple[bool, str]:
        """从 shell 命令中提取写目标路径并校验。

        最佳实践：只拦截明显违规，减少误报。
        """
        if not self._allowed or not command:
            return True, ""

        violations = []
        for pattern in _WRITE_PATH_PATTERNS:
            for match in pattern.finditer(command):
                raw = match.group(1).strip().strip("'\"")
                # 跳过明显的非路径（如 &&, ||, ;）
                if not raw or raw.startswith("-"):
                    continue
                # mkdir -p 可能有多个路径，按空格拆分
                if "mkdir" in pattern.pattern:
                    for part in shlex.split(raw):
                        if part.startswith("-"):
                            continue
                        if not self.is_allowed(part):
                            violations.append(part)
                else:
                    if not self.is_allowed(raw):
                        violations.append(raw)

        if violations:
            return False, self._violation_msg_multi(violations)
        return True, ""

    def _violation_msg(self, path: str) -> str:
        dirs = "\n".join(f"  - {d}" for d in self._allowed)
        return (
            f"PATH_VIOLATION: 路径 '{path}' 不在允许的目录范围内。\n"
            f"允许的目录:\n{dirs}\n"
            f"请使用上述目录下的路径重试。"
        )

    def _violation_msg_multi(self, paths: list[str]) -> str:
        dirs = "\n".join(f"  - {d}" for d in self._allowed)
        bad = "\n".join(f"  - {p}" for p in paths)
        return (
            f"PATH_VIOLATION: 以下路径不在允许的目录范围内:\n{bad}\n"
            f"允许的目录:\n{dirs}\n"
            f"请使用上述目录下的路径重试。"
        )


def make_guarded_handler(tool_name: str, handler, guard: PathGuard):
    """为写操作工具创建带路径校验的包装函数。

    Args:
        tool_name: 工具名称（用于匹配校验规则）
        handler: 原始工具函数
        guard: PathGuard 实例

    Returns:
        包装后的函数，路径违规时直接返回错误字符串
    """
    params_to_check = _FILE_PATH_PARAMS.get(tool_name)
    is_command_tool = tool_name in _COMMAND_TOOLS

    # 不需要包装的工具直接返回原函数
    if not params_to_check and not is_command_tool:
        return handler

    def guarded(**kwargs):
        # 检查文件路径参数
        if params_to_check:
            for param in params_to_check:
                val = kwargs.get(param)
                if val:
                    ok, msg = guard.check(val)
                    if not ok:
                        logger.warning(f"PathGuard blocked {tool_name}({param}={val})")
                        return msg

        # 检查 shell 命令中的写目标
        if is_command_tool:
            cmd = kwargs.get("command", "")
            ok, msg = guard.check_command(cmd)
            if not ok:
                logger.warning(f"PathGuard blocked {tool_name}: {cmd[:120]}")
                return msg

        return handler(**kwargs)

    guarded.__name__ = f"guarded_{handler.__name__}"
    guarded.__doc__ = handler.__doc__
    return guarded
