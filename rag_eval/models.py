"""数据模型：题集、企业/版本、引用文档、评测结果。

纯 dataclass，便于 YAML/JSON 序列化，不引入重型 ORM。
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict


@dataclass
class EnterpriseVersion:
    enterprise_id: str
    version: str          # 当前生效版本
    valid_from: str       # 仍有效的最早版本（含）
    valid_to: str         # 仍有效的最晚版本（含）

    def in_window(self, version: str) -> bool:
        return self.valid_from <= version <= self.valid_to


@dataclass
class CorpusDoc:
    doc_id: str
    enterprise_id: str
    version: str
    content: str
    keywords: list[str] = field(default_factory=list)   # 检索索引（演示用合成语料）


@dataclass
class DatasetItem:
    id: str
    question: str
    scenario: str = "normal"        # normal / insufficient / outdated / cross_enterprise / conflict
    enterprise_id: str = ""
    version: str = ""               # 当前版本（提问时点）
    expected_points: list[str] = field(default_factory=list)
    forbidden_claims: list[str] = field(default_factory=list)


@dataclass
class Citation:
    doc_id: str
    enterprise_id: str = ""
    version: str = ""


@dataclass
class QAResponse:
    answer: str = ""
    citations: list[Citation] = field(default_factory=list)
    model_version: str = ""
    knowledge_version: str = ""
    latency_ms: int = 0
    endpoint_error: str = ""        # 非空表示接口失败（timeout / 5xx / 4xx / 连接拒绝 / 结构异常）


@dataclass
class Flag:
    code: str
    detail: str = ""


@dataclass
class ItemResult:
    question_id: str
    scenario: str = ""
    group: str = ""                 # 通过 / 未命中 / 错引用 / 过期资料 / 越权 / 模型补写 / 接口失败
    flags: list[Flag] = field(default_factory=list)
    question: str = ""
    redacted_question: str = ""
    redacted: bool = False
    answer: str = ""
    citations: list[Citation] = field(default_factory=list)
    latency_ms: int = 0
    model_version: str = ""
    knowledge_version: str = ""
    human_annotation: str = ""      # 人工标注，与自动结果分开显示
    semantic: dict | None = None    # 语义评分（辅助，不参与分组）

    @property
    def ok(self) -> bool:
        return self.group == "通过"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["flags"] = [{"code": f.code, "detail": f.detail} for f in self.flags]
        d["citations"] = [asdict(c) for c in self.citations]
        return d
