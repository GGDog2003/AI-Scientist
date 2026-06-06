from enum import Enum

from pydantic import BaseModel
from pydantic import Field


class ResultAnalysis(BaseModel):
    summary: str = Field(description="实验结果的整体总结是什么。")
    key_findings: list[str] = Field(description="最关键的实验发现有哪些。")
    claims_boundary: list[str] = Field(description="哪些结论可以写进论文，哪些结论不能夸大。")
    paper_storyline: list[str] = Field(description="论文叙事主线怎么组织。")


class ExperimentGateDecision(str, Enum):
    direct_to_writing = "direct_to_writing"
    minor_revision = "minor_revision"
    major_revision = "major_revision"


class ExperimentGateReview(BaseModel):
    decision: ExperimentGateDecision = Field(description="导师基于实验结果给出的流程决策。")
    comments: list[str] = Field(description="导师针对实验结果给出的后续建议。")


__all__ = ["ExperimentGateDecision", "ExperimentGateReview", "ResultAnalysis"]
