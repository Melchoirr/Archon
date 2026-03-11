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


READ_FILE_SCHEMA = {
    "description": "读取指定路径的文件内容",
    "parameters": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "文件路径"},
        },
        "required": ["path"],
    },
}

WRITE_FILE_SCHEMA = {
    "description": "将内容写入指定路径的文件（覆盖已有内容）",
    "parameters": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "文件路径"},
            "content": {"type": "string", "description": "要写入的内容"},
        },
        "required": ["path", "content"],
    },
}

APPEND_FILE_SCHEMA = {
    "description": "将内容追加到文件末尾",
    "parameters": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "文件路径"},
            "content": {"type": "string", "description": "要追加的内容"},
        },
        "required": ["path", "content"],
    },
}

LIST_DIRECTORY_SCHEMA = {
    "description": "列出指定目录下的文件和子目录",
    "parameters": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "目录路径", "default": "."},
        },
        "required": [],
    },
}
