"""配置数据模型 — 对应 config.yaml 结构"""

from __future__ import annotations

from pydantic import BaseModel, Field


class TopicSection(BaseModel):
    title: str = "(未设置课题)"
    domain: str = ""
    keywords: list[str] = []


class LLMSection(BaseModel):
    provider: str = "minimax"
    sdk: str = "anthropic"
    base_url: str = ""
    default_model: str = "MiniMax-M2.5"
    fast_model: str = ""
    max_tokens: int = 4096


class ProjectSection(BaseModel):
    name: str = ""


class EnvironmentSection(BaseModel):
    conda_env: str = "agent"
    python: str = "3.10"
    pip_mirror: str = "https://pypi.tuna.tsinghua.edu.cn/simple"
    use_uv: bool = True


class MetricsSection(BaseModel):
    primary: list[str] = []
    topic_specific: list[str] = []


class ExperimentSection(BaseModel):
    quick_test: dict = Field(default_factory=dict)


class TopicConfig(BaseModel):
    """完整的 topic 配置"""
    topic: TopicSection = Field(default_factory=TopicSection)
    llm: LLMSection = Field(default_factory=LLMSection)
    project: ProjectSection = Field(default_factory=ProjectSection)
    environment: EnvironmentSection = Field(default_factory=EnvironmentSection)
    datasets: dict = Field(default_factory=dict)
    metrics: MetricsSection = Field(default_factory=MetricsSection)
    experiment: ExperimentSection = Field(default_factory=ExperimentSection)
    search: dict = Field(default_factory=dict)

    @property
    def dataset_names(self) -> str:
        return ", ".join(self.datasets.keys()) if self.datasets else ""

    @property
    def metric_names(self) -> str:
        all_m = self.metrics.primary + self.metrics.topic_specific
        return ", ".join(all_m) if all_m else ""

    @property
    def quick_test_desc(self) -> str:
        qt = self.experiment.quick_test
        return ", ".join(f"{k}={v}" for k, v in qt.items()) if qt else ""

    @property
    def search_keywords(self) -> list[str]:
        return self.topic.keywords
