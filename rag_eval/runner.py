"""主流程：导入题集 → 调用被测接口 → 规则检查 → 报告 → 复现包。"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from .adapter import Adapter
from .models import CorpusDoc, DatasetItem, EnterpriseVersion, ItemResult
from .redact import redact
from .report import build_report, render_html
from .repro import export_repro
from .rules import check_item

logger = logging.getLogger("rag_eval.runner")


def evaluate(items: list[DatasetItem], adapter: Adapter,
             corpus_by_id: dict[str, CorpusDoc],
             ent_by_id: dict[str, EnterpriseVersion],
             annotations: dict[str, str] | None = None,
             grader=None) -> list[ItemResult]:
    annotations = annotations or {}
    results: list[ItemResult] = []
    for item in items:
        redacted_q, changed = redact(item.question)
        resp = adapter.ask(item, redacted_q)
        result = check_item(item, resp, corpus_by_id, ent_by_id)
        result.redacted_question = redacted_q if changed else ""
        result.redacted = changed
        result.human_annotation = annotations.get(item.id, "")
        if grader is not None:
            sem = grader.grade(item.question, resp.answer, item.expected_points)
            result.semantic = sem.to_dict() if hasattr(sem, "to_dict") else sem
        results.append(result)
    return results


def run(dataset: list[DatasetItem], corpus: list[CorpusDoc], enterprises: list[EnterpriseVersion],
        baseline: Adapter, candidate: Adapter | None, out_dir: Path,
        labels: dict, dataset_meta: dict, annotations: dict[str, str] | None = None,
        grader=None) -> dict:
    corpus_by_id = {d.doc_id: d for d in corpus}
    ent_by_id = {e.enterprise_id: e for e in enterprises}

    logger.info("运行基线版：%s", labels.get("baseline", "baseline"))
    baseline_results = evaluate(dataset, baseline, corpus_by_id, ent_by_id, annotations, grader)
    candidate_results = evaluate(dataset, candidate, corpus_by_id, ent_by_id, annotations, grader) if candidate else None

    report = build_report(dataset_meta, baseline_results, candidate_results, labels)

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "report.html").write_text(render_html(report), encoding="utf-8")
    export_repro(baseline_results, out_dir, labels.get("baseline", "baseline"))
    if candidate_results is not None:
        export_repro(candidate_results, out_dir, labels.get("candidate", "candidate"))
    return report
