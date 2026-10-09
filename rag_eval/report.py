"""报告生成：机器可读 JSON + 可阅读 HTML 页面（macOS 风格）。

- 按错误类型分组，展示原题/原答/引用证据；
- 基线版与候选版回归差异（进步 / 退化 / 持平）；
- 人工标注与自动结果分开显示，不回填进自动判定。
"""
from __future__ import annotations

import html
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from .models import Citation, Flag, ItemResult
from .rules import ERROR_GROUPS, GROUP_PASS

_ORDER = [GROUP_PASS] + ERROR_GROUPS

# macOS 系统色板（浅色/深色均可用）
GROUP_ACCENT = {
    "通过": "#34C759",    # 系统绿
    "未命中": "#FF9500",   # 系统橙
    "错引用": "#FF6B00",   # 深橙
    "过期资料": "#AF52DE",  # 系统紫
    "越权": "#FF3B30",     # 系统红
    "模型补写": "#007AFF",  # 系统蓝
    "接口失败": "#8E8E93",  # 系统灰
}


def _summarize(results: list[ItemResult]) -> dict:
    by_group: dict[str, list[str]] = defaultdict(list)
    for r in results:
        by_group[r.group].append(r.question_id)
    return {
        "total": len(results),
        "pass": sum(1 for r in results if r.ok),
        "fail": sum(1 for r in results if not r.ok),
        "by_group": {g: sorted(by_group.get(g, [])) for g in _ORDER},
    }


def _diff(baseline: list[ItemResult], candidate: list[ItemResult]) -> dict:
    b = {r.question_id: r for r in baseline}
    c = {r.question_id: r for r in candidate}
    regressed = sorted(q for q in b if q in c and b[q].ok and not c[q].ok)
    improved = sorted(q for q in b if q in c and not b[q].ok and c[q].ok)
    both_fail = sorted(q for q in b if q in c and not b[q].ok and not c[q].ok)
    both_pass = sorted(q for q in b if q in c and b[q].ok and c[q].ok)
    return {
        "regressed": regressed,
        "improved": improved,
        "unchanged_fail": both_fail,
        "unchanged_pass": both_pass,
        "only_baseline": sorted(set(b) - set(c)),
        "only_candidate": sorted(set(c) - set(b)),
    }


def build_report(dataset_meta: dict, baseline: list[ItemResult],
                 candidate: list[ItemResult] | None, labels: dict) -> dict:
    report = {
        "meta": {
            **dataset_meta,
            "baseline_label": labels.get("baseline", "baseline"),
            "candidate_label": labels.get("candidate", "candidate"),
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "note": "自动结果为确定性规则检查；语义评分为辅助参考；人工标注单独存放，不与自动结果合并。",
        },
        "summary": {"baseline": _summarize(baseline)},
        "baseline": [r.to_dict() for r in baseline],
    }
    if candidate is not None:
        report["summary"]["candidate"] = _summarize(candidate)
        report["summary"]["regression"] = _diff(baseline, candidate)
        report["candidate"] = [r.to_dict() for r in candidate]
    return report


# ---------------------------------------------------------------------------
# HTML 渲染（macOS 风格）
# ---------------------------------------------------------------------------

def _esc(s: object) -> str:
    return html.escape(str(s))


def _rebuild(results: list[dict]) -> list[ItemResult]:
    out = []
    for r in results:
        item = ItemResult(
            question_id=r["question_id"], scenario=r.get("scenario", ""),
            group=r.get("group", ""), question=r.get("question", ""),
            redacted_question=r.get("redacted_question", ""), redacted=r.get("redacted", False),
            answer=r.get("answer", ""), latency_ms=r.get("latency_ms", 0),
            model_version=r.get("model_version", ""), knowledge_version=r.get("knowledge_version", ""),
            human_annotation=r.get("human_annotation", ""),
        )
        item.flags = [Flag(code=f["code"], detail=f.get("detail", "")) for f in r.get("flags", [])]
        item.citations = [Citation(**c) for c in r.get("citations", [])]
        item.semantic = r.get("semantic")
        out.append(item)
    return out


