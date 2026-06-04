from __future__ import annotations  # 启用延后类型注解，便于在类方法签名中引用后续定义的类型。

import json  # 导入 json，用于把任务负载格式化为模型可读的文本。
from typing import Any  # 导入 Any，用于标注通用任务负载类型。
from typing import TypeVar  # 导入 TypeVar，用于定义结构化输出泛型。

from langchain.agents import create_agent  # 导入 LangChain create_agent，用于构建支持工具调用的 Agent。
from langchain.chat_models import init_chat_model  # 导入通用聊天模型初始化函数，用于兼容 OpenAI 风格提供商。
from langchain_core.messages import HumanMessage  # 导入 HumanMessage，用于构造用户消息。
from langchain_core.messages import SystemMessage  # 导入 SystemMessage，用于构造系统提示消息。
from pydantic import BaseModel  # 导入 Pydantic 基类，用于约束结构化输出模型。

from app.config import AppSettings  # 导入项目配置对象，用于控制模型和 stub 模式。
from app.prompts import ADVISOR_SYSTEM_PROMPT  # 导入导师角色系统提示词。
from app.prompts import REVIEWER_SYSTEM_PROMPT  # 导入审稿人角色系统提示词。
from app.prompts import STUDENT_SYSTEM_PROMPT  # 导入研究生角色系统提示词。
from app.schemas.experiment_plan import ExperimentPlan  # 导入实验方案结构化输出模型。
from app.schemas.experiment_result import ResultAnalysis  # 导入实验结果分析结构化输出模型。
from app.schemas.innovation_card import InnovationCard  # 导入创新点卡片模型。
from app.schemas.innovation_card import InnovationProposal  # 导入创新点提案模型。
from app.schemas.innovation_card import InnovationReview  # 导入创新点评审模型。
from app.schemas.manuscript_review import BlindReview  # 导入盲审结构化输出模型。
from app.schemas.manuscript_review import ManuscriptDraft  # 导入论文草稿结构化输出模型。
from app.schemas.manuscript_review import PaperReview  # 导入导师论文审核结构化输出模型。
from app.schemas.manuscript_review import ReviewDecision  # 导入审核结论枚举，用于 stub 决策。
from app.schemas.paper_note import LiteratureNote  # 导入单篇论文笔记模型。
from app.schemas.paper_note import LiteratureSynthesis  # 导入文献调研汇总模型。

StructuredModel = TypeVar("StructuredModel", bound=BaseModel)  # 定义结构化输出泛型，约束为 Pydantic 模型。


