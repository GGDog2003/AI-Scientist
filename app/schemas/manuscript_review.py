from enum import Enum  # 导入枚举基类，用于定义审核结论常量。

from pydantic import BaseModel  # 导入 Pydantic 基类，用于定义论文和审稿相关模型。
from pydantic import Field  # 导入字段描述工具，用于补充结构化字段语义。


class ReviewDecision(str, Enum):  # 定义审核决策枚举。
    approved = "approved"  # 表示审核通过，可进入下一阶段。
    revise = "revise"  # 表示需要修改后重新提交。
    accept = "accept"  # 表示终稿可直接接受。
    minor_revision = "minor_revision"  # 表示小修后接受。
    major_revision = "major_revision"  # 表示大修后再审。
    reject = "reject"  # 表示当前版本拒稿或建议放弃。


class ManuscriptDraft(BaseModel):  # 定义研究生撰写的论文草稿模型。
    title: str = Field(description="论文标题是什么。")  # 保存论文标题。
    abstract: str = Field(description="论文摘要内容是什么。")  # 保存摘要内容。
    introduction: str = Field(description="论文引言内容是什么。")  # 保存引言内容。
    related_work: str = Field(description="相关工作章节内容是什么。")  # 保存相关工作章节。
    method: str = Field(description="方法章节内容是什么。")  # 保存方法章节。
    experiments: str = Field(description="实验章节内容是什么。")  # 保存实验章节。
    conclusion: str = Field(description="结论章节内容是什么。")  # 保存结论章节。
    references: list[str] = Field(description="参考文献条目有哪些。")  # 保存参考文献条目。
    self_review_notes: list[str] = Field(description="研究生自审记录有哪些。")  # 保存研究生自审记录。


class PaperReview(BaseModel):  # 定义导师对论文的二审输出模型。
    decision: ReviewDecision = Field(description="导师对论文给出的结论是什么。")  # 保存导师审核结论。
    major_issues: list[str] = Field(description="论文存在的主要问题有哪些。")  # 保存主要问题列表。
    minor_issues: list[str] = Field(description="论文存在的次要问题有哪些。")  # 保存次要问题列表。
    required_changes: list[str] = Field(description="论文必须修改的内容有哪些。")  # 保存必须修改项。


class BlindReview(BaseModel):  # 定义审稿人盲审输出模型。
    decision: ReviewDecision = Field(description="审稿人的最终结论是什么。")  # 保存盲审结论。
    summary: str = Field(description="审稿总体评价是什么。")  # 保存总体评价。
    strengths: list[str] = Field(description="论文的优点有哪些。")  # 保存优点列表。
    weaknesses: list[str] = Field(description="论文的缺点有哪些。")  # 保存缺点列表。
    required_changes: list[str] = Field(description="作者必须修改的内容有哪些。")  # 保存必须修改项。
    confidence: str = Field(description="审稿置信度如何。")  # 保存置信度说明。

__all__ = ["ReviewDecision", "ManuscriptDraft", "PaperReview", "BlindReview"]  # 暴露论文与审稿相关模型，供论文流程引用。