def _citations_html(citations: list[Citation]) -> str:
    if not citations:
        return '<span class="muted">（无引用）</span>'
    rows = "".join(
        f'<li><code>{_esc(c.doc_id)}</code><span class="muted"> 企业 {_esc(c.enterprise_id or "-")}'
        f" · 版本 {_esc(c.version or '-')}</span></li>"
        for c in citations
    )
    return f'<ul class="cites">{rows}</ul>'


def _item_card(r: ItemResult, baseline_group: str | None = None) -> str:
    accent = GROUP_ACCENT.get(r.group, "#8E8E93")
    diff_badge = ""
    if baseline_group is not None:
        if baseline_group == GROUP_PASS and not r.ok:
            diff_badge = '<span class="badge regress">退化</span>'
        elif baseline_group != GROUP_PASS and r.ok:
            diff_badge = '<span class="badge improve">进步</span>'
    flags = "".join(
        f'<li><code>{_esc(f.code)}</code><span class="muted"> {_esc(f.detail)}</span></li>'
        for f in r.flags
    )
    human = ("<span class='human'>人工标注：<b>" + _esc(r.human_annotation) + "</b></span>"
             if r.human_annotation else '<span class="muted">人工标注：（待标注）</span>')
    semantic = ""
    if r.semantic:
        s = r.semantic
        if s.get("error"):
            semantic = (f'<div class="kv semantic"><label>语义评分（辅助）</label>'
                        f'<div class="val err">{_esc(s["error"])}</div></div>')
        else:
            semantic = (f'<div class="kv semantic"><label>语义评分（辅助）</label>'
                        f'<div class="val">{s.get("score", 0)} 分 · {_esc(s.get("rationale", ""))}'
                        f' <span class="muted">（{_esc(s.get("model", ""))}，不参与分组）</span></div></div>')

    redacted = (f'<div class="kv"><label>脱敏后</label><div class="val">{_esc(r.redacted_question)}</div></div>'
                if r.redacted else "")

    return f"""
    <div class="card" style="--accent:{accent}">
      <div class="card-head">
        <div class="head-left">
          <span class="qid">#{_esc(r.question_id)}</span>
          <span class="pill" style="background:var(--accent)">{_esc(r.group)}</span>
          {diff_badge}
        </div>
        <span class="scenario">{_esc(r.scenario)}</span>
      </div>
      <div class="kv"><label>原题</label><div class="val">{_esc(r.question)}</div></div>
      {redacted}
      <div class="kv"><label>原答</label><div class="val">{_esc(r.answer) or '<span class="muted">（空）</span>'}</div></div>
      <div class="kv"><label>引用证据</label><div class="val">{_citations_html(r.citations)}</div></div>
      <div class="kv"><label>规则命中</label><div class="val"><ul class="flags">{flags or "<li class='muted'>（无）</li>"}</ul></div></div>
      <div class="kv meta"><label>耗时</label><div class="val">{r.latency_ms} ms</div></div>
      <div class="kv meta"><label>模型版本</label><div class="val">{_esc(r.model_version) or '<span class="muted">-</span>'}</div></div>
      <div class="kv meta"><label>知识版本</label><div class="val">{_esc(r.knowledge_version) or '<span class="muted">-</span>'}</div></div>
      {semantic}
      <div class="kv"><label>人工标注</label><div class="val">{human}</div></div>
    </div>"""


def _group_section(group: str, results: list[ItemResult], baseline_map: dict) -> str:
    accent = GROUP_ACCENT.get(group, "#8E8E93")
    cards = "".join(_item_card(r, baseline_map.get(r.question_id)) for r in results)
    return (f'<section id="g-{_esc(group)}" class="group-sec">'
            f'<h2><span class="dot" style="background:{accent}"></span>{_esc(group)}'
            f'<span class="count">{len(results)}</span></h2>{cards}</section>')


