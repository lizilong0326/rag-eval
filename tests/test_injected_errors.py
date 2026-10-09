"""四类注入错误的固定失败样例：报告必须定位到具体题目与证据。"""
import pytest

from rag_eval.adapter import MockAdapter
from rag_eval.data import load_corpus, load_dataset, load_enterprises
from rag_eval.mock_system import MockQASystem
from rag_eval.runner import evaluate

ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


@pytest.fixture(scope="module")
def ctx():
    dataset = load_dataset(DATA / "dataset.yaml")
    corpus = load_corpus(DATA / "corpus.yaml")
    ents = load_enterprises(DATA / "enterprises.yaml")
    return dataset, {d.doc_id: d for d in corpus}, {e.enterprise_id: e for e in ents}


def _run_one(ctx, question_id, error):
    dataset, corpus_by_id, ent_by_id = ctx
    item = next(d for d in dataset if d.id == question_id)
    corpus = load_corpus(DATA / "corpus.yaml")
    ents = load_enterprises(DATA / "enterprises.yaml")
    adapter = MockAdapter(MockQASystem(corpus, ents, inject={question_id: error}, label="candidate"))
    return evaluate([item], adapter, corpus_by_id, ent_by_id)[0]


def test_cross_enterprise_localized(ctx):
    r = _run_one(ctx, "Q15", "cross_enterprise")
    assert r.group == "越权"
    assert any(f.code == "citation_wrong_enterprise" for f in r.flags)
    assert r.citations and r.citations[0].enterprise_id == "ent_xw"


def test_expired_localized(ctx):
    r = _run_one(ctx, "Q12", "expired")
    assert r.group == "过期资料"
    assert any(f.code == "citation_expired" for f in r.flags)
    assert r.citations and r.citations[0].version == "v2"


def test_fabrication_localized(ctx):
    r = _run_one(ctx, "Q01", "fabrication")
    assert r.group == "模型补写"
    assert any(f.code == "no_citation" for f in r.flags)
    assert r.citations == []


def test_timeout_localized(ctx):
    r = _run_one(ctx, "Q04", "timeout")
    assert r.group == "接口失败"
    assert any(f.code == "endpoint_error" for f in r.flags)
