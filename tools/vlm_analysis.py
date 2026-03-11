"""VLM 图片分析工具：发送图片到 VLM 进行分析"""
import base64
import json
import os
import logging

logger = logging.getLogger(__name__)


def _encode_image(image_path: str) -> str:
    """将图片编码为 base64"""
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def _get_mime_type(image_path: str) -> str:
    ext = os.path.splitext(image_path)[1].lower()
    return {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".gif": "image/gif", ".webp": "image/webp"}.get(ext, "image/png")


def analyze_image(image_path: str, question: str = "请分析这张图片中展示的实验结果。") -> str:
    """发送图片到 VLM 进行分析。

    Args:
        image_path: 图片文件路径
        question: 分析问题/指令

    Returns:
        VLM 分析结果
    """
    if not os.path.exists(image_path):
        return f"Image not found: {image_path}"

    # 优先使用 MiniMax VLM
    api_key = os.environ.get("MINIMAX_API_KEY", "")
    if not api_key:
        return "No VLM API key configured (MINIMAX_API_KEY)"

    try:
        import anthropic
        client = anthropic.Anthropic(
            api_key=api_key,
            base_url=os.environ.get("MINIMAX_BASE_URL", "https://api.minimaxi.com/anthropic"),
        )

        image_data = _encode_image(image_path)
        mime_type = _get_mime_type(image_path)

        response = client.messages.create(
            model=os.environ.get("MINIMAX_MODEL", "MiniMax-M2.5"),
            max_tokens=2048,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": mime_type, "data": image_data}},
                    {"type": "text", "text": question},
                ],
            }],
        )

        if response.content:
            return response.content[0].text
        return "VLM returned empty response"

    except Exception as e:
        logger.error(f"VLM analysis failed: {e}")
        return f"VLM analysis error: {e}"


def analyze_plots_dir(plots_dir: str, context: str = "") -> str:
    """分析目录下的所有图片文件。

    Args:
        plots_dir: 图片目录
        context: 额外的实验上下文信息
    """
    if not os.path.exists(plots_dir):
        return f"Directory not found: {plots_dir}"

    image_exts = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
    images = [f for f in os.listdir(plots_dir) if os.path.splitext(f)[1].lower() in image_exts]

    if not images:
        return "No images found in directory."

    results = []
    for img in sorted(images):
        img_path = os.path.join(plots_dir, img)
        question = f"请分析这张实验结果图片。{f'上下文: {context}' if context else ''}"
        analysis = analyze_image(img_path, question)
        results.append(f"### {img}\n{analysis}")

    return "\n\n".join(results)


ANALYZE_IMAGE_SCHEMA = {
    "description": "发送图片到 VLM 进行分析（实验结果可视化、曲线图等）",
    "parameters": {
        "type": "object",
        "properties": {
            "image_path": {"type": "string", "description": "图片文件路径"},
            "question": {"type": "string", "description": "分析问题/指令", "default": "请分析这张图片中展示的实验结果。"},
        },
        "required": ["image_path"],
    },
}

ANALYZE_PLOTS_SCHEMA = {
    "description": "分析目录下的所有实验结果图片",
    "parameters": {
        "type": "object",
        "properties": {
            "plots_dir": {"type": "string", "description": "图片目录路径"},
            "context": {"type": "string", "description": "额外的实验上下文信息", "default": ""},
        },
        "required": ["plots_dir"],
    },
}