def render_html(report: dict) -> str:
    baseline_map = {r["question_id"]: r["group"] for r in report["baseline"]}
    b_by: dict[str, list[ItemResult]] = defaultdict(list)
    for r in _rebuild(report["baseline"]):
        b_by[r.group].append(r)

    c_by: dict[str, list[ItemResult]] = {}
    if report.get("candidate") is not None:
        for r in _rebuild(report["candidate"]):
            c_by.setdefault(r.group, []).append(r)

    bs = report["summary"]["baseline"]
    cs = report["summary"].get("candidate")
    reg = report["summary"].get("regression", {})
    meta = report["meta"]

    # 概览卡片
    kpis = [
        ("基线通过", bs["pass"], "green"),
        ("基线失败", bs["fail"], "red"),
    ]
    if cs is not None:
        kpis += [("候选通过", cs["pass"], "green"),
                 ("候选失败", cs["fail"], "red"),
                 ("退化", len(reg.get("regressed", [])), "red"),
                 ("进步", len(reg.get("improved", [])), "green")]
    kpi_html = "".join(
        f'<div class="kpi"><div class="num {tone}">{n}</div><div class="lbl">{label}</div></div>'
        for label, n, tone in kpis
    )

    # 错误分布条形图（取候选，无候选则基线）
    bar_src = cs["by_group"] if cs else bs["by_group"]
    total = max(1, sum(len(v) for v in bar_src.values()))
    bars = "".join(
        f'<div class="bar-row"><span class="bar-lbl">{_esc(g)}</span>'
        f'<div class="bar"><div class="bar-fill" style="width:{100 * len(v) // total}%;'
        f'background:{GROUP_ACCENT.get(g, "#8E8E93")}">{len(v)}</div></div></div>'
        for g, v in bar_src.items() if v
    )

    # 侧栏分组导航
    nav_src = c_by if c_by else b_by
    nav = "".join(
        f'<a class="nav-item" href="#g-{_esc(g)}"><span class="dot" '
        f'style="background:{GROUP_ACCENT.get(g, "#8E8E93")}"></span>{_esc(g)}'
        f'<span class="nav-count">{len(items)}</span></a>'
        for g, items in nav_src.items() if items
    )

    reg_rows = "".join(
        f"<tr><td>{_esc(k)}</td><td class='num-cell'>{len(reg.get(k, []))}</td>"
        f"<td class='muted'>{', '.join(_esc(x) for x in reg.get(k, [])) or '—'}</td></tr>"
        for k in ("regressed", "improved", "unchanged_fail", "unchanged_pass")
    )

    b_sections = "".join(_group_section(g, b_by.get(g, []), baseline_map) for g in _ORDER)
    c_sections = "".join(_group_section(g, c_by.get(g, []), baseline_map) for g in _ORDER)

    return f"""<!doctype html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>RAG 回归评测报告</title>
<style>
  :root {{
    --bg: #f5f5f7; --card: #ffffff; --sidebar: rgba(248,248,250,0.82);
    --text: #1d1d1f; --text-2: #6e6e73; --separator: rgba(0,0,0,0.10);
    --blue: #007aff; --green: #34c759; --red: #ff3b30; --orange: #ff9500;
    --purple: #af52de; --gray: #8e8e93; --indigo: #5856d6;
    --shadow: 0 1px 2px rgba(0,0,0,0.04), 0 8px 24px rgba(0,0,0,0.06);
    --radius: 14px;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --bg: #1e1e20; --card: #2c2c2e; --sidebar: rgba(40,40,42,0.85);
      --text: #f5f5f7; --text-2: #a1a1a6; --separator: rgba(255,255,255,0.10);
      --shadow: 0 1px 2px rgba(0,0,0,0.4), 0 8px 24px rgba(0,0,0,0.4);
    }}
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Helvetica Neue", "PingFang SC", sans-serif;
         background: var(--bg); color: var(--text); -webkit-font-smoothing: antialiased; line-height: 1.5; }}

  .titlebar {{ position: sticky; top: 0; z-index: 10; display: flex; align-items: center;
               padding: 13px 24px; border-bottom: 1px solid var(--separator);
               background: var(--sidebar); backdrop-filter: saturate(180%) blur(20px);
               -webkit-backdrop-filter: saturate(180%) blur(20px); }}
  .title {{ font-weight: 600; font-size: 14px; color: var(--text-2); }}
  .title b {{ color: var(--text); font-weight: 600; }}

  .layout {{ display: grid; grid-template-columns: 240px 1fr; }}
  @media (max-width: 820px) {{ .layout {{ grid-template-columns: 1fr; }} .sidebar {{ display: none; }} }}

  .sidebar {{ padding: 20px 16px; border-right: 1px solid var(--separator);
              background: var(--sidebar); backdrop-filter: saturate(180%) blur(20px);
              -webkit-backdrop-filter: saturate(180%) blur(20px); position: sticky; top: 51px;
              height: calc(100vh - 51px); overflow-y: auto; }}
  .sidebar h3 {{ font-size: 11px; text-transform: uppercase; letter-spacing: 0.06em;
                 color: var(--text-2); margin: 16px 0 8px; }}
  .nav-item {{ display: flex; align-items: center; gap: 8px; padding: 7px 10px; border-radius: 8px;
               color: var(--text); text-decoration: none; font-size: 13px; }}
  .nav-item:hover {{ background: rgba(0,0,0,0.05); }}
  @media (prefers-color-scheme: dark) {{ .nav-item:hover {{ background: rgba(255,255,255,0.08); }} }}
  .dot {{ width: 8px; height: 8px; border-radius: 50%; display: inline-block; flex: none; }}
  .nav-count {{ margin-left: auto; color: var(--text-2); font-size: 12px; }}

  .content {{ padding: 24px; }}
  h1 {{ font-size: 24px; font-weight: 700; letter-spacing: -0.02em; }}
  .sub {{ color: var(--text-2); font-size: 13px; margin: 4px 0 20px; }}
  .note {{ font-size: 12px; color: var(--text-2); background: var(--sidebar);
           border: 1px solid var(--separator); border-radius: 10px; padding: 10px 14px; margin: 12px 0; }}

  .kpis {{ display: flex; gap: 12px; flex-wrap: wrap; margin: 16px 0; }}
  .kpi {{ flex: 1 1 120px; background: var(--card); border: 1px solid var(--separator);
          border-radius: var(--radius); padding: 16px; text-align: center; box-shadow: var(--shadow); }}
  .kpi .num {{ font-size: 30px; font-weight: 700; letter-spacing: -0.02em; }}
  .kpi .num.green {{ color: var(--green); }} .kpi .num.red {{ color: var(--red); }}
  .kpi .lbl {{ font-size: 12px; color: var(--text-2); margin-top: 2px; }}

  .panel {{ background: var(--card); border: 1px solid var(--separator); border-radius: var(--radius);
            padding: 18px; margin: 16px 0; box-shadow: var(--shadow); }}
  .panel h3 {{ font-size: 14px; margin-bottom: 12px; }}

  .bar-row {{ display: flex; align-items: center; gap: 10px; margin: 6px 0; }}
  .bar-lbl {{ width: 84px; font-size: 13px; color: var(--text-2); }}
  .bar {{ flex: 1; background: var(--bg); border-radius: 6px; overflow: hidden; }}
  .bar-fill {{ color: #fff; font-size: 12px; font-weight: 600; padding: 2px 8px;
               border-radius: 6px; min-width: 26px; text-align: left; }}

  table {{ border-collapse: collapse; width: 100%; margin: 10px 0; font-size: 13px; }}
  th, td {{ text-align: left; padding: 8px 12px; border-bottom: 1px solid var(--separator); }}
  th {{ color: var(--text-2); font-weight: 600; font-size: 12px; }}
  .num-cell {{ font-variant-numeric: tabular-nums; font-weight: 600; }}

  .group-sec {{ margin: 22px 0; }}
  .group-sec h2 {{ font-size: 17px; font-weight: 600; display: flex; align-items: center; gap: 8px;
                   padding-bottom: 8px; border-bottom: 1px solid var(--separator); }}
  .group-sec h2 .count {{ color: var(--text-2); font-weight: 500; font-size: 13px; }}

  .card {{ background: var(--card); border: 1px solid var(--separator); border-left: 4px solid var(--accent);
           border-radius: var(--radius); padding: 16px 18px; margin: 12px 0; box-shadow: var(--shadow); }}
  .card-head {{ display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; }}
  .head-left {{ display: flex; align-items: center; gap: 8px; }}
  .qid {{ font-weight: 700; font-size: 15px; }}
  .pill {{ color: #fff; font-size: 12px; font-weight: 600; padding: 2px 10px; border-radius: 999px; }}
  .scenario {{ font-size: 12px; color: var(--text-2); background: var(--bg);
               padding: 2px 8px; border-radius: 6px; }}
  .badge {{ padding: 2px 8px; border-radius: 999px; font-size: 12px; font-weight: 600; color: #fff; }}
  .badge.regress {{ background: var(--red); }} .badge.improve {{ background: var(--green); }}

  .kv {{ display: grid; grid-template-columns: 86px 1fr; gap: 8px; padding: 5px 0; font-size: 14px; }}
  .kv label {{ color: var(--text-2); font-size: 12px; padding-top: 2px; }}
  .kv .val {{ word-break: break-word; }}
  .kv.meta {{ display: inline-grid; grid-template-columns: auto 1fr; gap: 6px; margin-right: 18px; font-size: 12px; }}
  ul.cites, ul.flags {{ list-style: none; }}
  ul.cites li, ul.flags li {{ margin: 2px 0; font-size: 13px; }}
  code {{ font-family: "SF Mono", ui-monospace, Menlo, monospace; font-size: 12px;
          background: var(--bg); padding: 1px 6px; border-radius: 5px; }}
  .muted {{ color: var(--text-2); }}
  .human {{ color: var(--indigo); }}
  .semantic .val {{ color: var(--blue); }}
  .err {{ color: var(--red); }}
</style>
</head>
<body>
  <div class="titlebar">
    <div class="title"><b>RAG 回归评测报告</b> · {_esc(meta.get("dataset", ""))}</div>
  </div>
  <div class="layout">
    <aside class="sidebar">
      <h3>基线 vs 候选</h3>
      <div class="nav-item"><span class="dot" style="background:var(--blue)"></span>{_esc(meta["baseline_label"])}</div>
      <div class="nav-item"><span class="dot" style="background:var(--gray)"></span>{_esc(meta["candidate_label"])}</div>
      <h3>错误分组</h3>
      {nav}
    </aside>
    <main class="content">
      <h1>回归评测报告</h1>
      <div class="sub">生成于 {_esc(meta["generated_at"])} · 自动结果 = 确定性规则检查 · 语义评分辅助 · 人工标注单独展示</div>
      <div class="kpis">{kpi_html}</div>

      <section class="panel">
        <h3>候选版错误分布</h3>
        {bars}
      </section>

      <section class="panel">
        <h3>回归差异</h3>
        <table><tr><th>类型</th><th>数量</th><th>题目</th></tr>{reg_rows}</table>
      </section>

      <div class="note">说明：自动结果 = 确定性规则检查；语义评分仅作辅助参考（不参与分组）；人工标注与自动结果分开，不以单个总分掩盖高风险错误。</div>

      <h2 style="margin-top:20px">基线版 · {_esc(meta["baseline_label"])}</h2>
      {b_sections}
      {("<h2 style='margin-top:28px'>候选版 · " + _esc(meta["candidate_label"]) + "</h2>" + c_sections) if cs is not None else ""}
    </main>
  </div>
</body>
</html>"""
