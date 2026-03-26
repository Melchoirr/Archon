"""全局配置模型 — 对应项目根 config.yaml"""

from __future__ import annotations
from pydantic import BaseModel, Field


class LLMConfig(BaseModel):
    base_url: str = "https://api.minimaxi.com/anthropic"
    default_model: str = "MiniMax-M2.5"
    fast_model: str = ""
    max_tokens: int = 16384


class SearchConfig(BaseModel):
    openalex_api: str = "https://api.openalex.org"
    web_search_engine: str = "duckduckgo"


class GlobalConfig(BaseModel):
    """全局配置，对应项目根 config.yaml"""
    llm: LLMConfig = Field(default_factory=LLMConfig)
    search: SearchConfig = Field(default_factory=SearchConfig)
