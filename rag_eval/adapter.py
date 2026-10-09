"""统一适配器：调用被测问答接口。

- MockAdapter：进程内 mock（演示 / 测试）。
- HttpAdapter：真实 HTTP 调用，Bearer 鉴权，白名单校验，
  超时 5s（可配置），仅对超时与 5xx 重试 1 次，4xx/连接拒绝/结构异常不重试。
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

from .models import Citation, DatasetItem, QAResponse
from .mock_system import MockQASystem
from .permission import check_endpoint


class Adapter:
    def ask(self, item: DatasetItem, redacted_question: str) -> QAResponse:
        raise NotImplementedError


class MockAdapter(Adapter):
    def __init__(self, system: MockQASystem):
        self.system = system

    def ask(self, item: DatasetItem, redacted_question: str) -> QAResponse:
        start = time.perf_counter()
        resp = self.system.ask(item, redacted_question)
        resp.latency_ms = int((time.perf_counter() - start) * 1000)
        return resp


class HttpAdapter(Adapter):
    def __init__(self, url: str, token: str = "", allow_hosts: list[str] | None = None,
                 allow_tokens: list[str] | None = None, timeout_seconds: float = 5.0,
                 retry: bool = True):
        self.url = url
        self.token = token
        self.allow_hosts = allow_hosts or []
        self.allow_tokens = allow_tokens or []
        self.timeout = timeout_seconds
        self.retry = retry

    def ask(self, item: DatasetItem, redacted_question: str) -> QAResponse:
        payload = json.dumps({
            "question_id": item.id,
            "question": redacted_question,
            "enterprise_id": item.enterprise_id,
            "version": item.version,
        }, ensure_ascii=False).encode("utf-8")
        return self._post(payload)

    def _post(self, payload: bytes) -> QAResponse:
        try:
            check_endpoint(self.url, self.token, self.allow_hosts, self.allow_tokens)
        except Exception as exc:  # noqa: BLE001 —— 拒绝调用也归接口失败
            return QAResponse(endpoint_error=f"permission_denied: {exc}")

        attempts = 2 if self.retry else 1
        last: QAResponse | None = None
        for i in range(attempts):
            start = time.perf_counter()
            req = urllib.request.Request(
                self.url, data=payload, method="POST",
                headers={"Content-Type": "application/json",
                         "Authorization": f"Bearer {self.token}"},
            )
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    raw = r.read().decode("utf-8")
                    return self._parse(raw, start)
            except urllib.error.HTTPError as e:
                code = e.code
                last = QAResponse(endpoint_error=f"http_{code}", latency_ms=self._elapsed(start))
                if code >= 500 and i < attempts - 1:      # 仅 5xx 重试
                    continue
                return last
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                is_timeout = isinstance(e, TimeoutError) or (
                    isinstance(e, urllib.error.URLError) and isinstance(e.reason, TimeoutError))
                reason = "timeout" if is_timeout else "connection_error"
                last = QAResponse(endpoint_error=reason, latency_ms=self._elapsed(start))
                if reason == "timeout" and i < attempts - 1:   # 仅超时重试
                    continue
                return last
        return last or QAResponse(endpoint_error="unknown")

    @staticmethod
    def _elapsed(start: float) -> int:
        return int((time.perf_counter() - start) * 1000)

    @staticmethod
    def _parse(raw: str, start: float) -> QAResponse:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return QAResponse(endpoint_error="invalid_json",
                              latency_ms=HttpAdapter._elapsed(start))
        citations = [Citation(doc_id=c.get("doc_id", ""),
                              enterprise_id=c.get("enterprise_id", ""),
                              version=c.get("version", ""))
                     for c in data.get("citations", []) if isinstance(c, dict)]
        return QAResponse(
            answer=data.get("answer", "") or "",
            citations=citations,
            model_version=data.get("model_version", "") or "",
            knowledge_version=data.get("knowledge_version", "") or "",
            latency_ms=int(data.get("latency_ms", 0) or HttpAdapter._elapsed(start)),
        )
