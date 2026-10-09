"""本地 HTTP mock 服务：把 MockQASystem 暴露为真实 HTTP 接口，演练 HttpAdapter 全链路。

用法：
  python -m rag_eval.serve_mock --port 8000
  python -m rag_eval.serve_mock --port 8001 --inject data/inject-candidate.json --delay 6

错误注入（--inject JSON: {question_id: error_type}）：
  - timeout：sleep delay 秒后再响应，触发客户端超时 + 重试
  - http_500：返回 HTTP 500，触发客户端 5xx 重试
  - cross_enterprise / expired / fabrication：正常 200，但携带相应错误内容（由规则层检出）
"""
from __future__ import annotations

import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .data import load_corpus, load_enterprises
from .mock_system import MockQASystem
from .models import DatasetItem

ROOT = Path(__file__).resolve().parents[1]


def _load_inject(path: str | None) -> dict[str, str]:
    if not path:
        return {}
    return json.loads(Path(path).read_text(encoding="utf-8"))


class _Handler(BaseHTTPRequestHandler):
    system: MockQASystem
    token: str = ""
    delay: float = 6.0

    def do_POST(self):
        if self.path.rstrip("/") != "/ask":
            self.send_error(404, "not found")
            return
        if self.token and self.headers.get("Authorization") != f"Bearer {self.token}":
            self.send_error(401, "unauthorized")
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length) or b"{}")
        except (json.JSONDecodeError, ValueError):
            self.send_error(400, "bad json")
            return

        item = DatasetItem(
            id=body.get("question_id", ""),
            question=body.get("question", ""),
            enterprise_id=body.get("enterprise_id", ""),
            version=body.get("version", ""),
        )
        err = self.system.inject.get(item.id)
        if err == "timeout":
            time.sleep(self.delay)   # 超过客户端超时，触发 HttpAdapter 超时 + 重试
            self._respond(200, {"answer": "", "citations": [],
                                "model_version": self.system.label})
            return
        if err == "http_500":
            self._respond(500, {"error": "internal server error"})
            return

        resp = self.system.ask(item, body.get("question", ""))
        self._respond(200, {
            "answer": resp.answer,
            "citations": [{"doc_id": c.doc_id, "enterprise_id": c.enterprise_id,
                           "version": c.version} for c in resp.citations],
            "model_version": resp.model_version,
            "knowledge_version": resp.knowledge_version,
            "latency_ms": resp.latency_ms,
        })

    def _respond(self, code: int, data: dict) -> None:
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        try:
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError):
            pass   # 客户端已超时断开，忽略写失败

    def log_message(self, *args):  # 静默，避免刷屏
        pass


def serve(port: int, corpus, enterprises, inject: dict | None = None,
          token: str = "", delay: float = 6.0) -> None:
    system = MockQASystem(corpus, enterprises, inject=inject or {}, label=f"mock-{port}")
    handler = type("BoundHandler", (_Handler,), {})
    handler.system = system
    handler.token = token
    handler.delay = delay
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    print(f"mock 服务已启动：http://127.0.0.1:{port}/ask"
          f"（注入 {len(inject or {})} 项，timeout 延迟 {delay}s）", flush=True)
    server.serve_forever()


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--corpus", default=str(ROOT / "data" / "corpus.yaml"))
    p.add_argument("--enterprises", default=str(ROOT / "data" / "enterprises.yaml"))
    p.add_argument("--inject", help="注入 JSON 文件：{question_id: error_type}")
    p.add_argument("--token", default="", help="如需鉴权，指定 Bearer token")
    p.add_argument("--delay", type=float, default=6.0,
                   help="timeout 注入的延迟秒数（应大于客户端超时 5s）")
    args = p.parse_args()
    serve(args.port, load_corpus(args.corpus), load_enterprises(args.enterprises),
          _load_inject(args.inject), args.token, args.delay)


if __name__ == "__main__":
    main()
