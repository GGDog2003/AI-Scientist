from __future__ import annotations  # 启用延后类型注解，便于模型之间互相引用。

from enum import Enum  # 导入枚举基类，便于定义有限状态值。
from typing import Any  # 导入 Any，用于通用字典字段标注。

from pydantic import BaseModel  # 导入 Pydantic 基类，便于定义结构化输出模型。
from pydantic import Field  # 导入字段描述工具，便于给模型字段补充语义说明。


class WorkflowStatus(str, Enum):  # 定义工作流状态枚举，统一控制图执行语义。
    running = "running"  # 表示工作流当前继续执行中。
    suspended = "suspended"  # 表示工作流当前已挂起等待输入。
    completed = "completed"  # 表示工作流已全部结束。


class ReviewDecision(str, Enum):  # 定义审核决策枚举，统一描述打回和通过结果。
    approved = "approved"  # 表示审核通过，可进入下一阶段。
    revise = "revise"  # 表示需要修改后重新提交。
    accept = "accept"  # 表示论文被接受，可直接终稿。
    minor_revision = "minor_revision"  # 表示小修后可接受。
    major_revision = "major_revision"  # 表示大修后再审。
    reject = "reject"  # 表示当前版本拒稿或建议放弃。


class LiteratureNote(BaseModel):  # 定义单篇论文阅读笔记模型。
    title: str = Field(description="论文标题是什么。")  # 保存论文标题，便于后续索引和引用。
    venue: str = Field(description="论文来源会议或期刊是什么。")  # 保存论文来源，便于判断顶会顶刊背景。
    year: int = Field(description="论文发表年份是什么。")  # 保存发表年份，便于分析研究趋势。
    summary: str = Field(description="论文核心内容概述是什么。")  # 保存论文概要，便于快速回顾。
    innovation_points: list[str] = Field(description="论文的创新点有哪些。")  # 保存论文创新点，便于汇总提炼。
    limitations: list[str] = Field(description="论文的不足点有哪些。")  # 保存论文不足点，便于寻找可改进空间。
    base_paper: str | None = Field(default=None, description="如果有基座论文，这里写基座论文标题。")  # 保存基座论文信息，便于追踪改进来源。
    improvements_over_base: list[str] = Field(default_factory=list, description="相对基座论文的提升点有哪些。")  # 保存相对基座论文的提升点。


class LiteratureSynthesis(BaseModel):  # 定义文献调研汇总模型。
    notes: list[LiteratureNote] = Field(description="已经阅读并提炼出的论文笔记列表。")  # 保存全部论文笔记。
    trend_summary: str = Field(description="当前研究方向的总体趋势总结是什么。")  # 保存研究趋势总结。
    possible_gaps: list[str] = Field(description="从文献中发现的潜在研究空白有哪些。")  # 保存潜在空白点，便于后续创新设计。


class InnovationCard(BaseModel):  # 定义单个创新点卡片模型。
    name: str = Field(description="创新点名称是什么。")  # 保存创新点名称，便于组会与版本管理。
    motivation: str = Field(description="为什么要做这个创新点。")  # 保存创新动机，便于导师审核。
    novelty_type: str = Field(description="创新点属于哪一类创新。")  # 保存创新类型，便于判断是否增量。
    expected_gain: str = Field(description="预期可能提升什么效果。")  # 保存预期收益，便于实验设计。
    risk_points: list[str] = Field(description="这个创新点的风险点有哪些。")  # 保存风险点，便于提前规避。
    evidence: list[str] = Field(description="哪些文献证据支持这个创新点。")  # 保存支撑证据，便于形成学术链路。


class InnovationProposal(BaseModel):  # 定义创新点提案模型。
    cards: list[InnovationCard] = Field(description="候选创新点列表。")  # 保存多个候选创新点。
    selected_focus: str = Field(description="研究生当前最看好的主创新点是什么。")  # 保存当前最推荐的创新点。
    meeting_brief: str = Field(description="给导师组会汇报的简要说明是什么。")  # 保存汇报摘要，便于导师快速判断。


class InnovationReview(BaseModel):  # 定义导师对创新点的审核输出模型。
    decision: ReviewDecision = Field(description="导师对创新点给出的审核结论是什么。")  # 保存创新点审核结果。
    comments: list[str] = Field(description="导师的逐条修改意见有哪些。")  # 保存具体修改意见。
    approved_card_name: str | None = Field(default=None, description="如果通过，对应通过的创新点名称是什么。")  # 保存被批准的创新点名称。


