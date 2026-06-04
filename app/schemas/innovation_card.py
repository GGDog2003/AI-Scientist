from pydantic import BaseModel  # 导入 Pydantic 基类，用于定义创新点相关模型。
from pydantic import Field  # 导入字段描述工具，用于给模型字段补充语义说明。

from app.schemas.manuscript_review import ReviewDecision  # 导入审核决策枚举，用于导师创新点评审结果。


class InnovationCard(BaseModel):  # 定义单个创新点卡片模型。
    name: str = Field(description="创新点名称是什么。")  # 保存创新点名称。
    motivation: str = Field(description="为什么要做这个创新点。")  # 保存创新动机。
    novelty_type: str = Field(description="这个创新点属于哪一类创新。")  # 保存创新类型。
    expected_gain: str = Field(description="预期可能带来什么收益。")  # 保存预期收益。
    risk_points: list[str] = Field(description="这个创新点有哪些风险点。")  # 保存风险点列表。
    evidence: list[str] = Field(description="支持这个创新点的文献证据有哪些。")  # 保存支撑证据。


class InnovationProposal(BaseModel):  # 定义研究生提交给导师的创新点提案模型。
    cards: list[InnovationCard] = Field(description="候选创新点列表。")  # 保存候选创新点卡片列表。
    selected_focus: str = Field(description="当前最推荐的创新点名称是什么。")  # 保存主推创新点名称。
    meeting_brief: str = Field(description="给导师汇报的组会摘要是什么。")  # 保存组会汇报摘要。


class InnovationReview(BaseModel):  # 定义导师对创新点的审核结果模型。
    decision: ReviewDecision = Field(description="导师对创新点给出的审核结论是什么。")  # 保存审核结论。
    comments: list[str] = Field(description="导师提出的修改意见有哪些。")  # 保存导师意见列表。
    approved_card_name: str | None = Field(default=None, description="如果通过，具体通过的创新点名称是什么。")  # 保存被批准的创新点名称。

__all__ = ["InnovationCard", "InnovationProposal", "InnovationReview"]  # 暴露创新点相关模型，供组会与审核流程复用。
