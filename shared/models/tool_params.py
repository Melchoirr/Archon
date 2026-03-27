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
    """读取指定路径的文件内容。

    使用场景：阅读 proposal.md、design.md、实验结果文件、代码文件等任何文本文件。
    返回：文件全文字符串；文件不存在时返回错误信息。
    示例：read_file(path="ideas/idea_001_xxx/proposal.md")
    """
    path: str = Field(description="文件路径")


class WriteFileParams(ToolParamsBase):
    """将内容写入指定路径的文件（覆盖已有内容）。

    使用场景：创建或覆盖写入 design.md、theory.md、analysis.md、代码文件等。
    返回：写入确认消息；自动创建不存在的父目录。
    示例：write_file(path="ideas/idea_001_xxx/design.md", content="# 方案设计\n...")
    """
    path: str = Field(description="文件路径")
    content: str = Field(description="要写入的内容")


class AppendFileParams(ToolParamsBase):
    """将内容追加到文件末尾。

    使用场景：向已有文件追加内容，如在日志文件中追加记录、在 markdown 末尾补充章节。
    返回：追加确认消息；文件不存在时自动创建。
    示例：append_file(path="ideas/idea_001_xxx/notes.md", content="\n## 新发现\n...")
    """
    path: str = Field(description="文件路径")
    content: str = Field(description="要追加的内容")


class EditFileParams(ToolParamsBase):
    """在文件中查找指定内容并替换为新内容（精确字符串匹配）。

    使用场景：更新已有文档的特定章节，如修改 survey.md 中的某一节。
    先用 read_file 获取要替换的原始内容，再调用本工具替换。
    返回：替换确认消息；old_content 未找到时返回错误和文件中的章节标题列表。
    示例：edit_file(path="survey/survey.md", old_content="## 旧章节\\n旧内容", new_content="## 新章节\\n新内容")
    """
    path: str = Field(description="文件路径")
    old_content: str = Field(description="要被替换的原始内容（必须精确匹配文件中的连续文本片段）")
    new_content: str = Field(description="替换后的新内容")


class ListDirectoryParams(ToolParamsBase):
    """列出指定目录下的文件和子目录。

    使用场景：查看目录结构，如查看 idea 目录下有哪些文件、results/ 下有哪些步骤目录。
    返回：换行分隔的文件名和子目录名列表。
    示例：list_directory(path="ideas/idea_001_xxx/results")
    """
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
    """执行 shell 命令并返回 stdout/stderr/returncode。

    使用场景：运行实验脚本、安装依赖、执行测试等需要 shell 环境的操作。
    返回：包含 stdout、stderr、returncode 的结构化结果；超时后自动终止进程。
    示例：run_command(command="python train.py --config config.yaml", timeout=600, venv_path="ideas/idea_001_xxx/src/.venv")
    """
    command: str = Field(description="要执行的 shell 命令")
    timeout: int = Field(default=300, description="超时时间（秒）")
    venv_path: str = Field(default="", description="venv 目录路径。设置后命令在该 venv 中执行。")


# ── idea_registry ─────────────────────────────────────────────

class ReadResearchStatusParams(ToolParamsBase):
    """读取研究状态总览（合并 idea_registry + FSM 状态）。

    使用场景：了解当前研究进度，查看所有 idea 的状态、当前阶段、实验步骤等。开始工作前先调用此工具获取全局视图。
    返回：JSON 格式的统一视图，包含 topic 状态和所有 idea 的元数据与 FSM 状态。
    示例：read_research_status()
    """


class AddIdeaParams(ToolParamsBase):
    """添加一个新的研究 idea 到注册表。

    使用场景：在 ideation 阶段产生新 idea 后，将其注册。
    返回：添加确认消息，含生成的完整 idea ID。
    示例：add_idea(idea_id="I001", title="基于频域的注意力机制", category="architecture", brief="freq_attention")
    """
    idea_id: str = Field(description="Idea ID，如 'I001'")
    title: str = Field(description="Idea 标题")
    category: str = Field(description="类别: loss/architecture/training/inference")
    brief: str = Field(default="", description="简短标识（用于目录名）")


# ── memory ────────────────────────────────────────────────────

class QueryMemoryParams(ToolParamsBase):
    """查询研究经验记忆，可按标签、阶段、idea ID 过滤。

    使用场景：在开始新阶段前查询历史经验，避免重复犯错；查找特定类型的 insight 或 failure 记录。
    返回：匹配的经验条目列表（JSON），每条含 summary、details、tags、phase 等字段。
    示例：query_memory(phase="experiment", tags="hyperparameter,failure")
    """
    tags: str = Field(default="", description="逗号分隔的标签过滤")
    phase: str = Field(default="", description="阶段过滤: elaborate/survey/ideation/refine/code/experiment/analyze/conclude")
    idea_id: str = Field(default="", description="Idea ID 过滤")
    topic_id: str = Field(default="", description="Topic ID 过滤（如 T001）")


