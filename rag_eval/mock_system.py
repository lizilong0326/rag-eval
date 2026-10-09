"""自建 mock 被测系统：演示与固定失败用例共用。

正确模式：只从「当前企业 + 当前版本」的语料里检索，检索不到就承认资料不足。
错误注入：timeout / cross_enterprise / expired / fabrication 四类（与 PRD 验收一致）。
"""
from __future__ import annotations

from .models import Citation, CorpusDoc, DatasetItem, EnterpriseVersion, QAResponse

ADMIT_TEXT = "抱歉，当前资料中暂未找到相关信息，无法回答。"


class MockQASystem:
    def __init__(self, corpus: list[CorpusDoc], enterprises: list[EnterpriseVersion],
                 inject: dict[str, str] | None = None, label: str = "mock"):
        self.corpus = corpus
        self.ent_by_id = {e.enterprise_id: e for e in enterprises}
        self.inject = inject or {}
        self.label = label

    def ask(self, item: DatasetItem, question: str) -> QAResponse:
        err = self.inject.get(item.id)
        if err == "timeout":
            return QAResponse(endpoint_error="timeout", model_version=self.label)

        ent = self.ent_by_id.get(item.enterprise_id)
        current = ent.version if ent else item.version
        valid_from = ent.valid_from if ent else current

        if err == "cross_enterprise":
            docs = [d for d in self.corpus if d.enterprise_id != item.enterprise_id]
            best = self._rank(question, docs)
            return self._answer(best) if best else self._admit()

        if err == "expired":
            docs = [d for d in self.corpus
                    if d.enterprise_id == item.enterprise_id and d.version < valid_from]
            best = self._rank(question, docs)
            return self._answer(best) if best else self._admit()

        if err == "fabrication":
            return QAResponse(answer="（合成）根据一般经验：可以，无需额外手续即可办理。",
                              citations=[], model_version=self.label)

        docs = [d for d in self.corpus
                if d.enterprise_id == item.enterprise_id and d.version == current]
        best = self._rank(question, docs)
        return self._answer(best) if best else self._admit()

    def _rank(self, question: str, docs: list[CorpusDoc]) -> CorpusDoc | None:
        scored: list[tuple[int, CorpusDoc]] = []
        q = set(question)
        for d in docs:
            if not any(k and k in question for k in d.keywords):
                continue
            scored.append((len(q & set(d.content)), d))
        if not scored:
            return None
        scored.sort(key=lambda x: -x[0])
        return scored[0][1]

    def _answer(self, doc: CorpusDoc) -> QAResponse:
        return QAResponse(
            answer=doc.content,
            citations=[Citation(doc_id=doc.doc_id, enterprise_id=doc.enterprise_id, version=doc.version)],
            knowledge_version=doc.version,
            model_version=self.label,
        )

    def _admit(self) -> QAResponse:
        return QAResponse(answer=ADMIT_TEXT, citations=[], model_version=self.label)
