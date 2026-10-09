"""规则检查（确定性）：引用核验、禁止断言、资料不足承认、错误分组。

分组优先级（报告六类）：接口失败 > 越权 > 过期资料 > 错引用 > 模型补写 > 未命中 > 通过。
所有命中的规则都保留为 flags 证据，不以单个分组掩盖其余问题。
"""
from __future__ import annotations

from .models import Citation, CorpusDoc, DatasetItem, EnterpriseVersion, Flag, ItemResult, QAResponse

GROUP_ENDPOINT = "接口失败"
GROUP_UNAUTHORIZED = "越权"
GROUP_EXPIRED = "过期资料"
GROUP_WRONG_CITE = "错引用"
GROUP_FABRICATE = "模型补写"
GROUP_MISS = "未命中"
GROUP_PASS = "通过"

ERROR_GROUPS = [GROUP_ENDPOINT, GROUP_UNAUTHORIZED, GROUP_EXPIRED,
                GROUP_WRONG_CITE, GROUP_FABRICATE, GROUP_MISS]

INSUFFICIENT_KEYWORDS = ("无法", "暂未", "未找到", "资料不足", "尚无", "暂无", "未收录", "没有相关")


def _overlap_ratio(answer: str, content: str) -> float:
    """答案字符在引用文档内容中的覆盖率（轻量「内容支撑」判定）。"""
    if not content or not answer:
        return 0.0
    sa = set(answer)
    if not sa:
        return 0.0
    return len(sa & set(content)) / len(sa)


def check_item(item: DatasetItem, resp: QAResponse,
               corpus_by_id: dict[str, CorpusDoc],
               ent_by_id: dict[str, EnterpriseVersion]) -> ItemResult:
    flags: list[Flag] = []

    if resp.endpoint_error:
        return ItemResult(
            question_id=item.id, scenario=item.scenario, group=GROUP_ENDPOINT,
            flags=[Flag("endpoint_error", resp.endpoint_error)],
            question=item.question, answer=resp.answer, citations=resp.citations,
            latency_ms=resp.latency_ms, model_version=resp.model_version,
            knowledge_version=resp.knowledge_version,
        )

    ent = ent_by_id.get(item.enterprise_id)
    unauthorized = expired = wrong = fabricate = miss = False

    # 1) 引用核验：存在性 / 归属企业 / 版本有效期 / 内容支撑
    for c in resp.citations:
        doc = corpus_by_id.get(c.doc_id)
        if doc is None:
            flags.append(Flag("citation_not_found", f"引用文档 {c.doc_id} 不存在"))
            wrong = True
            continue
        if doc.enterprise_id != item.enterprise_id:
            flags.append(Flag("citation_wrong_enterprise",
                              f"{c.doc_id} 属于 {doc.enterprise_id}，题目属于 {item.enterprise_id}"))
            unauthorized = True
        if ent is not None and not ent.in_window(doc.version):
            flags.append(Flag("citation_expired",
                              f"{c.doc_id} 版本 {doc.version} 已过期（有效窗口 {ent.valid_from}~{ent.valid_to}）"))
            expired = True
        if _overlap_ratio(resp.answer, doc.content) < 0.5:
            flags.append(Flag("citation_unsupported", f"答案与引用 {c.doc_id} 内容不支撑"))
            wrong = True

    # 2) 禁止断言
    for claim in item.forbidden_claims:
        if claim and claim in resp.answer:
            flags.append(Flag("forbidden_claim", f"答案说出禁止断言：{claim}"))
            fabricate = True

    # 3) 无来源补写（已承认资料不足的答案不算补写）
    admitted = any(k in resp.answer for k in INSUFFICIENT_KEYWORDS)
    if resp.answer.strip() and not resp.citations and not admitted:
        flags.append(Flag("no_citation", "答案有内容但无引用来源"))
        fabricate = True

    # 4) 资料不足是否被承认
    expect_admit = (item.scenario == "insufficient" or (not resp.answer.strip() and not resp.citations))
    if expect_admit and not admitted:
        flags.append(Flag("insufficient_not_admitted", "该承认资料不足却未承认"))
        if resp.answer.strip():
            fabricate = True
        else:
            miss = True

    # 5) 期望要点命中
    for point in item.expected_points:
        if point and point not in resp.answer:
            flags.append(Flag("missed_point", f"未命中期望要点：{point}"))
            miss = True

    # 分组（优先级从高到低）
    if unauthorized:
        group = GROUP_UNAUTHORIZED
    elif expired:
        group = GROUP_EXPIRED
    elif wrong:
        group = GROUP_WRONG_CITE
    elif fabricate:
        group = GROUP_FABRICATE
    elif miss:
        group = GROUP_MISS
    else:
        group = GROUP_PASS

    return ItemResult(
        question_id=item.id, scenario=item.scenario, group=group, flags=flags,
        question=item.question, answer=resp.answer, citations=resp.citations,
        latency_ms=resp.latency_ms, model_version=resp.model_version,
        knowledge_version=resp.knowledge_version,
    )
