"""工具参数模型 — 精确替代所有手写 schema dict

每个模型的字段名、类型、描述、默认值、required 列表
都与原始手写 schema dict 完全一致。
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ToolParamsBase(BaseModel):
    """所有工具参数模型的基类，提供 to_schema() 桥接 base_agent"""

    @classmethod
    def to_schema(cls) -> dict:
        schema = cls.model_json_schema()
        props = {}
        for k, v in schema.get("properties", {}).items():
            v.pop("title", None)
            # 把 anyOf (Optional) 简化为基础类型
            if "anyOf" in v:
                for option in v["anyOf"]:
                    if option.get("type") != "null":
                        v.update(option)
                        break
                v.pop("anyOf", None)
            props[k] = v
        required = [n for n, f in cls.model_fields.items() if f.is_required()]
        return {
            "description": cls.__doc__ or "",
            "parameters": {"type": "object", "properties": props, "required": required},
        }


# ── file_ops ──────────────────────────────────────────────────

class ReadFileParams(ToolParamsBase):
    """读取指定路径的文件内容"""
    path: str = Field(description="文件路径")


class WriteFileParams(ToolParamsBase):
    """将内容写入指定路径的文件（覆盖已有内容）"""
    path: str = Field(description="文件路径")
    content: str = Field(description="要写入的内容")


class AppendFileParams(ToolParamsBase):
    """将内容追加到文件末尾"""
    path: str = Field(description="文件路径")
    content: str = Field(description="要追加的内容")


class ListDirectoryParams(ToolParamsBase):
    """列出指定目录下的文件和子目录"""
    path: str = Field(default=".", description="目录路径")


# ── web_search ────────────────────────────────────────────────

class WebSearchParams(ToolParamsBase):
    """使用 DuckDuckGo 搜索引擎搜索网页内容"""
    query: str = Field(description="搜索关键词")
    max_results: int = Field(default=10, description="返回结果数量")


# ── openalex ──────────────────────────────────────────────────

class SearchTopicsParams(ToolParamsBase):
    """搜索 OpenAlex 学科主题，返回 topic_id。两步搜索第一步：先查 topic_id，再用 search_papers(topic_id=...) 精确搜索。"""
    query: str = Field(description="主题关键词（如 'time series forecasting'）")
    limit: int = Field(default=5, description="返回数量（默认5）")


class SearchPapersParams(ToolParamsBase):
    """在 OpenAlex 上搜索学术论文。推荐两步搜索：先 search_topics 获取 topic_id，再 search_papers(query=关键词, topic_id=...) 精确搜索。支持三种搜索模式：keyword（短关键词）、semantic（长自然语言描述）、exact（精确匹配不做词干化）。"""
    query: str = Field(description="搜索词。keyword 模式建议 2-4 个英文词；semantic 模式可用长自然语言描述；支持引号精确短语、近邻搜索、通配符、Boolean")
    limit: int = Field(default=10, description="返回数量（默认10，上限200，semantic 模式上限50）")
    min_citations: int = Field(default=0, description="最低引用数过滤（默认0）")
    year_range: str = Field(default="", description="年份范围，如 '2023-'(2023至今) '2019-2024' '2023'(仅2023)")
    sort: str = Field(default="relevance", description="排序: relevance（默认）/ citationCount:desc / publicationDate:desc")
    topic_id: str = Field(default="", description="OpenAlex Topic ID（如 T12205），限定领域搜索，大幅提高相关性")
    include_abstract: bool = Field(default=False, description="是否返回摘要（默认False）")
    search_mode: str = Field(default="keyword", description="搜索模式: keyword（默认，短关键词）/ semantic（语义搜索，适合长描述，限1req/s）/ exact（精确匹配，不做词干化）")


class GetPaperReferencesParams(ToolParamsBase):
    """获取论文引用的其他论文列表（该论文的参考文献）"""
    paper_id: str = Field(description="OpenAlex work ID（如 W2741809807）")
    limit: int = Field(default=20, description="返回数量")


class GetPaperCitationsParams(ToolParamsBase):
    """获取引用了该论文的论文列表（谁引了它）"""
    paper_id: str = Field(description="OpenAlex work ID（如 W2741809807）")
    limit: int = Field(default=20, description="返回数量")


# ── bash_exec ─────────────────────────────────────────────────

class RunCommandParams(ToolParamsBase):
    """执行 shell 命令并返回 stdout/stderr/returncode"""
    command: str = Field(description="要执行的 shell 命令")
    timeout: int = Field(default=300, description="超时时间（秒）")
    venv_path: str = Field(default="", description="venv 目录路径。设置后命令在该 venv 中执行。")


# ── research_tree ─────────────────────────────────────────────

class ReadTreeParams(ToolParamsBase):
    """读取完整的研究树状态"""


class UpdateIdeaPhaseParams(ToolParamsBase):
    """更新指定 idea 的某个阶段状态"""
    idea_id: str = Field(description="Idea ID（如 T001-I001）")
    phase: str = Field(description="阶段名: refinement/code_reference/coding/experiment/analysis/conclusion")
    status: str = Field(description="状态: pending/in_progress/running/completed/failed/skipped")


class UpdateIdeaStatusParams(ToolParamsBase):
    """更新指定 idea 的整体状态"""
    idea_id: str = Field(description="Idea ID（如 T001-I001）")
    status: str = Field(description="状态: proposed/recommended/deprioritized/active/completed/failed")


class UpdateSurveyStatusParams(ToolParamsBase):
    """更新 survey 阶段状态"""
    status: str = Field(description="状态: pending/in_progress/completed/failed")
    rounds: int = Field(default=0, description="完成的轮次数")


class UpdateElaborateStatusParams(ToolParamsBase):
    """更新 elaborate 阶段状态"""
    status: str = Field(description="状态: pending/in_progress/completed/failed")


class AddIdeaParams(ToolParamsBase):
    """向研究树中添加一个新的研究 idea"""
    idea_id: str = Field(description="Idea ID，如 'I001'")
    title: str = Field(description="Idea 标题")
    category: str = Field(description="类别: loss/architecture/training/inference")
    brief: str = Field(default="", description="简短标识（用于目录名）")


class AddExperimentStepParams(ToolParamsBase):
    """注册一个实验步骤到指定 idea，含可配置的迭代次数"""
    idea_id: str = Field(description="Idea ID")
    step_name: str = Field(description="步骤名称（如 quick_test, full_test）")
    max_iter: int = Field(default=3, description="最大迭代次数")


class UpdateIterationParams(ToolParamsBase):
    """更新实验迭代状态"""
    idea_id: str = Field(description="Idea ID")
    step_id: str = Field(description="步骤 ID（如 S01）")
    version: int = Field(description="版本号（如 1, 2, 3）")
    status: str = Field(description="状态: pending/running/completed/failed/skipped")
    config_diff: str = Field(default="", description="相对 V1 的配置差异")


# ── memory ────────────────────────────────────────────────────

class QueryMemoryParams(ToolParamsBase):
    """查询研究经验记忆，可按标签、阶段、idea ID 过滤"""
    tags: str = Field(default="", description="逗号分隔的标签过滤")
    phase: str = Field(default="", description="阶段过滤: elaborate/survey/ideation/refine/code/experiment/analyze/conclude")
    idea_id: str = Field(default="", description="Idea ID 过滤")
    topic_id: str = Field(default="", description="Topic ID 过滤（如 T001）")


class AddExperienceParams(ToolParamsBase):
    """添加一条研究经验记录"""
    idea_id: str = Field(default="", description="关联的 Idea ID")
    phase: str = Field(default="", description="所属阶段")
    type: str = Field(default="", description="类型: insight/success/failure/observation")
    summary: str = Field(description="经验摘要")
    details: str = Field(default="", description="详细描述")
    tags: str = Field(default="", description="逗号分隔的标签")
    topic_id: str = Field(default="", description="关联的 Topic ID（如 T001）")


# ── paper_manager ─────────────────────────────────────────────

class DownloadPaperParams(ToolParamsBase):
    """下载论文 PDF 并用 MinerU 解析为 Markdown，支持后续按章节阅读"""
    paper_id: str = Field(description="论文 ID（OpenAlex W* / arXiv ID）")
    title: str = Field(default="", description="论文标题（可选，用于索引）")


class ReadPaperSectionParams(ToolParamsBase):
    """按需阅读论文的指定章节（如 method, experiment）或按关键词搜索论文内容。为空则返回结构概览。"""
    paper_id: str = Field(description="论文 ID（OpenAlex W* / arXiv ID）")
    section: str = Field(default="", description="章节名（abstract/introduction/method/experiment/conclusion）或搜索关键词，为空返回概览")


class ListPapersParams(ToolParamsBase):
    """列出所有已下载并解析的论文"""


class SearchPaperIndexParams(ToolParamsBase):
    """按标题/关键词搜索全局论文索引"""
    query: str = Field(description="搜索关键词")
    topic_id: str = Field(default="", description="可选，只搜索指定 topic 引用的论文")
    base_dir: str = Field(default="", description="论文存储根目录（默认 knowledge/papers）")


# ── claude_code ───────────────────────────────────────────────

class ClaudeWriteModuleParams(ToolParamsBase):
    """调用 claude -p 编写一个功能模块。Claude 会自动读取项目中的文件。每次只写一个模块。在 task 中描述清楚：功能、目标文件路径、输入输出、技术细节、需要参考哪些已有文件。"""
    module_name: str = Field(description="模块名称（如 '数据加载器'、'模型定义'、'损失函数'、'训练循环'、'评估脚本'）")
    task: str = Field(description="详细的编码任务描述：功能、目标文件、输入输出、技术要求、需要参考的已有文件等")
    working_dir: str = Field(default="", description="工作目录（相对于项目根目录），通常是 idea 目录如 'ideas/idea_001_xxx'")
    context_files: str = Field(default="", description="参考文件内容（直接传入文件内容作为上下文，如 design.md 或已有模块的代码）")


class ClaudeFixErrorParams(ToolParamsBase):
    """调用 claude -p 修复代码错误。将 run_command 得到的报错信息传入，Claude 会自动定位并修复。"""
    error_info: str = Field(description="错误信息：traceback、测试失败输出、或具体的错误描述")
    fix_instruction: str = Field(default="", description="额外的修复提示（可选）")
    working_dir: str = Field(default="", description="工作目录")


class ClaudeReviewParams(ToolParamsBase):
    """调用 claude -p 审查代码。Claude 会自动读取文件并检查。"""
    review_instruction: str = Field(description="审查指令：审查哪个文件、重点关注什么（如 '审查 src/model.py，对照 design.md 检查模型结构是否一致'）")
    working_dir: str = Field(default="", description="工作目录")


# ── config_updater ────────────────────────────────────────────

class UpdateConfigSectionParams(ToolParamsBase):
    """更新 config.yaml 的指定 section（如 datasets, metrics, experiment）。data 参数为 YAML 格式字符串。"""
    section: str = Field(description="要更新的顶层 key，如 datasets, metrics, experiment")
    data: str = Field(description="YAML 格式字符串，解析后写入该 section")


# ── knowledge_base ────────────────────────────────────────────

class SearchKBParams(ToolParamsBase):
    """搜索知识库中的历史中间结果。可搜索论文总结、实验结果、代码摘要等所有历史产出。"""
    query: str = Field(description="搜索内容")
    scope: str = Field(default="all", description="搜索范围: topic ID (如 T001) 或 phase (survey/dataset) 按标题前缀过滤, all=全部")
    top_k: int = Field(default=5, description="返回结果数")


# ── github_repo ───────────────────────────────────────────────

class CloneRepoParams(ToolParamsBase):
    """Git clone 一个 GitHub 仓库到 knowledge/repos/ 目录（浅克隆）"""
    repo_url: str = Field(description="GitHub 仓库 URL")
    target_dir: str = Field(default="", description="目标目录名（可选，默认从 URL 推断）")


class SummarizeRepoParams(ToolParamsBase):
    """用 claude -p 生成仓库代码摘要，输出 SUMMARY.md"""
    repo_path: str = Field(description="仓库路径（如 knowledge/repos/repo_name）")


class ListReposParams(ToolParamsBase):
    """列出已 clone 的仓库列表"""


# ── idea_graph ────────────────────────────────────────────────

class AddRelationshipParams(ToolParamsBase):
    """添加两个 idea 之间的关系（builds_on/alternative_to/complementary/combines_with）"""
    idea_a: str = Field(description="第一个 idea ID (如 T001-I001)")
    idea_b: str = Field(description="第二个 idea ID (如 T001-I002)")
    rel_type: str = Field(description="关系类型")
    topic_dir: str = Field(default=".", description="topic 目录路径")


class GetGraphParams(ToolParamsBase):
    """获取完整的 idea 关系图（markdown 格式）"""
    topic_dir: str = Field(default=".", description="topic 目录路径")


class SuggestCombinationsParams(ToolParamsBase):
    """建议可组合的 idea 对"""
    topic_dir: str = Field(default=".", description="topic 目录路径")


# ── vlm_analysis ──────────────────────────────────────────────

class AnalyzeImageParams(ToolParamsBase):
    """发送图片到 VLM 进行分析（实验结果可视化、曲线图等）"""
    image_path: str = Field(description="图片文件路径")
    question: str = Field(default="请分析这张图片中展示的实验结果。", description="分析问题/指令")


class AnalyzePlotsParams(ToolParamsBase):
    """分析目录下的所有实验结果图片"""
    plots_dir: str = Field(description="图片目录路径")
    context: str = Field(default="", description="额外的实验上下文信息")


# ── phase_logger ──────────────────────────────────────────────

class LogPhaseStartParams(ToolParamsBase):
    """记录阶段开始时的状态快照"""
    phase: str = Field(description="阶段名称")
    topic_dir: str = Field(description="topic 目录路径")
    idea_id: str = Field(default="", description="idea ID")


class LogPhaseEndParams(ToolParamsBase):
    """记录阶段结束时的状态和摘要"""
    phase: str = Field(description="阶段名称")
    topic_dir: str = Field(description="topic 目录路径")
    idea_id: str = Field(default="", description="idea ID")
    summary: str = Field(default="", description="阶段执行摘要")


# ── idea_scorer ───────────────────────────────────────────────

class ScoreIdeasParams(ToolParamsBase):
    """对所有 proposed 状态的 idea 进行评分和排序"""


# ── venv_manager ─────────────────────────────────────────────

class SetupVenvParams(ToolParamsBase):
    """创建 venv 并安装 requirements.txt 中的依赖"""
    idea_src_dir: str = Field(description="idea 的 src/ 目录路径（包含 requirements.txt）")
    python_version: str = Field(default="3.10", description="Python 版本")
    pip_mirror: str = Field(default="https://pypi.tuna.tsinghua.edu.cn/simple", description="PyPI 镜像 URL")
    use_uv: bool = Field(default=True, description="是否使用 uv 加速安装")
