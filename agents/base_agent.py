"""
Agent 基类：基于 MiniMax M2.5 API 的 ReAct 循环。
使用 Anthropic 兼容接口 + tool calling。
"""
import json
import os
import logging

import anthropic

from tools.knowledge_base import search_knowledge_base, SEARCH_KB_SCHEMA

logger = logging.getLogger(__name__)


class BaseAgent:
    def __init__(self, name: str, system_prompt: str, tools: list = None, max_iterations: int = 20):
        self.name = name
        self.system_prompt = system_prompt
        self.tools = tools or []
        self.tool_handlers = {}
        self.max_iterations = max_iterations

        self.client = anthropic.Anthropic(
            api_key=os.environ.get("MINIMAX_API_KEY", ""),
            base_url=os.environ.get("MINIMAX_BASE_URL", "https://api.minimaxi.com/anthropic"),
        )
        self.model = os.environ.get("MINIMAX_MODEL", "MiniMax-M2.5")
        self.messages = []

        # 自动注册全局知识库搜索工具
        self.register_tool("search_knowledge_base", search_knowledge_base, SEARCH_KB_SCHEMA)

    def register_tool(self, name: str, handler, schema: dict):
        """注册一个工具：名称、处理函数、schema"""
        self.tool_handlers[name] = handler
        self.tools.append({
            "name": name,
            "description": schema["description"],
            "input_schema": schema["parameters"],
        })

    def _compress_messages(self):
        """压缩过长的历史消息，保留最近 N 轮 + 摘要"""
        MAX_HISTORY_CHARS = 50000  # 约 25K tokens

        # 计算当前消息总长度
        total = sum(len(str(m.get("content", ""))) for m in self.messages)
        if total <= MAX_HISTORY_CHARS:
            return

        # 保留第一条（初始 prompt）+ 最近 6 轮（12 条消息）
        keep_first = 1
        keep_last = 12

        if len(self.messages) <= keep_first + keep_last:
            return

        middle = self.messages[keep_first:-keep_last]

        # 提取中间轮次的工具调用摘要
        tool_calls = []
        for msg in middle:
            content = msg.get("content", "")
            if isinstance(content, list):
                for block in content:
                    if hasattr(block, "name"):
                        tool_calls.append(f"- {block.name}(...)")
                    elif isinstance(block, dict) and block.get("type") == "tool_result":
                        result_preview = str(block.get("content", ""))[:80]
                        tool_calls.append(f"  → {result_preview}")

        summary_text = (
            f"[历史摘要: 已执行 {len(middle)//2} 轮工具调用]\n"
            + "\n".join(tool_calls[-20:])
        )

        self.messages = (
            self.messages[:keep_first]
            + [{"role": "user", "content": summary_text}]
            + self.messages[-keep_last:]
        )
        logger.info(f"Messages compressed: {total} -> {sum(len(str(m.get('content', ''))) for m in self.messages)} chars")

    def run(self, user_prompt: str) -> str:
        """ReAct 循环：推理 -> 调用工具 -> 观察 -> 继续"""
        self.messages.append({"role": "user", "content": user_prompt})
        print(f"\n\n{'='*60}")
        print(f"  {self.name} 启动")
        print(f"{'='*60}\n")

        for i in range(self.max_iterations):
            self._compress_messages()

            kwargs = {
                "model": self.model,
                "system": self.system_prompt,
                "messages": self.messages,
                "max_tokens": 4096,
            }
            if self.tools:
                kwargs["tools"] = self.tools

            response = self.client.messages.create(**kwargs)

            # 解析 response content blocks
            text_parts = []
            tool_uses = []
            for block in response.content:
                if block.type == "text":
                    text_parts.append(block.text)
                elif block.type == "tool_use":
                    tool_uses.append(block)

            # 将 assistant 消息追加到历史
            self.messages.append({"role": "assistant", "content": response.content})

            # 打印 agent 的文本输出（如有）
            if text_parts:
                text = "\n".join(text_parts)
                # 只打印前 200 字符作为进度提示
                preview = text[:200] + ("..." if len(text) > 200 else "")
                print(f"\n\n  [{i+1}/{self.max_iterations}] {self.name}:")
                print(f"  {preview}\n")

            # 无工具调用 -> 完成
            if not tool_uses:
                result_text = "\n".join(text_parts)
                print(f"\n\n  {self.name} 完成 ({i+1} 轮)\n")
                return result_text

            # 有工具调用 -> 执行并构建 tool_result
            tool_results = []
            for tool_use in tool_uses:
                fn_name = tool_use.name
                fn_args = tool_use.input

                # 简洁的工具调用日志
                args_preview = str(fn_args)
                if len(args_preview) > 80:
                    args_preview = args_preview[:80] + "..."
                print(f"  -> {fn_name}({args_preview})")

                if fn_name not in self.tool_handlers:
                    result = f"Error: Unknown tool '{fn_name}'"
                else:
                    try:
                        result = self.tool_handlers[fn_name](**fn_args)
                    except Exception as e:
                        result = f"Error: {e}"
                        print(f"     ! {result}")

                # 简洁的结果日志
                result_str = str(result)
                if len(result_str) > 100:
                    print(f"     = ({len(result_str)} chars)")
                else:
                    print(f"     = {result_str}")

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_use.id,
                    "content": result_str,
                })

            self.messages.append({"role": "user", "content": tool_results})

        return f"[{self.name}] 达到最大迭代次数 ({self.max_iterations})"

    def get_message_history(self) -> list:
        return self.messages
