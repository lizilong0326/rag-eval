"""硬化层测试：语义评分（stub，不调真实 API）与 promptfoo 导出。"""
from pathlib import Path

from rag_eval.data import load_corpus, load_dataset, load_enterprises
from rag_eval.promptfoo import build_promptfoo_config

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


class _Resp:
    content = [type("B", (), {"type": "text", "text": '{"score": 85, "rationale": "覆盖了期望要点"}'})()]


class _Msg:
    def __init__(self):
        self.calls = []
    def create(self, **kw):
        self.calls.append(kw)
        return _Resp()


class _Client:
    def __init__(self):
        self.messages = _Msg()


class StubGrader:
    def grade(self, question, answer, expected_points):
        return {"enabled": True, "score": 90, "rationale": "stub", "model": "stub", "error": ""}


def test_semantic_grader_parses_json():
    from rag_eval.semantic import SemanticGrader
    client = _Client()
    grader = SemanticGrader(model="fake", client=client)
    s = grader.grade("示例房车首保周期？", "首保周期为5000公里。", ["5000公里"])
    assert s.enabled and s.score == 85 and s.rationale == "覆盖了期望要点"
    assert client.messages.calls


def test_semantic_error_degrades_gracefully():
    from rag_eval.semantic import SemanticGrader

    class _BadMsg:
        def create(self, **kw):
            raise RuntimeError("boom")
    class _BadClient:
        messages = _BadMsg()

    s = SemanticGrader(model="fake", client=_BadClient()).grade("q", "a", [])
    assert s.enabled and s.error and "boom" in s.error


def test_semantic_attached_to_result():
    from rag_eval.adapter import MockAdapter
    from rag_eval.mock_system import MockQASystem
    from rag_eval.runner import evaluate
    dataset = load_dataset(DATA / "dataset.yaml")
    corpus = load_corpus(DATA / "corpus.yaml")
    ents = load_enterprises(DATA / "enterprises.yaml")
    item = dataset[0]
    adapter = MockAdapter(MockQASystem(corpus, ents, inject={}, label="b"))
    result = evaluate([item], adapter, {d.doc_id: d for d in corpus},
                      {e.enterprise_id: e for e in ents}, grader=StubGrader())[0]
    assert result.semantic and result.semantic["score"] == 90
    assert result.group == "通过"   # 语义评分不改变规则分组


def test_promptfoo_export():
    dataset = load_dataset(DATA / "dataset.yaml")
    cfg = build_promptfoo_config(dataset, "http://127.0.0.1:8000/ask")
    assert len(cfg["tests"]) == 20
    q18 = next(t for t in cfg["tests"] if t["vars"]["question"] == "示例房车首保周期是多少？")
    assert {"type": "contains", "value": "5000公里"} in q18["assert"]
    assert {"type": "not-contains", "value": "终身免保"} in q18["assert"]
