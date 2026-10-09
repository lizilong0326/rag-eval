"""失败项复现包：原题、原答、引用证据、请求参数、版本信息落盘。"""
from __future__ import annotations

import json
from pathlib import Path

from .models import ItemResult


def export_repro(results: list[ItemResult], out_dir: Path, label: str) -> Path:
    failed = [r for r in results if not r.ok]
    bundle = Path(out_dir) / "repro" / label
    bundle.mkdir(parents=True, exist_ok=True)
    for r in failed:
        (bundle / f"{r.question_id}.json").write_text(
            json.dumps(r.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return bundle
