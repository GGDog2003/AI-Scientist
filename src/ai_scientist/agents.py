from __future__ import annotations  # 启用延后类型注解，便于类方法中引用模型类型。

import json  # 导入 json，用于把任务负载格式化成提示词文本。
from typing import Any  # 导入 Any，用于描述通用任务负载。
from typing import TypeVar  # 导入 TypeVar，用于声明结构化输出的泛型。

from langchain.agents import create_agent  # 导入 LangChain create_agent，用于构建图驱动的 Agent。
from langchain.chat_models import init_chat_model  # 导入通用模型初始化入口，兼容多家模型提供商。
from pydantic import BaseModel  # 导入 Pydantic 基类，用于约束结构化输出。

from ai_scientist.config import AppSettings  # 导入项目配置，便于决定模型来源和 stub 模式。
from ai_scientist.prompts import ADVISOR_SYSTEM_PROMPT  # 导入导师系统提示词。
from ai_scientist.prompts import REVIEWER_SYSTEM_PROMPT  # 导入审稿人系统提示词。
from ai_scientist.prompts import STUDENT_SYSTEM_PROMPT  # 导入研究生系统提示词。
from ai_scientist.schemas import BlindReview  # 导入盲审输出模型。
from ai_scientist.schemas import ExperimentPlan  # 导入实验方案输出模型。
from ai_scientist.schemas import InnovationCard  # 导入创新点卡片模型。
from ai_scientist.schemas import InnovationProposal  # 导入创新点提案输出模型。
from ai_scientist.schemas import InnovationReview  # 导入创新点审核输出模型。
from ai_scientist.schemas import LiteratureNote  # 导入单篇论文笔记模型。
from ai_scientist.schemas import LiteratureSynthesis  # 导入文献调研输出模型。
from ai_scientist.schemas import ManuscriptDraft  # 导入论文草稿输出模型。
from ai_scientist.schemas import PaperReview  # 导入导师论文审核输出模型。
from ai_scientist.schemas import ResultAnalysis  # 导入实验结果分析输出模型。
from ai_scientist.schemas import ReviewDecision  # 导入审核决策枚举，便于 stub 决策。

StructuredModel = TypeVar("StructuredModel", bound=BaseModel)  # 声明结构化输出泛型，约束为 Pydantic 模型。


