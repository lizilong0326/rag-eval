"""核心循环回归：导入 → 调用 → 规则检查 → 报告；重复运行结果一致。"""
from pathlib import Path

from rag_eval.adapter import MockAdapter
from rag_eval.data import load_corpus, load_dataset, load_enterprises
from rag_eval.mock_system import MockQASystem
from rag_eval.runner import evaluate, run

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

GROUPS = {"模型补写", "接口失败", "过期资料", "越权"}


def _load():
    return (load_dataset(DATA / "dataset.yaml"),
            load_corpus(DATA / "corpus.yaml"),
            load_enterprises(DATA / "enterprises.yaml"))


def _index(corpus, ents):
    return {d.doc_id: d for d in corpus}, {e.enterprise_id: e for e in ents}


def test_dataset_size():
    dataset, _, _ = _load()
    assert len(dataset) == 20
    scenarios = {d.scenario for d in dataset}
    assert {"normal", "insufficient", "outdated", "cross_enterprise", "conflict"} <= scenarios


def test_baseline_all_pass():
    dataset, corpus, ents = _load()
    base = MockAdapter(MockQASystem(corpus, ents, inject={}, label="baseline-v1"))
    results = evaluate(dataset, base, *_index(corpus, ents))
    assert len(results) == 20
    assert all(r.ok for r in results), [r.question_id for r in results if not r.ok]


def test_demo_four_regressions(tmp_path):
    from rag_eval.cli import DEMO_INJECT
    dataset, corpus, ents = _load()
    baseline = MockAdapter(MockQASystem(corpus, ents, inject={}, label="baseline-v1"))
    candidate = MockAdapter(MockQASystem(corpus, ents, inject=DEMO_INJECT, label="candidate-v2"))
    report = run(dataset, corpus, ents, baseline, candidate, tmp_path,
                 labels={"baseline": "baseline-v1", "candidate": "candidate-v2"},
                 dataset_meta={"dataset": "demo"})

    s = report["summary"]
    assert s["baseline"]["fail"] == 0
    assert s["candidate"]["fail"] == 4
    assert set(s["candidate"]["by_group"].keys()) & GROUPS == GROUPS
    assert s["regression"]["regressed"] == ["Q01", "Q04", "Q12", "Q15"]
    # 报告文件与复现包落盘
    assert (tmp_path / "report.json").exists()
    assert (tmp_path / "report.html").exists()
    assert (tmp_path / "repro" / "candidate-v2" / "Q01.json").exists()


def test_rerun_deterministic(tmp_path):
    from rag_eval.cli import DEMO_INJECT
    dataset, corpus, ents = _load()
    def _run():
        return run(dataset, corpus, ents,
                   MockAdapter(MockQASystem(corpus, ents, inject={}, label="b")),
                   MockAdapter(MockQASystem(corpus, ents, inject=DEMO_INJECT, label="c")),
                   tmp_path, labels={"baseline": "b", "candidate": "c"},
                   dataset_meta={"dataset": "demo"})
    r1 = _run()
    r2 = _run()
    assert r1["summary"] == r2["summary"]
    assert r1["baseline"] == r2["baseline"]
    assert r1["candidate"] == r2["candidate"]