class BaseAgent:  # 定义所有角色 Agent 共用的基础行为封装。
    def __init__(self, settings: AppSettings, role_name: str, system_prompt: str, tools: list) -> None:  # 初始化基础 Agent。
        self.settings = settings  # 保存全局配置对象，便于后续统一读取模型和运行模式。
        self.role_name = role_name  # 保存角色名称，便于调试和日志输出。
        self.system_prompt = system_prompt  # 保存角色系统提示词，约束当前 Agent 的职责边界。
        self.tools = tools  # 保存工具列表，便于在兼容模型上继续走 ReAct 风格调用。
        self.model = None if settings.use_stub_agent else self._build_model()  # 如果不是 stub 模式，就提前初始化真实模型。

    def _build_model(self):  # 构建 LangChain 聊天模型实例。
        if self.settings.model_provider:  # 判断是否显式指定了模型提供商。
            return init_chat_model(self.settings.model_name, model_provider=self.settings.model_provider, temperature=self.settings.temperature)  # 按 provider + model 形式初始化模型。
        return init_chat_model(self.settings.model_name, temperature=self.settings.temperature)  # 在未指定 provider 时交给 LangChain 默认推断。

    def _invoke_structured_direct(self, task_name: str, payload: dict[str, Any], response_model: type[StructuredModel]) -> StructuredModel:  # 使用无工具的结构化输出模式直接调用模型。
        structured_model = self.model.with_structured_output(response_model)  # 让底层聊天模型直接按目标 Pydantic 模型返回结构化结果。
        messages = [  # 构造最小消息列表，避免再触发工具选择相关的兼容性问题。
            SystemMessage(content=self.system_prompt),  # 写入当前角色的系统提示词，保持角色职责不变。
            HumanMessage(content=json.dumps({"task_name": task_name, "payload": payload}, ensure_ascii=False, indent=2)),  # 把任务名和负载格式化为 JSON 文本发给模型。
        ]  # 结束消息列表构造。
        result = structured_model.invoke(messages)  # 直接调用结构化输出模型，获取目标结果。
        return result if isinstance(result, response_model) else response_model.model_validate(result)  # 确保最终返回值严格匹配目标 Pydantic 模型。

    def _should_fallback_to_direct(self, error: Exception) -> bool:  # 判断当前异常是否属于应自动回退到无工具模式的模型兼容性问题。
        message = str(error)  # 提取异常文本，便于按关键字识别兼容性问题。
        fallback_markers = (  # 定义需要触发回退的关键字集合。
            "tool_choice",  # 覆盖 DeepSeek thinking mode 不支持 tool_choice 的错误。
            "Thinking mode does not support this tool_choice",  # 覆盖当前已出现的明确报错文本。
            "invalid_request_error",  # 覆盖某些兼容网关把工具参数错误统一包装成 invalid_request_error 的情况。
        )  # 结束关键字定义。
        return any(marker in message for marker in fallback_markers)  # 只要命中任一关键字，就判定应切换到直接结构化输出模式。

    def _invoke_structured(self, task_name: str, payload: dict[str, Any], response_model: type[StructuredModel]) -> StructuredModel:  # 用统一方式执行结构化任务。
        if self.settings.use_stub_agent:  # 判断当前是否处于离线 stub 模式。
            return self._stub_response(task_name=task_name, payload=payload, response_model=response_model)  # 使用本地规则生成结构化结果。
        if not self.tools:  # 判断当前角色是否根本没有可用工具。
            return self._invoke_structured_direct(task_name=task_name, payload=payload, response_model=response_model)  # 没有工具时直接走结构化输出调用。
        try:  # 先优先尝试原来的 Agent + Tools 路径，尽量保持 ReAct 能力。
            agent = create_agent(model=self.model, tools=self.tools, system_prompt=self.system_prompt, response_format=response_model)  # 构建 LangChain Agent，使其在节点内部可循环调用工具。
            user_message = {"role": "user", "content": json.dumps({"task_name": task_name, "payload": payload}, ensure_ascii=False, indent=2)}  # 把任务名和负载格式化成 JSON 用户消息文本。
            result = agent.invoke({"messages": [user_message]})  # 执行 Agent 并返回最终状态。
            structured = result["structured_response"]  # 读取结构化响应内容。
            return structured if isinstance(structured, response_model) else response_model.model_validate(structured)  # 确保返回值最终校验成目标模型。
        except Exception as error:  # 捕获工具型 Agent 调用失败的异常，便于做兼容回退。
            if self._should_fallback_to_direct(error):  # 判断是否命中了 DeepSeek 等模型的工具兼容性问题。
                return self._invoke_structured_direct(task_name=task_name, payload=payload, response_model=response_model)  # 自动退回无工具结构化模式，优先保证工作流可运行。
            raise  # 如果不是已知兼容性问题，就保留原异常继续抛出，避免吞掉真实错误。

    def _stub_response(self, task_name: str, payload: dict[str, Any], response_model: type[StructuredModel]) -> StructuredModel:  # 在无模型依赖时生成一个可运行的本地结构化结果。
        if response_model is LiteratureSynthesis:  # 判断当前任务是否需要产出文献综述。
            paper_paths = payload.get("paper_paths") or ["未提供论文路径"]  # 读取论文路径列表，如无则给一个占位值。
            notes = [  # 根据传入论文路径构造示例论文笔记列表。
                LiteratureNote(  # 创建单篇论文笔记对象。
                    title=f"示例论文 {index}",  # 使用顺序号生成示例标题。
                    venue="DemoConf",  # 生成示例会议名称。
                    year=2025,  # 生成示例年份。
                    summary=f"这是对论文 {paper_path} 的离线调试摘要。",  # 生成离线模式摘要。
                    innovation_points=[f"创新点{index}A", f"创新点{index}B"],  # 生成示例创新点列表。
                    limitations=[f"不足点{index}A", f"不足点{index}B"],  # 生成示例不足点列表。
                    base_paper=f"基座论文 {index}" if index % 2 == 0 else None,  # 偶数序号时生成基座论文名称。
                    improvements_over_base=["提升了特征融合", "优化了训练稳定性"] if index % 2 == 0 else [],  # 偶数序号时生成改进点。
                )  # 结束单篇论文笔记创建。
                for index, paper_path in enumerate(paper_paths[:10], start=1)  # 最多读取前十篇论文做模拟。
            ]  # 结束笔记列表推导。
            return response_model.model_validate({"notes": [note.model_dump() for note in notes], "trend_summary": "近期研究趋势集中在轻量模块增强、多尺度建模和训练策略优化。", "possible_gaps": ["现有方法对弱边界目标提升有限", "对计算成本与效果的平衡研究不足"]})  # 返回结构化文献综述结果。
        if response_model is InnovationProposal:  # 判断当前任务是否需要产出创新点提案。
            cards = [  # 构造三个示例创新点卡片。
                InnovationCard(name="自适应边界增强模块", motivation="针对弱边界目标分割不稳定的问题提出模块增强。", novelty_type="module_improvement", expected_gain="提升边界区域的 mIoU 与 F1。", risk_points=["模块增益可能不稳定", "参数量可能上升"], evidence=["多篇论文都指出边界区域是性能瓶颈"]),  # 创建第一个创新点。
                InnovationCard(name="多尺度语义一致性损失", motivation="缓解不同尺度特征学习目标不一致的问题。", novelty_type="loss_function", expected_gain="提升模型泛化能力和跨数据集稳定性。", risk_points=["损失设计可能过于复杂", "训练收敛速度可能下降"], evidence=["现有工作对损失层面的探索较少"]),  # 创建第二个创新点。
                InnovationCard(name="教师反馈引导的伪标签筛选", motivation="在半监督设置下过滤低质量伪标签。", novelty_type="training_strategy", expected_gain="提升半监督实验中的标签利用效率。", risk_points=["额外训练阶段带来时间开销"], evidence=["近年半监督论文强调伪标签质量控制"]),  # 创建第三个创新点。
            ]  # 结束创新点卡片列表构造。
            return response_model.model_validate({"cards": [card.model_dump() for card in cards], "selected_focus": cards[0].name, "meeting_brief": "建议优先验证边界增强方向，因为证据更充分且实现成本较低。"})  # 返回结构化创新点提案结果。
        if response_model is InnovationReview:  # 判断当前任务是否需要导师审核创新点。
            round_number = int(payload.get("review_round", 0))  # 读取当前审核轮次。
            proposal = payload.get("proposal", {})  # 读取创新点提案内容。
            first_card_name = proposal.get("cards", [{}])[0].get("name") if proposal.get("cards") else None  # 尝试读取第一个创新点名称。
            decision = ReviewDecision.revise if round_number == 0 else ReviewDecision.approved  # 第一轮先打回，第二轮开始通过。
            return response_model.model_validate({"decision": decision, "comments": ["需要补充与最新相关工作的差异性说明。"] if decision == ReviewDecision.revise else ["创新点已经具备实验验证价值，可以进入实验阶段。"], "approved_card_name": None if decision == ReviewDecision.revise else first_card_name})  # 返回结构化创新点审核结果。
        if response_model is ExperimentPlan:  # 判断当前任务是否需要实验设计方案。
            innovation_name = payload.get("approved_innovation", {}).get("name", "示例创新点")  # 读取已通过创新点名称。
            return response_model.model_validate({"objective": f"验证 {innovation_name} 是否能够稳定提升目标任务性能。", "datasets": ["Dataset-A", "Dataset-B"], "baselines": ["Baseline-1", "Baseline-2"], "metrics": ["mIoU", "F1", "Accuracy"], "ablations": ["去掉新增模块", "替换损失函数", "改变训练策略"], "python_modules": ["train.py", "eval.py", "models/custom_module.py", "configs/default.yaml"], "execution_steps": ["准备数据集", "安装依赖", "执行训练", "执行评估", "整理日志和结果表"]})  # 返回结构化实验方案。
        if response_model is ResultAnalysis:  # 判断当前任务是否需要实验结果分析。
            metrics = payload.get("human_result", {}).get("metrics", {})  # 读取人工反馈的实验指标。
            return response_model.model_validate({"summary": f"实验结果显示目标方法在核心指标上取得提升，原始指标为：{metrics}。", "key_findings": ["主要增益集中在边界相关指标。", "新增模块带来的收益高于损失项微调。"], "claims_boundary": ["可以表述为在当前实验设置下有效。", "不能宣称对所有任务都普适提升。"], "paper_storyline": ["文献空白 -> 创新动机", "方法设计 -> 实验验证", "结果优势 -> 局限与未来工作"]})  # 返回结构化结果分析。
        if response_model is ManuscriptDraft:  # 判断当前任务是否需要论文草稿。
            focus = payload.get("approved_innovation", {}).get("name", "目标创新点")  # 读取当前论文聚焦的创新点名称。
            return response_model.model_validate({"title": f"面向目标任务的 {focus} 方法研究", "abstract": "本文围绕目标任务中的性能瓶颈，提出了一种可验证的改进方法，并通过真实实验进行评估。", "introduction": "引言部分说明问题背景、现有不足和本文创新点。", "related_work": "相关工作部分对比模块改进、损失函数设计和训练策略三条主线。", "method": "方法部分详细描述模块设计、数据流向和训练目标。", "experiments": "实验部分报告数据集、对照组、指标、消融实验和误差分析。", "conclusion": "结论部分总结当前方法有效性、局限性和未来改进方向。", "references": ["[1] Example Reference A.", "[2] Example Reference B."], "self_review_notes": ["已核对实验结果来自人工反馈。", "已避免使用超出证据范围的夸大表述。"]})  # 返回结构化论文草稿。
        if response_model is PaperReview:  # 判断当前任务是否需要导师论文二审。
            round_number = int(payload.get("review_round", 0))  # 读取当前导师审核轮次。
            decision = ReviewDecision.revise if round_number == 0 else ReviewDecision.approved  # 第一轮打回，第二轮通过。
            return response_model.model_validate({"decision": decision, "major_issues": ["方法描述还不够精确，需要补充关键设计动机。"] if decision == ReviewDecision.revise else [], "minor_issues": ["引言中部分表述可以进一步压缩。"], "required_changes": ["补充方法与实验现象之间的呼应分析。"] if decision == ReviewDecision.revise else ["保留终稿前最后一次通读。"]})  # 返回结构化导师审核结果。
        if response_model is BlindReview:  # 判断当前任务是否需要审稿人盲审。
            round_number = int(payload.get("review_round", 0))  # 读取盲审轮次。
            decision = ReviewDecision.minor_revision if round_number == 0 else ReviewDecision.accept  # 第一轮小修，第二轮接受。
            return response_model.model_validate({"decision": decision, "summary": "论文整体完整，实验可信，但部分分析仍可更凝练。", "strengths": ["问题定义明确", "实验设计较完整", "创新点与结果形成呼应"], "weaknesses": ["局限性讨论略短", "图表自解释性还有提升空间"], "required_changes": ["补充局限性分析段落", "优化表格说明文字"] if decision == ReviewDecision.minor_revision else ["整理最终排版。"], "confidence": "medium"})  # 返回结构化盲审结果。
        raise ValueError(f"Unsupported response model: {response_model}")  # 如果传入未知结构化模型，就显式抛出异常。


