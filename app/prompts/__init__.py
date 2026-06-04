from __future__ import annotations  # 启用延后类型注解，便于函数签名中引用 Path。

from pathlib import Path  # 导入 Path，用于读取当前 prompts 目录下的文本文件。


def _read_prompt(role: str) -> str:  # 读取指定角色的系统提示词文本。
    prompt_path = Path(__file__).resolve().parent / role / "system_prompt.txt"  # 计算角色提示词文件路径。
    return prompt_path.read_text(encoding="utf-8").strip()  # 使用 UTF-8 读取并返回去首尾空白的提示词。


STUDENT_SYSTEM_PROMPT = _read_prompt("student")  # 读取研究生角色系统提示词。
ADVISOR_SYSTEM_PROMPT = _read_prompt("advisor")  # 读取导师角色系统提示词。
REVIEWER_SYSTEM_PROMPT = _read_prompt("reviewer")  # 读取审稿人角色系统提示词。

__all__ = ["STUDENT_SYSTEM_PROMPT", "ADVISOR_SYSTEM_PROMPT", "REVIEWER_SYSTEM_PROMPT"]  # 暴露三个角色的系统提示词常量。
