"""
Agent 基类：基于 MiniMax M2.5 API 的 ReAct 循环。
使用 Anthropic 兼容接口 + tool calling。
工具参数通过 Pydantic 模型校验。
"""
import os
import logging
import time

import anthropic
from pydantic import BaseModel, ValidationError

from tools.knowledge_base import search_knowledge_base
from shared.models.tool_params import SearchKBParams

logger = logging.getLogger(__name__)


def llm_call_with_retry(client, max_retries=3, **kwargs):
    """带指数退避重试的 LLM 调用"""
    for attempt in range(max_retries):
        try:
            return client.messages.create(**kwargs)
        except (anthropic.APIConnectionError,
                anthropic.RateLimitError,
                anthropic.InternalServerError) as e:
            if attempt == max_retries - 1:
                raise
            delay = 2 * (2 ** attempt)  # 2s, 4s, 8s
            logger.warning(f"LLM retry {attempt+1}/{max_retries} after {delay}s: {e}")
            time.sleep(delay)


class BaseAgent:
    def __init__(self, name: str, system_prompt: str, tools: list = None,
                 max_iterations: int = 20, allowed_dirs: list[str] = None):
        self.name = name
        self.system_prompt = system_prompt
        self.tools = tools or []
        self.tool_handlers = {}
        self._param_models: dict[str, type[BaseModel]] = {}
        self.max_iterations = max_iterations

        # 路径白名单守卫
        from shared.path_guard import PathGuard
        self._path_guard = PathGuard(allowed_dirs) if allowed_dirs else None

        from shared.utils.config_helpers import load_global_config
        cfg = load_global_config()
        self.client = anthropic.Anthropic(
            api_key=os.environ.get("MINIMAX_API_KEY", ""),
            base_url=cfg.llm.base_url,
        )
        self.model = cfg.llm.default_model
        self._max_tokens = cfg.llm.max_tokens
        self.messages = []

        # 子类可设置，build_prompt 时自动注入已有产出
        self._output_paths: list[str] = []

        # 自动注册全局知识库搜索工具
        self.register_tool("search_knowledge_base", search_knowledge_base, SearchKBParams)

    def _scan_existing_outputs(self) -> str:
        """扫描 _output_paths 中已存在的文件/目录，返回完整内容注入段。

        - 文件：读取全文（超过 MAX_INJECT_CHARS 截断）
        - 目录：列出内容 + 读取每个文件
        """
        if not self._output_paths:
            return ""

        MAX_INJECT_CHARS = 80000  # 单个文件注入上限
        sections = []

        for p in self._output_paths:
            if not os.path.exists(p):
                continue

            if os.path.isfile(p):
                content = self._read_for_inject(p, MAX_INJECT_CHARS)
                if content:
                    sections.append(f"### {os.path.basename(p)}\n"
                                    f"路径: `{p}`\n\n{content}")

            elif os.path.isdir(p):
                entries = sorted(e for e in os.listdir(p)
                                 if not e.startswith("."))
                if not entries:
                    continue
                dir_sections = []
                for e in entries:
                    ep = os.path.join(p, e)
                    if os.path.isdir(ep):
                        sub = sorted(x for x in os.listdir(ep)
                                     if not x.startswith("."))
                        dir_sections.append(f"📂 {e}/ ({len(sub)} 项)")
                    elif os.path.isfile(ep):
                        content = self._read_for_inject(ep, MAX_INJECT_CHARS)
                        if content:
                            dir_sections.append(
                                f"### {e}\n路径: `{ep}`\n\n{content}")
                        else:
                            size = os.path.getsize(ep)
                            dir_sections.append(f"📄 {e} ({size} bytes, 二进制)")
                if dir_sections:
                    sections.append(f"## 目录: {p}/\n\n" + "\n\n".join(dir_sections))

        if not sections:
            return ""

        return ("# 已有产出（断点恢复参考）\n\n"
                "以下是当前阶段已产生的文件内容。请仔细阅读，**跳过已完成的部分**，"
                "只补充缺失或不完整的内容。\n\n"
                + "\n\n---\n\n".join(sections)
                + "\n\n---\n\n")

    @staticmethod
    def _read_for_inject(path: str, max_chars: int) -> str:
        """读取文件内容用于注入，非文本文件返回空。"""
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            if len(content) > max_chars:
                content = content[:max_chars] + f"\n\n... [截断，共 {len(content)} 字符]"
            return content
        except (UnicodeDecodeError, IsADirectoryError):
            return ""

    def register_tool(self, name: str, handler, schema):
        """注册一个工具。schema: Pydantic BaseModel 子类（推荐）或 dict（兼容）

        如果 allowed_dirs 已设置，写操作工具会自动包装路径校验。
        """
        if isinstance(schema, type) and issubclass(schema, BaseModel):
            schema_dict = schema.to_schema()
            self._param_models[name] = schema
        else:
            schema_dict = schema

        # 路径白名单包装
        if self._path_guard is not None:
            from shared.path_guard import make_guarded_handler
            handler = make_guarded_handler(name, handler, self._path_guard)

        self.tool_handlers[name] = handler
        self.tools.append({
            "name": name,
            "description": schema_dict["description"],
            "input_schema": schema_dict["parameters"],
        })

    def _compress_messages(self):
        """压缩过长的历史消息，保留最近 N 轮 + 摘要"""
        MAX_HISTORY_CHARS = 150000

        total = sum(len(str(m.get("content", ""))) for m in self.messages)
        if total <= MAX_HISTORY_CHARS:
            return

        keep_first = 1
        keep_last = 12

        if len(self.messages) <= keep_first + keep_last:
            return

        middle = self.messages[keep_first:-keep_last]

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
                "max_tokens": self._max_tokens,
            }
            if self.tools:
                kwargs["tools"] = self.tools

            try:
                response = llm_call_with_retry(self.client, **kwargs)
            except Exception as e:
                logger.error(f"LLM call failed after retries: {e}")
                return f"[{self.name}] LLM 调用失败: {e}"

            text_parts = []
            tool_uses = []
            for block in response.content:
                if block.type == "text":
                    text_parts.append(block.text)
                elif block.type == "tool_use":
                    tool_uses.append(block)

            self.messages.append({"role": "assistant", "content": response.content})

            if text_parts:
                text = "\n".join(text_parts)
                preview = text[:200] + ("..." if len(text) > 200 else "")
                print(f"\n\n  [{i+1}/{self.max_iterations}] {self.name}:")
                print(f"  {preview}\n")

            if not tool_uses:
                result_text = "\n".join(text_parts)
                print(f"\n\n  {self.name} 完成 ({i+1} 轮)\n")
                return result_text

            tool_results = []

            def _exec_tool(tool_use):
                fn_name = tool_use.name
                fn_args = tool_use.input
                args_preview = str(fn_args)
                if len(args_preview) > 80:
                    args_preview = args_preview[:80] + "..."
                print(f"  -> {fn_name}({args_preview})")

                if fn_name not in self.tool_handlers:
                    result_str = f"Error: Unknown tool '{fn_name}'"
                else:
                    # Pydantic 参数校验
                    if fn_name in self._param_models:
                        try:
                            validated = self._param_models[fn_name](**fn_args)
                            fn_args = validated.model_dump(exclude_none=True)
                        except ValidationError as e:
                            result_str = f"参数校验失败，请修正后重试:\n{e}"
                            print(f"     ! {result_str[:100]}")
                            return {"type": "tool_result", "tool_use_id": tool_use.id, "content": result_str}
                    try:
                        result = self.tool_handlers[fn_name](**fn_args)
                        result_str = str(result)
                    except Exception as e:
                        result_str = f"Error: {e}"
                        print(f"     ! {result_str}")

                if len(result_str) > 100:
                    print(f"     = ({len(result_str)} chars)")
                else:
                    print(f"     = {result_str}")
                return {"type": "tool_result", "tool_use_id": tool_use.id, "content": result_str}

            if len(tool_uses) == 1:
                tool_results.append(_exec_tool(tool_uses[0]))
            else:
                from concurrent.futures import ThreadPoolExecutor
                with ThreadPoolExecutor(max_workers=min(len(tool_uses), 8)) as pool:
                    tool_results.extend(pool.map(_exec_tool, tool_uses))

            remaining = self.max_iterations - i - 1
            if remaining <= 5:
                urgency = "⚠️ 时间紧迫！" if remaining <= 2 else ""
                tool_results.append({
                    "type": "text",
                    "text": f"[系统提示] 你还剩 {remaining} 轮迭代。{urgency}请确保在结束前完成所有必要的 write_file 操作。",
                })

            self.messages.append({"role": "user", "content": tool_results})

        return f"[{self.name}] 达到最大迭代次数 ({self.max_iterations})"

    def get_message_history(self) -> list:
        return self.messages
