"""Shell 命令执行工具"""
import os
import subprocess


def run_command(command: str, timeout: int = 300, venv_path: str = "") -> str:
    """执行 shell 命令并返回结果"""
    if venv_path and os.path.exists(os.path.join(venv_path, "bin", "activate")):
        command = f"source {venv_path}/bin/activate && {command}"
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
