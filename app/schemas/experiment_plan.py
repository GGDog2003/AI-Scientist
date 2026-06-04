from pydantic import BaseModel  # 导入 Pydantic 基类，用于定义实验方案模型。
from pydantic import Field  # 导入字段描述工具，用于补充模型字段语义说明。


class ExperimentPlan(BaseModel):  # 定义实验设计方案模型。
    objective: str = Field(description="本次实验要验证什么研究问题。")  # 保存实验目标。
    datasets: list[str] = Field(description="实验要使用哪些数据集。")  # 保存数据集列表。
    baselines: list[str] = Field(description="实验需要对比哪些 baseline。")  # 保存对照方法列表。
    metrics: list[str] = Field(description="实验使用哪些评价指标。")  # 保存评价指标列表。
    ablations: list[str] = Field(description="实验需要做哪些消融实验。")  # 保存消融实验列表。
    python_modules: list[str] = Field(description="建议生成哪些 Python 代码模块。")  # 保存建议代码模块列表。
    execution_steps: list[str] = Field(description="人类执行实验时需要完成哪些步骤。")  # 保存人工实验步骤列表。

__all__ = ["ExperimentPlan"]  # 暴露实验方案模型，供实验设计流程引用。
