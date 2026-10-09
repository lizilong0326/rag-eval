"""promptfoo 断言导出：把题集转成 promptfoo 测试配置（零依赖，只写 YAML）。

映射：
- expected_points  → assert type=contains
- forbidden_claims → assert type=not-contains
- scenario         → vars.scenario（供断言模板按场景扩展）
"""
from __future__ import annotations

from pathlib import Path

import yaml

from .models import DatasetItem


def build_promptfoo_config(dataset: list[DatasetItem], provider_url: str,
                           provider_name: str = "qa-http") -> dict:
    tests = []
    for item in dataset:
        asserts = [{"type": "contains", "value": p} for p in item.expected_points]
        asserts += [{"type": "not-contains", "value": c} for c in item.forbidden_claims]
        tests.append({
            "description": f"{item.id} [{item.scenario}] {item.question[:30]}",
            "vars": {"question": item.question, "enterprise_id": item.enterprise_id,
                     "version": item.version, "scenario": item.scenario},
            "assert": asserts or [{"type": "contains", "value": "__PLACEHOLDER_NO_ASSERT__"}],
        })
    return {
        "description": "RAG 回归评测（由 rag-eval 导出）",
        "prompts": ["prompt_qa.py"],   # 由 promptfoo 的脚本 provider 组织请求体
        "providers": [{
            "id": "http",
            "config": {
                "url": provider_url,
                "method": "POST",
                "headers": {"Authorization": "Bearer {{QA_ENDPOINT_TOKEN}}"},
                "body": {"question": "{{question}}", "enterprise_id": "{{enterprise_id}}",
                         "version": "{{version}}"},
            },
        }],
        "defaultTest": {"assert": [{"type": "contains", "value": "__PLACEHOLDER__"}]},
        "tests": tests,
    }


def export_promptfoo(dataset: list[DatasetItem], out_path: Path, provider_url: str) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cfg = build_promptfoo_config(dataset, provider_url)
    out_path.write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return out_path