class AddExperienceParams(ToolParamsBase):
    """添加一条研究经验记录。

    使用场景：记录实验中的关键发现、成功经验、失败教训，供后续阶段和其他 idea 参考。
    返回：添加确认消息。tags 用逗号分隔多个标签。
    示例：add_experience(idea_id="T001-I001", phase="experiment", type="failure", summary="学习率 1e-3 导致训练发散", tags="hyperparameter,learning_rate")
    """
    idea_id: str = Field(default="", description="关联的 Idea ID")
    phase: str = Field(default="", description="所属阶段")
    type: str = Field(default="", description="类型: insight/success/failure/observation")
    summary: str = Field(description="经验摘要")
    details: str = Field(default="", description="详细描述")
    tags: str = Field(default="", description="逗号分隔的标签")
    topic_id: str = Field(default="", description="关联的 Topic ID（如 T001）")


# ── paper_manager ─────────────────────────────────────────────

class CheckLocalKnowledgeParams(ToolParamsBase):
    """检查本地知识库中是否已存在匹配的资源（论文、代码库、数据集、总结）。在下载前调用，避免重复下载。支持 paper_id、标题关键词、repo 名称/URL、数据集名称模糊匹配。"""
    query: str = Field(description="搜索词（paper_id / arXiv ID / 标题关键词 / repo 名称或 URL / 数据集名称）")
    resource_type: str = Field(default="all", description="资源类型: paper/repo/summary/dataset/all（默认 all）")


class RegisterDatasetParams(ToolParamsBase):
    """注册数据集到索引并生成 dataset card。所有数据集（无论是否下载）都必须注册。

    access_mode 决定获取方式：
    - downloaded: 已下载到本地，local_path 必填
    - card_only: 仅记录元信息（数据集过大、需 API 访问、需注册等），不下载
    """
    name: str = Field(description="数据集名称")
    url: str = Field(default="", description="下载 URL 或官方页面")
    local_path: str = Field(default="", description="本地文件/目录路径（downloaded 模式必填）")
    format: str = Field(default="", description="文件格式（csv/parquet/zip/hdf5 等）")
    description: str = Field(default="", description="简要描述")
    access_mode: str = Field(default="downloaded", description="获取方式: downloaded（已下载）/ card_only（仅记录）")
    size_info: str = Field(default="", description="数据规模描述（如 '1.2GB', '100M 行'）")
    access_note: str = Field(default="", description="获取说明（card_only 时必填：如何获取数据、需要注册哪个平台等）")


class RegisterRepoParams(ToolParamsBase):
    """将已 clone 的仓库注册到索引，记录 URL、本地路径等元数据"""
    repo_url: str = Field(description="GitHub 仓库 URL")
    local_path: str = Field(description="本地仓库路径")
    has_summary: bool = Field(default=False, description="是否已生成 SUMMARY.md")


class DownloadPaperParams(ToolParamsBase):
    """下载论文 PDF 并用 MinerU 解析为 Markdown，支持后续按章节阅读。

    使用场景：需要深入阅读某篇论文时，先下载解析，再用 read_paper_section 按章节阅读。
    返回：下载状态和解析后的存储路径；已下载的论文会跳过重复下载。
    示例：download_paper(paper_id="W2741809807", title="Attention Is All You Need")
    """
    paper_id: str = Field(description="论文 ID（OpenAlex W* / arXiv ID）")
    title: str = Field(default="", description="论文标题（可选，用于索引）")


class ReadPaperSectionParams(ToolParamsBase):
    """按需阅读论文的指定章节（如 method, experiment）或按关键词搜索论文内容。

    使用场景：下载论文后按需阅读特定章节，避免一次性读取全文。section 为空时返回论文结构概览（含所有章节标题）。
    返回：指定章节的 Markdown 文本；或结构概览列表。
    示例：read_paper_section(paper_id="W2741809807", section="method")
    """
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
    """发送图片到 VLM 进行分析（实验结果可视化、曲线图等）。

    使用场景：分析实验生成的可视化图片，如 loss 曲线、指标对比图、预测结果图等。
    返回：VLM 生成的分析文本，包含图中趋势、异常点、关键数值的解读。
    示例：analyze_image(image_path="results/S01_quick_test/V1/plots/loss_curve.png", question="分析训练损失的收敛趋势")
    """
    image_path: str = Field(description="图片文件路径")
    question: str = Field(default="请分析这张图片中展示的实验结果。", description="分析问题/指令")


class AnalyzePlotsParams(ToolParamsBase):
    """批量分析目录下的所有实验结果图片。

    使用场景：一次性分析某个实验步骤的所有可视化结果，省去逐张调用 analyze_image。
    返回：每张图片的分析汇总文本，按文件名排序。
    示例：analyze_plots_dir(plots_dir="results/S01_quick_test/V1/plots", context="quick test 使用了默认超参数")
    """
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
