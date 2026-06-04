from pydantic import BaseModel  # 导入 Pydantic 基类，用于定义实验结果分析模型。
from pydantic import Field  # 导入字段描述工具，用于增强结构化输出语义。


class ResultAnalysis(BaseModel):  # 定义实验结果解读与论文话术分析模型。
    summary: str = Field(description="实验结果的整体总结是什么。")  # 保存实验结果整体总结。
    key_findings: list[str] = Field(description="最关键的实验发现有哪些。")  # 保存关键发现列表。
    claims_boundary: list[str] = Field(description="哪些结论可以写进论文，哪些结论不能夸大。")  # 保存结论边界。
    paper_storyline: list[str] = Field(description="论文叙事主线怎么组织。")  # 保存论文叙事建议。

__all__ = ["ResultAnalysis"]  # 暴露结果分析模型，供论文写作阶段引用。
