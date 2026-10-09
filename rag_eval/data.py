"""本地数据加载：题集 / 语料 / 企业版本，均存 YAML。"""
from __future__ import annotations

from pathlib import Path

import yaml

from .models import CorpusDoc, DatasetItem, EnterpriseVersion


def _read_yaml(path: str | Path) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}


def load_enterprises(path: str | Path) -> list[EnterpriseVersion]:
    rows = _read_yaml(path).get("enterprises", [])
    return [EnterpriseVersion(enterprise_id=r["enterprise_id"], version=r["version"],
                              valid_from=r.get("valid_from", r["version"]),
                              valid_to=r.get("valid_to", r["version"])) for r in rows]


def load_corpus(path: str | Path) -> list[CorpusDoc]:
    rows = _read_yaml(path).get("documents", [])
    return [CorpusDoc(doc_id=r["doc_id"], enterprise_id=r["enterprise_id"], version=r["version"],
                      content=r["content"], keywords=list(r.get("keywords", []))) for r in rows]


def load_dataset(path: str | Path) -> list[DatasetItem]:
    rows = _read_yaml(path).get("items", [])
    return [DatasetItem(id=r["id"], question=r["question"], scenario=r.get("scenario", "normal"),
                        enterprise_id=r.get("enterprise_id", ""), version=r.get("version", ""),
                        expected_points=list(r.get("expected_points", [])),
                        forbidden_claims=list(r.get("forbidden_claims", []))) for r in rows]


def load_annotations(path: str | Path) -> dict[str, str]:
    """人工标注：question_id -> 标注文本（与自动结果分开）。"""
    return _read_yaml(path).get("annotations", {}) if Path(path).exists() else {}
