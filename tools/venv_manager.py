"""虚拟环境管理工具 — 为每个 idea 创建隔离 venv 并安装依赖"""

import os
import shutil
import subprocess


def setup_idea_venv(
    idea_src_dir: str,
    python_version: str = "3.10",
    pip_mirror: str = "https://pypi.tuna.tsinghua.edu.cn/simple",
    use_uv: bool = True,
) -> str:
    """创建 venv 并安装 requirements.txt 中的依赖。

    1. 检查 {idea_src_dir}/requirements.txt 是否存在
    2. uv venv --python {python_version} {idea_src_dir}/.venv
       （fallback: python{version} -m venv）
    3. uv pip install --python {venv}/bin/python -r requirements.txt -i {mirror}
       （fallback: {venv}/bin/pip install -r requirements.txt -i {mirror}）
    4. 返回成功/失败信息
    """
    req_path = os.path.join(idea_src_dir, "requirements.txt")
    has_requirements = os.path.exists(req_path)

    venv_path = os.path.join(idea_src_dir, ".venv")
    venv_python = os.path.join(venv_path, "bin", "python")

    # ── 创建 venv ──────────────────────────────────────────
    if not os.path.exists(venv_python):
        created = False
        if use_uv and shutil.which("uv"):
            ret = subprocess.run(
                ["uv", "venv", "--python", python_version, venv_path],
                capture_output=True, text=True,
            )
            if ret.returncode == 0:
                created = True
            else:
                # uv 创建失败，fallback
                pass

        if not created:
            # fallback: python -m venv
            py_cmd = f"python{python_version}"
            if not shutil.which(py_cmd):
                py_cmd = "python"
            ret = subprocess.run(
                [py_cmd, "-m", "venv", venv_path],
                capture_output=True, text=True,
            )
            if ret.returncode != 0:
                return f"venv 创建失败: {ret.stderr}"

    # ── 安装依赖 ──────────────────────────────────────────
    if not has_requirements:
        return f"venv 已创建（无依赖）: venv={venv_path}"

    if use_uv and shutil.which("uv"):
        cmd = [
            "uv", "pip", "install",
            "--python", venv_python,
            "-r", req_path,
            "-i", pip_mirror,
        ]
    else:
        pip_cmd = os.path.join(venv_path, "bin", "pip")
        cmd = [
            pip_cmd, "install",
            "-r", req_path,
            "-i", pip_mirror,
        ]

    ret = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if ret.returncode != 0:
        return f"依赖安装失败:\n{ret.stderr}\n{ret.stdout}"

    return f"环境配置成功: venv={venv_path}"


def get_venv_activate_prefix(idea_src_dir: str) -> str:
    """返回 'source {venv}/bin/activate && ' 或空字符串"""
    venv_path = os.path.join(idea_src_dir, ".venv")
    activate = os.path.join(venv_path, "bin", "activate")
    if os.path.exists(activate):
        return f"source {activate} && "
    return ""


def get_venv_path(idea_src_dir: str) -> str:
    """返回 venv 路径（如果存在），否则空字符串"""
    venv_path = os.path.join(idea_src_dir, ".venv")
    if os.path.exists(os.path.join(venv_path, "bin", "activate")):
        return venv_path
    return ""