class StudentAgent(BaseAgent):  # 定义研究生角色 Agent。
    def __init__(self, settings: AppSettings, tools: list) -> None:  # 初始化研究生角色 Agent。
        super().__init__(settings=settings, role_name="student", system_prompt=STUDENT_SYSTEM_PROMPT, tools=tools)  # 调用父类初始化逻辑。

    def summarize_literature(self, payload: dict[str, Any]) -> LiteratureSynthesis:  # 执行文献阅读与汇总任务。
        return self._invoke_structured(task_name="summarize_literature", payload=payload, response_model=LiteratureSynthesis)  # 返回结构化文献汇总结果。

    def propose_innovations(self, payload: dict[str, Any]) -> InnovationProposal:  # 执行创新点提案任务。
        return self._invoke_structured(task_name="propose_innovations", payload=payload, response_model=InnovationProposal)  # 返回结构化创新点提案。

    def design_experiment(self, payload: dict[str, Any]) -> ExperimentPlan:  # 执行实验设计任务。
        return self._invoke_structured(task_name="design_experiment", payload=payload, response_model=ExperimentPlan)  # 返回结构化实验方案。

    def analyze_results(self, payload: dict[str, Any]) -> ResultAnalysis:  # 执行实验结果分析任务。
        return self._invoke_structured(task_name="analyze_results", payload=payload, response_model=ResultAnalysis)  # 返回结构化结果分析。

    def draft_manuscript(self, payload: dict[str, Any]) -> ManuscriptDraft:  # 执行论文写作任务。
        return self._invoke_structured(task_name="draft_manuscript", payload=payload, response_model=ManuscriptDraft)  # 返回结构化论文草稿。