class BaseRoleAgent:  # 定义所有角色 Agent 的基础能力封装。
    def __init__(self, settings: AppSettings, role_name: str, system_prompt: str, tools: list) -> None:  # 初始化角色 Agent。
        self.settings = settings  # 保存全局配置，便于后续判定模型与 stub 模式。
        self.role_name = role_name  # 保存角色名，便于日志和提示词识别。
        self.system_prompt = system_prompt  # 保存系统提示词，便于约束当前角色行为。
        self.tools = tools  # 保存工具列表，便于让 Agent 在局部任务内执行 ReAct。
        self.model = None if settings.use_stub_agent else self._build_model()  # 如果不是 stub 模式，就提前初始化真实模型。

    def _build_model(self):  # 构建 LangChain 聊天模型对象。
        if self.settings.model_provider:  # 判断是否显式指定了模型提供商。
            return init_chat_model(  # 按 provider + model 的形式构建模型。
                self.settings.model_name,  # 传入模型名。
                model_provider=self.settings.model_provider,  # 传入模型提供商。
                temperature=self.settings.temperature,  # 传入温度参数。
            )  # 返回初始化好的聊天模型。
        return init_chat_model(  # 在未显式指定提供商时，走 LangChain 默认推断。
            self.settings.model_name,  # 传入模型名。
            temperature=self.settings.temperature,  # 传入温度参数。
        )  # 返回初始化好的聊天模型。

    def _invoke_structured(self, task_name: str, payload: dict[str, Any], response_model: type[StructuredModel]) -> StructuredModel:  # 用统一方式执行结构化任务。
        if self.settings.use_stub_agent:  # 判断当前是否处于本地桩代理模式。
            return self._stub_response(task_name=task_name, payload=payload, response_model=response_model)  # 使用本地规则生成结构化结果。
        agent = create_agent(  # 构建 LangChain Agent，使其可在内部循环使用工具。
            model=self.model,  # 传入真实聊天模型。
            tools=self.tools,  # 传入工具列表，允许模型在局部任务内执行 ReAct。
            system_prompt=self.system_prompt,  # 传入当前角色系统提示词。
            response_format=response_model,  # 传入目标结构化输出模型。
        )  # 完成 Agent 构建。
        user_message = {  # 组装用户消息体，传给当前角色 Agent。
            "role": "user",  # 指定消息角色为用户输入。
            "content": json.dumps({"task_name": task_name, "payload": payload}, ensure_ascii=False, indent=2),  # 使用 JSON 表达任务名称和上下文负载。
        }  # 结束消息对象构建。
        result = agent.invoke({"messages": [user_message]})  # 执行 Agent，并让其返回结构化结果。
        structured = result["structured_response"]  # 从最终状态中取出结构化响应。
        return structured if isinstance(structured, response_model) else response_model.model_validate(structured)  # 确保返回值最终被校验成指定模型类型。

    def _stub_response(self, task_name: str, payload: dict[str, Any], response_model: type[StructuredModel]) -> StructuredModel:  # 在离线模式下生成一个可运行的本地结构化结果。
        if response_model is LiteratureSynthesis:  # 判断当前任务是否需要产出文献综述。
            paper_paths = payload.get("paper_paths") or ["未提供论文路径"]  # 从负载中拿到论文路径列表，如无则放一个占位值。
            notes = [  # 根据传入论文路径构造简单的论文笔记列表。
                LiteratureNote(  # 创建单篇论文笔记对象。
                    title=f"示例论文 {index}",  # 使用顺序号生成示例标题。
                    venue="DemoConf",  # 使用示例会议名称。
                    year=2025,  # 使用示例年份。
                    summary=f"这是对论文 {paper_path} 的离线调试摘要。",  # 生成离线模式摘要。
                    innovation_points=[f"创新点 {index}A", f"创新点 {index}B"],  # 生成两个示例创新点。
                    limitations=[f"不足点 {index}A", f"不足点 {index}B"],  # 生成两个示例不足点。
                    base_paper=f"基座论文 {index}" if index % 2 == 0 else None,  # 偶数序号时生成一个基座论文名称。
                    improvements_over_base=["提升了特征融合", "优化了训练稳定性"] if index % 2 == 0 else [],  # 偶数序号时生成改进点。
                )  # 结束单篇论文笔记对象创建。
                for index, paper_path in enumerate(paper_paths[:10], start=1)  # 最多取前十篇论文，用于模拟阅读结果。
            ]  # 结束笔记列表推导。
            return response_model.model_validate(  # 返回结构化文献综述结果。
                {  # 构造符合 LiteratureSynthesis 的字典。
                    "notes": [note.model_dump() for note in notes],  # 写入全部论文笔记。
                    "trend_summary": "近期研究趋势集中在轻量模块增强、多尺度建模和训练策略优化。",  # 写入趋势总结。
                    "possible_gaps": ["现有方法对弱边界目标提升有限", "对计算成本与效果的平衡研究不足"],  # 写入潜在空白点。
                }  # 结束文献综述负载构建。
            )  # 完成 Pydantic 校验并返回。
        if response_model is InnovationProposal:  # 判断当前任务是否需要产出创新点提案。
            cards = [  # 构造三个示例创新点卡片。
                InnovationCard(  # 创建第一个创新点。
                    name="自适应边界增强模块",  # 保存创新点名称。
                    motivation="针对弱边界目标分割不稳定的问题提出模块增强。",  # 保存创新动机。
                    novelty_type="module_improvement",  # 保存创新类型。
                    expected_gain="提升边界区域的 mIoU 与 F1。",  # 保存预期收益。
                    risk_points=["模块增益可能不稳定", "参数量可能上升"],  # 保存风险点。
                    evidence=["多篇论文都指出边界区域是性能瓶颈"],  # 保存支撑证据。
                ),  # 结束第一个创新点创建。
                InnovationCard(  # 创建第二个创新点。
                    name="多尺度语义一致性损失",  # 保存创新点名称。
                    motivation="缓解不同尺度特征学习目标不一致的问题。",  # 保存创新动机。
                    novelty_type="loss_function",  # 保存创新类型。
                    expected_gain="提升模型泛化能力和跨数据集稳定性。",  # 保存预期收益。
                    risk_points=["损失设计可能过于复杂", "训练收敛速度可能下降"],  # 保存风险点。
                    evidence=["现有工作对损失层面的探索较少"],  # 保存支撑证据。
                ),  # 结束第二个创新点创建。
                InnovationCard(  # 创建第三个创新点。
                    name="教师反馈引导的伪标签筛选",  # 保存创新点名称。
                    motivation="在半监督设置下过滤低质量伪标签。",  # 保存创新动机。
                    novelty_type="training_strategy",  # 保存创新类型。
                    expected_gain="提升半监督实验中的标签利用效率。",  # 保存预期收益。
                    risk_points=["额外训练阶段带来时间开销"],  # 保存风险点。
                    evidence=["近年半监督论文强调伪标签质量控制"],  # 保存支撑证据。
                ),  # 结束第三个创新点创建。
            ]  # 结束创新点列表构造。
            return response_model.model_validate(  # 返回结构化创新点提案结果。
                {  # 构造提案字典。
                    "cards": [card.model_dump() for card in cards],  # 写入全部创新点卡片。
                    "selected_focus": cards[0].name,  # 默认选择第一个创新点作为主推方向。
                    "meeting_brief": "建议优先验证边界增强方向，因为证据更充分且实现成本较低。",  # 生成简短组会汇报摘要。
                }  # 结束提案字典构建。
            )  # 完成校验并返回。
        if response_model is InnovationReview:  # 判断当前任务是否需要导师创新点审核。
            round_number = int(payload.get("review_round", 0))  # 读取当前审核轮次，便于模拟打回和通过。
            proposal = payload.get("proposal", {})  # 读取创新点提案内容，便于选择通过项。
            first_card_name = proposal.get("cards", [{}])[0].get("name") if proposal.get("cards") else None  # 尝试读取第一个创新点名称。
            decision = ReviewDecision.revise if round_number == 0 else ReviewDecision.approved  # 第一轮先打回，第二轮开始通过。
            return response_model.model_validate(  # 返回结构化创新点审核结果。
                {  # 构造审核输出字典。
                    "decision": decision,  # 写入审核结论。
                    "comments": ["需要补充与最新相关工作的差异性说明。"] if decision == ReviewDecision.revise else ["创新点已经具备实验验证价值，可以进入实验阶段。"],  # 根据结论生成意见。
                    "approved_card_name": None if decision == ReviewDecision.revise else first_card_name,  # 通过时写入批准的创新点名称。
                }  # 结束审核字典构造。
            )  # 完成校验并返回。
        if response_model is ExperimentPlan:  # 判断当前任务是否需要实验设计方案。
            innovation_name = payload.get("approved_innovation", {}).get("name", "示例创新点")  # 读取被批准的创新点名称。
            return response_model.model_validate(  # 返回结构化实验方案。
                {  # 构造实验方案字典。
                    "objective": f"验证 {innovation_name} 是否能够稳定提升目标任务性能。",  # 写入实验目标。
                    "datasets": ["Dataset-A", "Dataset-B"],  # 写入示例数据集。
                    "baselines": ["Baseline-1", "Baseline-2"],  # 写入示例 baseline。
                    "metrics": ["mIoU", "F1", "Accuracy"],  # 写入评价指标。
                    "ablations": ["去掉新增模块", "替换损失函数", "改变训练策略"],  # 写入消融实验。
                    "python_modules": ["train.py", "eval.py", "models/custom_module.py", "configs/default.yaml"],  # 写入建议代码模块。
                    "execution_steps": ["准备数据集", "安装依赖", "执行训练", "执行评估", "整理日志和结果表"],  # 写入人工执行步骤。
                }  # 结束实验方案字典构造。
            )  # 完成校验并返回。
        if response_model is ResultAnalysis:  # 判断当前任务是否需要结果分析。
            metrics = payload.get("human_result", {}).get("metrics", {})  # 读取人工反馈的实验指标。
            return response_model.model_validate(  # 返回结构化结果分析。
                {  # 构造结果分析字典。
                    "summary": f"实验结果显示目标方法在核心指标上取得提升，原始指标为：{metrics}。",  # 写入总体总结。
                    "key_findings": ["主要增益集中在边界相关指标。", "新增模块带来的收益高于损失项微调。"],  # 写入关键发现。
                    "claims_boundary": ["可以表述为在当前实验设置下有效。", "不能宣称对所有任务都普适提升。"],  # 写入结论边界。
                    "paper_storyline": ["文献空白 -> 创新动机", "方法设计 -> 实验验证", "结果优势 -> 局限与未来工作"],  # 写入论文叙事主线。
                }  # 结束结果分析字典构造。
            )  # 完成校验并返回。
        if response_model is ManuscriptDraft:  # 判断当前任务是否需要论文草稿。
            focus = payload.get("approved_innovation", {}).get("name", "目标创新点")  # 读取当前论文聚焦的创新点名称。
            return response_model.model_validate(  # 返回结构化论文草稿。
                {  # 构造论文草稿字典。
                    "title": f"面向目标任务的 {focus} 方法研究",  # 生成论文标题。
                    "abstract": "本文围绕目标任务中的性能瓶颈，提出了一种可验证的改进方法，并通过真实实验进行评估。",  # 生成摘要正文。
                    "introduction": "引言部分说明问题背景、现有不足和本文创新点。",  # 生成引言章节。
                    "related_work": "相关工作部分对比模块改进、损失函数设计和训练策略三条主线。",  # 生成相关工作章节。
                    "method": "方法部分详细描述模块设计、数据流向和训练目标。",  # 生成方法章节。
                    "experiments": "实验部分报告数据集、对照组、指标、消融实验和误差分析。",  # 生成实验章节。
                    "conclusion": "结论部分总结当前方法有效性、局限性和未来改进方向。",  # 生成结论章节。
                    "references": ["[1] Example Reference A.", "[2] Example Reference B."],  # 生成示例参考文献。
                    "self_review_notes": ["已核对实验结果来自人工反馈。", "已避免使用超出证据范围的夸大表述。"],  # 写入研究生自审记录。
                }  # 结束论文草稿字典构造。
            )  # 完成校验并返回。
        if response_model is PaperReview:  # 判断当前任务是否需要导师论文二审。
            round_number = int(payload.get("review_round", 0))  # 读取当前论文二审轮次。
            decision = ReviewDecision.revise if round_number == 0 else ReviewDecision.approved  # 第一轮打回，第二轮通过。
            return response_model.model_validate(  # 返回结构化导师审核结果。
                {  # 构造导师审核字典。
                    "decision": decision,  # 写入导师审核结论。
                    "major_issues": ["方法描述还不够精确，需要补充关键设计动机。"] if decision == ReviewDecision.revise else [],  # 根据结论生成主要问题。
                    "minor_issues": ["引言中部分表述可以进一步压缩。"],  # 生成次要问题列表。
                    "required_changes": ["补充方法与实验现象之间的呼应分析。"] if decision == ReviewDecision.revise else ["保留终稿前最后一次通读。"],  # 生成必须修改事项。
                }  # 结束导师审核字典构造。
            )  # 完成校验并返回。
        if response_model is BlindReview:  # 判断当前任务是否需要审稿人盲审。
            round_number = int(payload.get("review_round", 0))  # 读取盲审轮次。
            decision = ReviewDecision.minor_revision if round_number == 0 else ReviewDecision.accept  # 第一轮小修，第二轮接受。
            return response_model.model_validate(  # 返回结构化盲审结果。
                {  # 构造盲审字典。
                    "decision": decision,  # 写入盲审结论。
                    "summary": "论文整体完整，实验可信，但部分分析仍可更凝练。",  # 写入总体评价。
                    "strengths": ["问题定义明确", "实验设计较完整", "创新点与结果形成呼应"],  # 写入优点列表。
                    "weaknesses": ["局限性讨论略短", "图表自解释性还有提升空间"],  # 写入缺点列表。
                    "required_changes": ["补充局限性分析段落", "优化表格说明文字"] if decision == ReviewDecision.minor_revision else ["整理最终排版。"],  # 写入必须修改事项。
                    "confidence": "medium",  # 写入置信度。
                }  # 结束盲审字典构造。
            )  # 完成校验并返回。
        raise ValueError(f"Unsupported response model: {response_model}")  # 如果传入了未知结构化模型，就显式抛出异常。


