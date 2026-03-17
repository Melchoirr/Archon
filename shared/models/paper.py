"""论文数据模型"""

from __future__ import annotations

from pydantic import BaseModel, Field


class Author(BaseModel):
    name: str


class ExternalIds(BaseModel):
    ArXiv: str | None = None
    DOI: str | None = None


class Paper(BaseModel):
    """OpenAlex / Semantic Scholar 返回的论文结构"""
    paperId: str
    title: str
    year: int | None = None
    citationCount: int = 0
    venue: str = ""
    authors: list[Author] = []
    externalIds: ExternalIds = Field(default_factory=ExternalIds)
    url: str = ""
    arxiv_url: str = ""
    arxiv_pdf: str = ""


class PaperIndexEntry(BaseModel):
    """论文索引条目，对应 index.yaml 中的每一项"""
    paper_id: str
    title: str
    year: int | None = None
    citation_count: int = 0
    arxiv_id: str = ""
    venue: str = ""
    authors: list[str] = []
    open_access_url: str = ""
    relevance: str = ""
    download_status: str = "pending"
    summary_status: str = "pending"