class AdvisorAgent(BaseAgent):  # 定义导师角色 Agent。
    def __init__(self, settings: AppSettings, tools: list) -> None:  # 初始化导师角色 Agent。
        super().__init__(settings=settings, role_name="advisor", system_prompt=ADVISOR_SYSTEM_PROMPT, tools=tools)  # 调用父类初始化逻辑。

    def review_innovations(self, payload: dict[str, Any]) -> InnovationReview:  # 执行创新点审核任务。
        return self._invoke_structured(task_name="review_innovations", payload=payload, response_model=InnovationReview)  # 返回结构化创新点审核结果。

    def review_manuscript(self, payload: dict[str, Any]) -> PaperReview:  # 执行论文二审任务。
        return self._invoke_structured(task_name="review_manuscript", payload=payload, response_model=PaperReview)  # 返回结构化论文二审结果。


class ReviewerAgent(BaseAgent):  # 定义审稿人角色 Agent。
    def __init__(self, settings: AppSettings, tools: list) -> None:  # 初始化审稿人角色 Agent。
        super().__init__(settings=settings, role_name="reviewer", system_prompt=REVIEWER_SYSTEM_PROMPT, tools=tools)  # 调用父类初始化逻辑。

    def blind_review(self, payload: dict[str, Any]) -> BlindReview:  # 执行第三方盲审任务。
        return self._invoke_structured(task_name="blind_review", payload=payload, response_model=BlindReview)  # 返回结构化盲审结果。


__all__ = ["BaseAgent", "StudentAgent", "AdvisorAgent", "ReviewerAgent"]  # 暴露四个核心 Agent 类型，供工作流层统一导入。
