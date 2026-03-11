"""Shell 命令执行工具"""
import subprocess


def run_command(command: str, timeout: int = 300) -> str:
    """执行 shell 命令并返回结果"""
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = ""
        if result.stdout:
            output += f"stdout:\n{result.stdout}\n"
        if result.stderr:
            output += f"stderr:\n{result.stderr}\n"
        output += f"returncode: {result.returncode}"
        return output
    except subprocess.TimeoutExpired:
        return f"Command timed out after {timeout}s"


RUN_COMMAND_SCHEMA = {
    "description": "执行 shell 命令并返回 stdout/stderr/returncode",
    "parameters": {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "要执行的 shell 命令"},
            "timeout": {"type": "integer", "description": "超时时间（秒）", "default": 300},
        },
        "required": ["command"],
    },
}
