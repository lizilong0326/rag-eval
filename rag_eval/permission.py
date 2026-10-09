"""权限控制：被测接口白名单校验，默认拒绝，拒绝事件记审计日志。

对应 PRD 决策 17/20：地址与凭据不在白名单内即拒绝调用，归入「接口失败」。
"""
from __future__ import annotations

import logging
from urllib.parse import urlparse

logger = logging.getLogger("rag_eval.audit")


class PermissionDenied(RuntimeError):
    """地址或凭据未通过白名单校验。"""


def check_endpoint(url: str, token: str, allow_hosts: list[str],
                   allow_tokens: list[str] | None = None) -> None:
    host = (urlparse(url).hostname or "").lower()
    if not host or (allow_hosts and host not in [h.lower() for h in allow_hosts]):
        logger.warning("audit=deny host=%r reason=host-not-in-allowlist", host)
        raise PermissionDenied(f"被测接口 host 不在白名单：{host or '(空)'}")
    if allow_tokens and token not in allow_tokens:
        logger.warning("audit=deny host=%s reason=token-not-in-allowlist", host)
        raise PermissionDenied("被测接口凭据不在白名单")
    logger.info("audit=allow host=%s", host)
