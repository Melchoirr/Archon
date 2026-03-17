"""文件操作工具"""
import os


def read_file(path: str) -> str:
    """读取文件内容"""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def write_file(path: str, content: str) -> str:
    """写入文件（覆盖）"""
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return f"Written to {path}"


def append_file(path: str, content: str) -> str:
    """追加内容到文件"""
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(content)
    return f"Appended to {path}"


def list_directory(path: str = ".") -> str:
    """列出目录内容"""
    entries = os.listdir(path)
    return "\n".join(sorted(entries))