class ExperimentPlan(BaseModel):  # 定义实验设计方案模型。
    objective: str = Field(description="本次实验要验证什么研究问题。")  # 保存实验目标。
    datasets: list[str] = Field(description="要使用哪些数据集。")  # 保存实验数据集列表。
    baselines: list[str] = Field(description="需要对比哪些 baseline。")  # 保存对照方法列表。
    metrics: list[str] = Field(description="使用哪些评价指标。")  # 保存评价指标列表。
    ablations: list[str] = Field(description="需要做哪些消融实验。")  # 保存消融实验列表。
    python_modules: list[str] = Field(description="建议生成哪些 Python 模块。")  # 保存代码框架模块列表。
    execution_steps: list[str] = Field(description="人类运行实验时需要执行哪些步骤。")  # 保存人工执行步骤。


class ResultAnalysis(BaseModel):  # 定义实验结果分析模型。
    summary: str = Field(description="实验结果总览是什么。")  # 保存结果总结。
    key_findings: list[str] = Field(description="结果中最重要的发现有哪些。")  # 保存关键发现。
    claims_boundary: list[str] = Field(description="哪些结论可以说，哪些不能夸大。")  # 保存结论边界，避免学术失真。
    paper_storyline: list[str] = Field(description="论文话术和叙事主线怎么组织。")  # 保存论文叙事建议。


class ManuscriptDraft(BaseModel):  # 定义论文初稿模型。
    title: str = Field(description="论文标题是什么。")  # 保存论文标题。
    abstract: str = Field(description="论文摘要内容是什么。")  # 保存摘要正文。
    introduction: str = Field(description="论文引言内容是什么。")  # 保存引言正文。
    related_work: str = Field(description="相关工作内容是什么。")  # 保存相关工作章节。
    method: str = Field(description="方法章节内容是什么。")  # 保存方法章节。
    experiments: str = Field(description="实验章节内容是什么。")  # 保存实验章节。
    conclusion: str = Field(description="结论章节内容是什么。")  # 保存结论章节。
    references: list[str] = Field(description="参考文献条目有哪些。")  # 保存参考文献条目。
    self_review_notes: list[str] = Field(description="研究生自审时发现的问题和确认事项有哪些。")  # 保存自审记录。


class PaperReview(BaseModel):  # 定义导师二审输出模型。
    decision: ReviewDecision = Field(description="导师对论文给出的结论是什么。")  # 保存论文二审结论。
    major_issues: list[str] = Field(description="论文存在的主要问题有哪些。")  # 保存主要问题列表。
    minor_issues: list[str] = Field(description="论文存在的次要问题有哪些。")  # 保存次要问题列表。
    required_changes: list[str] = Field(description="要求研究生必须修改的内容有哪些。")  # 保存必须修改的事项。


class BlindReview(BaseModel):  # 定义审稿人盲审输出模型。
    decision: ReviewDecision = Field(description="审稿人的最终结论是什么。")  # 保存盲审结论。
    summary: str = Field(description="审稿总体评价是什么。")  # 保存总体评价摘要。
    strengths: list[str] = Field(description="论文优点有哪些。")  # 保存论文优点。
    weaknesses: list[str] = Field(description="论文缺点有哪些。")  # 保存论文缺点。
    required_changes: list[str] = Field(description="作者需要修改的内容有哪些。")  # 保存必须修改的项目。
    confidence: str = Field(description="审稿人对自己判断的置信度如何。")  # 保存置信度说明。


class ArtifactRecord(BaseModel):  # 定义工件记录模型。
    bucket: str = Field(description="工件属于哪个目录桶。")  # 保存工件目录类型。
    path: str = Field(description="工件的相对路径是什么。")  # 保存工件路径。
    title: str = Field(description="工件标题是什么。")  # 保存工件标题。
    stage: str = Field(description="工件属于哪个工作流阶段。")  # 保存工件阶段。


class AgentMessage(BaseModel):  # 定义 Agent 间消息模型。
    message_id: str = Field(description="消息唯一标识是什么。")  # 保存消息唯一 ID。
    from_agent: str = Field(description="消息由哪个角色发送。")  # 保存发送角色。
    to_agent: str = Field(description="消息要发给哪个角色。")  # 保存接收角色。
    stage: str = Field(description="消息属于哪个阶段。")  # 保存当前阶段名。
    artifact_type: str = Field(description="提交的工件类型是什么。")  # 保存提交工件类型。
    artifact_path: str = Field(description="提交工件的路径是什么。")  # 保存提交工件路径。
    summary: str = Field(description="消息概要是什么。")  # 保存消息摘要。
    metadata: dict[str, Any] = Field(default_factory=dict, description="附加元数据有哪些。")  # 保存挂起、恢复等扩展信息。
