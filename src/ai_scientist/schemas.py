from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel
from pydantic import Field


class WorkflowStatus(str, Enum):
    running = "running"
    suspended = "suspended"
    completed = "completed"


class ReviewDecision(str, Enum):
    approved = "approved"
    revise = "revise"
    accept = "accept"
    minor_revision = "minor_revision"
    major_revision = "major_revision"
    reject = "reject"


class ExperimentGateDecision(str, Enum):
    direct_to_writing = "direct_to_writing"
    minor_revision = "minor_revision"
    major_revision = "major_revision"


class LiteratureNote(BaseModel):
    title: str = Field(description="论文标题是什么。")
    venue: str = Field(description="论文来源会议或期刊是什么。")
    year: int = Field(description="论文发表年份是什么。")
    summary: str = Field(description="论文核心内容概述是什么。")
    innovation_points: list[str] = Field(description="论文的创新点有哪些。")
    limitations: list[str] = Field(description="论文的不足点有哪些。")
    base_paper: str | None = Field(default=None, description="如果有基座论文，这里写基座论文标题。")
    improvements_over_base: list[str] = Field(default_factory=list, description="相对基座论文的提升点有哪些。")


class LiteratureSynthesis(BaseModel):
    notes: list[LiteratureNote] = Field(description="已经阅读并提炼出的论文笔记列表。")
    trend_summary: str = Field(description="当前研究方向的总体趋势总结是什么。")
    possible_gaps: list[str] = Field(description="从文献中发现的潜在研究空白有哪些。")


class InnovationCard(BaseModel):
    name: str = Field(description="创新点名称是什么。")
    motivation: str = Field(description="为什么要做这个创新点。")
    novelty_type: str = Field(description="创新点属于哪一类创新。")
    expected_gain: str = Field(description="预期可能提升什么效果。")
    risk_points: list[str] = Field(description="这个创新点的风险点有哪些。")
    evidence: list[str] = Field(description="哪些文献证据支持这个创新点。")


class InnovationProposal(BaseModel):
    cards: list[InnovationCard] = Field(description="候选创新点列表。")
    selected_focus: str = Field(description="研究生当前最看好的主创新点是什么。")
    meeting_brief: str = Field(description="给导师组会汇报的简要说明是什么。")


class InnovationReview(BaseModel):
    decision: ReviewDecision = Field(description="导师对创新点给出的审核结论是什么。")
    comments: list[str] = Field(description="导师的逐条修改意见有哪些。")
    approved_card_name: str | None = Field(default=None, description="如果通过，对应通过的创新点名称是什么。")


class ExperimentPlan(BaseModel):
    objective: str = Field(description="本次实验要验证什么研究问题。")
    datasets: list[str] = Field(description="要使用哪些数据集。")
    baselines: list[str] = Field(description="需要对比哪些 baseline。")
    metrics: list[str] = Field(description="使用哪些评价指标。")
    ablations: list[str] = Field(description="需要做哪些消融实验。")
    python_modules: list[str] = Field(description="建议生成哪些 Python 模块。")
    execution_steps: list[str] = Field(description="人类运行实验时需要执行哪些步骤。")


class ResultAnalysis(BaseModel):
    summary: str = Field(description="实验结果总览是什么。")
    key_findings: list[str] = Field(description="结果中最重要的发现有哪些。")
    claims_boundary: list[str] = Field(description="哪些结论可以说，哪些不能夸大。")
    paper_storyline: list[str] = Field(description="论文话术和叙事主线怎么组织。")


class ExperimentGateReview(BaseModel):
    decision: ExperimentGateDecision = Field(description="导师基于实验结果给出的流程决策。")
    comments: list[str] = Field(description="导师针对实验结果给出的后续建议。")


class ManuscriptDraft(BaseModel):
    title: str = Field(description="论文标题是什么。")
    abstract: str = Field(description="论文摘要内容是什么。")
    introduction: str = Field(description="论文引言内容是什么。")
    related_work: str = Field(description="相关工作内容是什么。")
    method: str = Field(description="方法章节内容是什么。")
    experiments: str = Field(description="实验章节内容是什么。")
    conclusion: str = Field(description="结论章节内容是什么。")
    references: list[str] = Field(description="参考文献条目有哪些。")
    self_review_notes: list[str] = Field(description="研究生自审时发现的问题和确认事项有哪些。")


class PaperReview(BaseModel):
    decision: ReviewDecision = Field(description="导师对论文给出的结论是什么。")
    major_issues: list[str] = Field(description="论文存在的主要问题有哪些。")
    minor_issues: list[str] = Field(description="论文存在的次要问题有哪些。")
    required_changes: list[str] = Field(description="要求研究生必须修改的内容有哪些。")


class BlindReview(BaseModel):
    decision: ReviewDecision = Field(description="审稿人的最终结论是什么。")
    summary: str = Field(description="审稿总体评价是什么。")
    strengths: list[str] = Field(description="论文优点有哪些。")
    weaknesses: list[str] = Field(description="论文缺点有哪些。")
    required_changes: list[str] = Field(description="作者需要修改的内容有哪些。")
    confidence: str = Field(description="审稿人对自己的判断的置信度如何。")


class ArtifactRecord(BaseModel):
    bucket: str = Field(description="工件属于哪个目录桶。")
    path: str = Field(description="工件的相对路径是什么。")
    title: str = Field(description="工件标题是什么。")
    stage: str = Field(description="工件属于哪个工作流阶段。")


class AgentMessage(BaseModel):
    message_id: str = Field(description="消息唯一标识是什么。")
    from_agent: str = Field(description="消息由哪个角色发送。")
    to_agent: str = Field(description="消息要发给哪个角色。")
    stage: str = Field(description="消息属于哪个阶段。")
    artifact_type: str = Field(description="提交的工件类型是什么。")
    artifact_path: str = Field(description="提交工件的路径是什么。")
    summary: str = Field(description="消息概要是什么。")
    metadata: dict[str, Any] = Field(default_factory=dict, description="附加元数据有哪些。")


__all__ = [
    "AgentMessage",
    "ArtifactRecord",
    "BlindReview",
    "ExperimentGateDecision",
    "ExperimentGateReview",
    "ExperimentPlan",
    "InnovationCard",
    "InnovationProposal",
    "InnovationReview",
    "LiteratureNote",
    "LiteratureSynthesis",
    "ManuscriptDraft",
    "PaperReview",
    "ResultAnalysis",
    "ReviewDecision",
    "WorkflowStatus",
]
