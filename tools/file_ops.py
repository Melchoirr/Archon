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


def edit_file(path: str, old_content: str, new_content: str) -> str:
    """在文件中查找指定内容并替换（精确字符串匹配）"""
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()

    count = text.count(old_content)
    if count == 0:
        # 提取 ## 标题帮助 Agent 定位
        headers = [line for line in text.splitlines() if line.startswith("## ")]
        hint = "\n".join(headers[:20]) if headers else "(无 ## 标题)"
        return f"EDIT_FAILED: old_content 未找到。文件章节:\n{hint}"
    if count > 1:
        return f"EDIT_FAILED: old_content 匹配到 {count} 处，请提供更长的上下文以唯一定位。"

    text = text.replace(old_content, new_content, 1)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)

    delta = len(new_content) - len(old_content)
    sign = "+" if delta >= 0 else ""
    return f"Edited {path} ({sign}{delta} chars)"


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
