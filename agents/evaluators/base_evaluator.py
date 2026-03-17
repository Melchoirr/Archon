"""评估器基类：单次 LLM 调用，结构化 YAML 输出，无工具循环"""

import os
import re
import logging

import yaml
import anthropic

from agents.base_agent import llm_call_with_retry

logger = logging.getLogger(__name__)


class BaseEvaluator:
    """轻量评估器基类。

    与 BaseAgent 不同，评估器不进入 ReAct 循环，
    只做单次 LLM 调用并解析结构化 YAML 输出。
    """

    def __init__(self, name: str, system_prompt: str):
        self.name = name
        self.system_prompt = system_prompt
        self.client = anthropic.Anthropic(
            api_key=os.environ.get("MINIMAX_API_KEY", ""),
            base_url=os.environ.get("MINIMAX_BASE_URL", "https://api.minimaxi.com/anthropic"),
        )
        self.model = os.environ.get("MINIMAX_MODEL", "MiniMax-M2.5")

    def evaluate(self, context: dict) -> dict:
        """构建 prompt → 单次 LLM 调用 → 解析 YAML → 返回结构化决策"""
        prompt = self.build_prompt(**context)

        logger.info(f"[{self.name}] 评估开始")
        try:
            response = llm_call_with_retry(
                self.client,
                model=self.model,
                system=self.system_prompt,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=4096,
            )
        except Exception as e:
            logger.error(f"[{self.name}] LLM 调用失败: {e}")
            return {"verdict": "error", "error": str(e)}

        text = ""
        for block in response.content:
            if block.type == "text":
                text += block.text

        logger.info(f"[{self.name}] 评估完成，解析输出")
        return self._parse_yaml(text)

    def build_prompt(self, **kwargs) -> str:
        """子类实现：构建评估 prompt"""
        raise NotImplementedError

    def _parse_yaml(self, text: str) -> dict:
        """从 LLM 输出中提取 YAML 块并解析"""
        # 尝试提取 ```yaml ... ``` 块
        match = re.search(r"```ya?ml\s*\n(.*?)```", text, re.DOTALL)
        if match:
            yaml_str = match.group(1)
        else:
            # 尝试直接解析整段文本
            yaml_str = text

        try:
            result = yaml.safe_load(yaml_str)
            if isinstance(result, dict):
                return result
        except yaml.YAMLError:
            pass

        # 回退：尝试逐行解析 key: value
        result = {}
        for line in text.split("\n"):
            line = line.strip()
            if ":" in line and not line.startswith("#"):
                key, _, val = line.partition(":")
                key = key.strip()
                val = val.strip()
                if key and val:
                    result[key] = val

        if not result:
            logger.warning(f"[{self.name}] 无法解析 YAML 输出，返回原始文本")
            return {"verdict": "error", "raw_output": text[:2000]}

        return result
