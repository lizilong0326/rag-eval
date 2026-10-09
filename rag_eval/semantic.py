"""语义评分（辅助，可选，默认关闭）。

- 结果只作辅助参考，不参与确定性规则分组；
- 启用后走 DeepSeek（或任意 Anthropic-compatible 网关）；
- 调用失败降级为 error 字段，不影响主流程。
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

_SYSTEM = ("你是企业知识问答的辅助评分员。只根据「期望要点」判断答案覆盖程度，"
           "输出 0–100 分与一句理由。你的评分不构成事实正确性结论，仅作人工复核参考。")


def _load_env() -> None:
    from dotenv import load_dotenv
    for p in (ROOT / ".env", ROOT.parent / ".env"):
        if p.exists():
            load_dotenv(p, override=False)


def _extract_json(text: str) -> dict:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if fence:
        text = fence.group(1)
    start = text.find("{")
    if start < 0:
        raise ValueError("输出里没有 JSON")
    return json.loads(text[start:text.rfind("}") + 1])


@dataclass
class SemanticScore:
    enabled: bool
    score: int = 0
    rationale: str = ""
    model: str = ""
    error: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class SemanticGrader:
    def __init__(self, model: str | None = None, client=None):
        _load_env()
        self.model = model or os.getenv("SEMANTIC_MODEL_ID") or os.getenv("MODEL_ID") or "deepseek-chat"
        self.client = client
        if self.client is None:
            from anthropic import Anthropic
            self.client = Anthropic(base_url=os.getenv("ANTHROPIC_BASE_URL"),
                                    timeout=60.0, max_retries=0)

    def grade(self, question: str, answer: str, expected_points: list[str]) -> SemanticScore:
        if not answer.strip():
            return SemanticScore(enabled=True, score=0, rationale="答案为空", model=self.model)
        points = "\n".join(f"- {p}" for p in expected_points) or "（无期望要点，仅评答案自洽性）"
        prompt = f"问题：{question}\n答案：{answer}\n期望要点：\n{points}\n\n只输出 JSON：{{\"score\": 0-100 整数, \"rationale\": \"一句理由\"}}"
        try:
            resp = self.client.messages.create(
                model=self.model, max_tokens=300, system=_SYSTEM,
                messages=[{"role": "user", "content": prompt}],
            )
            text = "".join(getattr(b, "text", "") for b in resp.content
                           if getattr(b, "type", None) == "text")
            data = _extract_json(text)
            score = max(0, min(100, int(data.get("score", 0))))
            return SemanticScore(enabled=True, score=score,
                                 rationale=str(data.get("rationale", "")), model=self.model)
        except Exception as exc:  # noqa: BLE001 —— 语义评分失败不阻断主流程
            return SemanticScore(enabled=True, error=f"{type(exc).__name__}: {exc}", model=self.model)
