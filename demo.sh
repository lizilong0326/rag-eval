#!/usr/bin/env bash
# 一键启动演示：mock 基线版 vs 候选版（注入四类错误），输出报告。
set -euo pipefail
cd "$(dirname "$0")"

PY="${PYTHON:-}"
if [ -z "$PY" ]; then
  for cand in ../.venv/bin/python .venv/bin/python python3.12 python3.11 python3; do
    if command -v "$cand" >/dev/null 2>&1; then PY="$cand"; break; fi
  done
fi

echo "==> 使用 $("$PY" --version)"
if ! "$PY" -c "import yaml" >/dev/null 2>&1; then
  echo "==> 安装依赖 pyyaml ..."
  "$PY" -m pip install -q -r requirements.txt
fi

"$PY" -m rag_eval demo -o out/demo
echo ""
echo "==> 打开报告：open out/demo/report.html"
