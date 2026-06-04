# AI Scientist LangGraph Project

这是一个按 [实现方式/20260604_110941_hello-agents科研agent实现细节.md](/D:/python/AI-Scientist/实现方式/20260604_110941_hello-agents科研agent实现细节.md) 落地的 `LangChain + LangGraph` 科研多 Agent 项目。

## 核心设计

- 全局编排：`Plan-and-Solve`
- 单个角色内部：`ReAct`
- 角色协作：提交后挂起，等待对方返回结果后再恢复
- 人类介入：实验结果通过 `LangGraph interrupt` 恢复
- 持久化：默认使用 SQLite Checkpointer

## 角色

- `StudentAgent`
- `AdvisorAgent`
- `ReviewerAgent`

## 目录

```text
app/
  agents/
  workflows/
  tools/
  memory/
  schemas/
  prompts/
  main.py
main.py
workspace/
  papers/
  parsed_papers/
  literature_reports/
  innovation_meetings/
  experiment_plans/
  experiment_results/
  manuscripts/
  reviews/
  logs/
```

当前正式代码入口有两层：

- 根目录脚本入口：`python main.py ...`
- 模块入口：[app/main.py](/D:/python/AI-Scientist/app/main.py)

## 安装

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .[dev]
```

## 环境变量

如果你要使用真实模型，至少配置以下变量之一：

```powershell
$env:OPENAI_API_KEY="sk-..."
```

可选变量：

```powershell
$env:AI_SCIENTIST_MODEL="openai:gpt-4.1-mini"
$env:AI_SCIENTIST_TEMPERATURE="0"
$env:AI_SCIENTIST_CHECKPOINT_DB="D:\python\AI-Scientist\workspace\checkpoints.sqlite"
$env:AI_SCIENTIST_USE_STUB="false"
```

如果未配置模型密钥，系统会自动回退到本地 `stub` 模式，便于先跑通状态机。

## 快速开始

默认建议直接在仓库根目录执行：

```powershell
python main.py start --topic "图像分割" --domain "人工智能" --paper-dir ".\workspace\papers"
```

`--paper-dir` 传入的是论文目录路径，程序会按文件名顺序自动遍历该目录下全部 `.pdf` 文件并逐篇读取。

如果你已经把项目安装成命令行工具，也可以使用等价写法：

```powershell
ai-scientist start --topic "图像分割" --domain "人工智能" --paper-dir ".\workspace\papers"
```

当工作流运行到人工实验节点时，会触发中断并输出等待信息。此时你手动运行实验后，可以通过下面的方式恢复：

```powershell
python main.py resume --thread-id "<thread-id>" --resume-json "{""summary"": ""mIoU 提升 1.4%"", ""metrics"": {""miou"": 82.1, ""f1"": 88.3}}"
```

查看当前线程状态：

```powershell
python main.py state --thread-id "<thread-id>"
```

## 工作流说明

1. 研究生读取论文目录中的 PDF，并生成文献调研报告。
2. 研究生提出创新点并提交导师审核。
3. 导师若打回，研究生继续修改；若通过，则进入实验设计。
4. 人类执行实验，并通过 `resume` 回填实验结果。
5. 研究生撰写论文，导师二审，审稿人三审。
6. 按审核结论进入返修或终稿阶段。

## 验证

你可以先做基础语法验证：

```powershell
python -m compileall main.py app tests
```
