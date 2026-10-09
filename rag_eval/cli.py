"""命令行入口。

  python -m rag_eval demo                # 一键演示：mock 基线 vs 候选（注入四类错误）
  python -m rag_eval run --dataset ...   # 真实 HTTP 被测接口（或继续用 mock）
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .adapter import HttpAdapter, MockAdapter
from .data import load_annotations, load_corpus, load_dataset, load_enterprises
from .mock_system import MockQASystem
from .promptfoo import export_promptfoo
from .runner import run
from .semantic import SemanticGrader

ROOT = Path(__file__).resolve().parent.parent
DEMO_DATA = ROOT / "data"

# 演示用四类注入错误（与 PRD 验收一致）
DEMO_INJECT = {
    "Q01": "fabrication",       # 无来源补写 → 模型补写
    "Q04": "timeout",           # 接口超时 → 接口失败
    "Q12": "expired",           # 过期政策 → 过期资料
    "Q15": "cross_enterprise",  # 跨企业引用 → 越权
}


def _make_grader(enabled: bool):
    return SemanticGrader() if enabled else None


def _load_demo():
    corpus = load_corpus(DEMO_DATA / "corpus.yaml")
    enterprises = load_enterprises(DEMO_DATA / "enterprises.yaml")
    dataset = load_dataset(DEMO_DATA / "dataset.yaml")
    return dataset, corpus, enterprises


def cmd_demo(args) -> int:
    dataset, corpus, enterprises = _load_demo()
    baseline = MockAdapter(MockQASystem(corpus, enterprises, inject={}, label="baseline-v1"))
    candidate = MockAdapter(MockQASystem(corpus, enterprises, inject=DEMO_INJECT, label="candidate-v2"))
    out = Path(args.out)
    report = run(dataset, corpus, enterprises, baseline, candidate, out,
                 labels={"baseline": "baseline-v1", "candidate": "candidate-v2"},
                 dataset_meta={"dataset": "demo-房车客服-合成数据", "version": "1.0",
                               "data_source": "全部合成，不包含真实客户信息"},
                 grader=_make_grader(args.semantic))
    s = report["summary"]
    print(f"\n✅ 演示完成：{out}")
    print(f"   基线 {s['baseline']['total']} 题：通过 {s['baseline']['pass']}，失败 {s['baseline']['fail']}")
    print(f"   候选 {s['candidate']['total']} 题：通过 {s['candidate']['pass']}，失败 {s['candidate']['fail']}")
    reg = s["regression"]
    print(f"   回归：退化 {len(reg['regressed'])} 题 → {', '.join(reg['regressed'])}")
    print(f"   报告：{out / 'report.html'}（可阅读页面） / {out / 'report.json'}（机器可读）")
    return 0


def cmd_run(args) -> int:
    corpus = load_corpus(args.corpus)
    enterprises = load_enterprises(args.enterprises)
    dataset = load_dataset(args.dataset)
    annotations = load_annotations(args.annotations) if args.annotations else {}

    if args.mock:
        inject = {}
        if args.inject:
            inject = json.loads(Path(args.inject).read_text(encoding="utf-8"))
        baseline = MockAdapter(MockQASystem(corpus, enterprises, inject={}, label=args.baseline_label))
        candidate = MockAdapter(MockQASystem(corpus, enterprises, inject=inject, label=args.candidate_label))
    else:
        if not args.url:
            print("❌ 非 mock 模式需要 --url 指定被测接口地址")
            return 2
        baseline = HttpAdapter(url=args.url, token=args.token,
                               allow_hosts=args.allow_hosts.split(",") if args.allow_hosts else [],
                               allow_tokens=args.allow_tokens.split(",") if args.allow_tokens else [],
                               timeout_seconds=args.timeout)
        candidate = None
        if args.candidate_url:
            candidate = HttpAdapter(url=args.candidate_url, token=args.token,
                                    allow_hosts=args.allow_hosts.split(",") if args.allow_hosts else [],
                                    allow_tokens=args.allow_tokens.split(",") if args.allow_tokens else [],
                                    timeout_seconds=args.timeout)

    report = run(dataset, corpus, enterprises, baseline, candidate, Path(args.out),
                 labels={"baseline": args.baseline_label, "candidate": args.candidate_label},
                 dataset_meta={"dataset": str(args.dataset), "version": "1.0"},
                 annotations=annotations, grader=_make_grader(args.semantic))
    print(f"\n✅ 报告已生成：{args.out}")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    return 0


def cmd_export_promptfoo(args) -> int:
    dataset = load_dataset(args.dataset)
    out = export_promptfoo(dataset, Path(args.out), args.url)
    print(f"✅ promptfoo 配置已导出：{out}")
    print("   运行：npx promptfoo@latest eval -c " + str(out))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="rag_eval", description="RAG 回归评测与错误归因系统")
    p.add_argument("--version", action="version", version=f"rag_eval {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("demo", help="一键演示：mock 基线 vs 候选（注入四类错误）")
    d.add_argument("-o", "--out", default="out/demo")
    d.add_argument("--semantic", action="store_true", help="启用 DeepSeek 语义评分（默认关闭）")
    d.set_defaults(func=cmd_demo)

    r = sub.add_parser("run", help="跑题集（mock 或真实 HTTP）")
    r.add_argument("--dataset", required=True)
    r.add_argument("--corpus", required=True)
    r.add_argument("--enterprises", required=True)
    r.add_argument("--mock", action="store_true", help="用进程内 mock（配合 --inject）")
    r.add_argument("--inject", help="mock 错误注入 JSON 文件：{question_id: error_type}")
    r.add_argument("--url", help="被测接口 URL（非 mock 模式必填）")
    r.add_argument("--candidate-url", help="候选版接口 URL（可选，用于两版回归）")
    r.add_argument("--token", default="", help="Bearer 凭据")
    r.add_argument("--allow-hosts", default="", help="host 白名单，逗号分隔")
    r.add_argument("--allow-tokens", default="", help="token 白名单，逗号分隔")
    r.add_argument("--timeout", type=float, default=5.0, help="接口超时秒数（默认 5）")
    r.add_argument("--baseline-label", default="baseline")
    r.add_argument("--candidate-label", default="candidate")
    r.add_argument("--annotations", help="人工标注 YAML：{annotations: {question_id: 文本}}")
    r.add_argument("--semantic", action="store_true", help="启用 DeepSeek 语义评分（默认关闭）")
    r.add_argument("-o", "--out", default="out/run")
    r.set_defaults(func=cmd_run)

    e = sub.add_parser("export-promptfoo", help="把题集导出为 promptfoo 测试配置")
    e.add_argument("--dataset", required=True)
    e.add_argument("--url", required=True, help="被测接口 URL")
    e.add_argument("-o", "--out", default="out/promptfooconfig.yaml")
    e.set_defaults(func=cmd_export_promptfoo)
    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
