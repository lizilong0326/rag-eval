#!/usr/bin/env bash
# 真机 HTTP 链路演示：起两个本地 mock 服务（基线 / 候选），用 HttpAdapter 跑真实 HTTP 回归。
set -euo pipefail
cd "$(dirname "$0")"

PY="${PYTHON:-}"
if [ -z "$PY" ]; then
  for cand in ../.venv/bin/python .venv/bin/python python3.12 python3.11 python3; do
    if command -v "$cand" >/dev/null 2>&1; then PY="$cand"; break; fi
  done
fi

echo "==> 使用 $("$PY" --version)"

# 起基线服务（无注入，8000）与候选服务（注入四类错误，8001）
"$PY" -m rag_eval.serve_mock --port 8000 &
PID_BASE=$!
"$PY" -m rag_eval.serve_mock --port 8001 --inject data/inject-candidate.json --delay 6 &
PID_CAND=$!
trap 'kill $PID_BASE $PID_CAND 2>/dev/null || true' EXIT

sleep 1  # 等服务就绪

echo ""
echo "==> 通过真实 HTTP 跑基线 vs 候选回归 …"
"$PY" -m rag_eval run \
  --dataset data/dataset.yaml --corpus data/corpus.yaml --enterprises data/enterprises.yaml \
  --url http://127.0.0.1:8000/ask \
  --candidate-url http://127.0.0.1:8001/ask \
  --allow-hosts 127.0.0.1 \
  -o out/http-demo

echo ""
echo "==> 打开报告：open out/http-demo/report.html"
open out/http-demo/report.html
