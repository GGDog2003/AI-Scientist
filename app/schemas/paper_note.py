from pydantic import BaseModel  # 导入 Pydantic 基类，用于定义结构化论文笔记模型。
from pydantic import Field  # 导入字段描述工具，用于增强模型可读性。


class LiteratureNote(BaseModel):  # 定义单篇论文阅读笔记模型。
    title: str = Field(description="论文标题是什么。")  # 保存论文标题。
    venue: str = Field(description="论文来源会议或期刊是什么。")  # 保存论文来源。
    year: int = Field(description="论文发表年份是什么。")  # 保存发表年份。
    summary: str = Field(description="论文核心内容概述是什么。")  # 保存论文摘要总结。
    innovation_points: list[str] = Field(description="论文的创新点有哪些。")  # 保存论文创新点列表。
    limitations: list[str] = Field(description="论文的不足点有哪些。")  # 保存论文不足点列表。
    base_paper: str | None = Field(default=None, description="如果存在基座论文，这里写基座论文标题。")  # 保存基座论文标题。
    improvements_over_base: list[str] = Field(default_factory=list, description="相对基座论文的提升点有哪些。")  # 保存相对基座论文的改进点。


class LiteratureSynthesis(BaseModel):  # 定义文献调研汇总模型。
    notes: list[LiteratureNote] = Field(description="当前已阅读并提炼出的论文笔记列表。")  # 保存全部论文笔记。
    trend_summary: str = Field(description="当前研究方向的趋势总结是什么。")  # 保存研究趋势总结。
    possible_gaps: list[str] = Field(description="从现有文献中发现的潜在研究空白有哪些。")  # 保存潜在研究空白点。


__all__ = ["LiteratureNote", "LiteratureSynthesis"]  # 暴露文献相关模型，供研究生 Agent 和工作流使用。
