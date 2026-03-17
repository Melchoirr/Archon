"""VLM 图片分析工具：通过 Qwen3.5-Plus VL（阿里云百炼 OpenAI 兼容接口）分析图片"""
import base64
import json
import os
import logging

logger = logging.getLogger(__name__)

QWEN_VL_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
QWEN_VL_MODEL = "qwen3.5-vl-plus"


def _encode_image(image_path: str) -> str:
    """将图片编码为 base64"""
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def _get_mime_type(image_path: str) -> str:
    ext = os.path.splitext(image_path)[1].lower()
    return {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".gif": "image/gif", ".webp": "image/webp"}.get(ext, "image/png")


def analyze_image(image_path: str, question: str = "请分析这张图片中展示的实验结果。") -> str:
    """发送图片到 Qwen VL 进行分析。

    Args:
        image_path: 图片文件路径
        question: 分析问题/指令

    Returns:
        VLM 分析结果
    """
    if not os.path.exists(image_path):
        return f"Image not found: {image_path}"

    api_key = os.environ.get("QWEN_API_KEY", "")
    if not api_key:
        return "No VLM API key configured (QWEN_API_KEY)"

    try:
        from openai import OpenAI
        client = OpenAI(
            api_key=api_key,
            base_url=os.environ.get("QWEN_VL_BASE_URL", QWEN_VL_BASE_URL),
        )

        image_data = _encode_image(image_path)
        mime_type = _get_mime_type(image_path)
        data_url = f"data:{mime_type};base64,{image_data}"

        response = client.chat.completions.create(
            model=os.environ.get("QWEN_VL_MODEL", QWEN_VL_MODEL),
            max_tokens=4096,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": data_url}},
                    {"type": "text", "text": question},
                ],
            }],
        )

        if response.choices and response.choices[0].message.content:
            return response.choices[0].message.content
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
