from app.agents.base_agent import BaseAgent  # 导出基础 Agent 类型，便于子模块统一引用。
from app.agents.student_agent import StudentAgent  # 导出研究生 Agent 类型。
from app.agents.advisor_agent import AdvisorAgent  # 导出导师 Agent 类型。
from app.agents.reviewer_agent import ReviewerAgent  # 导出审稿人 Agent 类型。

__all__ = ["BaseAgent", "StudentAgent", "AdvisorAgent", "ReviewerAgent"]  # 显式声明导出对象，保持接口清晰。