class StudentAgent(BaseRoleAgent):  # 定义研究生角色 Agent。
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


class AdvisorAgent(BaseRoleAgent):  # 定义导师角色 Agent。
    def __init__(self, settings: AppSettings, tools: list) -> None:  # 初始化导师角色 Agent。
        super().__init__(settings=settings, role_name="advisor", system_prompt=ADVISOR_SYSTEM_PROMPT, tools=tools)  # 调用父类初始化逻辑。

    def review_innovations(self, payload: dict[str, Any]) -> InnovationReview:  # 执行创新点审核任务。
        return self._invoke_structured(task_name="review_innovations", payload=payload, response_model=InnovationReview)  # 返回结构化创新点审核结果。

    def review_manuscript(self, payload: dict[str, Any]) -> PaperReview:  # 执行论文二审任务。
        return self._invoke_structured(task_name="review_manuscript", payload=payload, response_model=PaperReview)  # 返回结构化论文二审结果。


class ReviewerAgent(BaseRoleAgent):  # 定义审稿人角色 Agent。
    def __init__(self, settings: AppSettings, tools: list) -> None:  # 初始化审稿人角色 Agent。
        super().__init__(settings=settings, role_name="reviewer", system_prompt=REVIEWER_SYSTEM_PROMPT, tools=tools)  # 调用父类初始化逻辑。

    def blind_review(self, payload: dict[str, Any]) -> BlindReview:  # 执行第三方盲审任务。
        return self._invoke_structured(task_name="blind_review", payload=payload, response_model=BlindReview)  # 返回结构化盲审结果。
