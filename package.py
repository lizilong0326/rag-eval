"""按允许清单生成 rag-eval 分发包，不收集本地密钥、虚拟环境、缓存或运行产物。"""
from __future__ import annotations

import argparse
import os
import tempfile
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parent

# 顶层文件（允许清单）
ROOT_FILES = (
    "README.md", "requirements.txt", "config.example.yaml", ".env.example", "demo.sh",
)

# 目录文件模式（允许清单）
PATTERNS = (
    "data/*.yaml",
    "rag_eval/*.py",
    "tests/*.py",
)

# 绝对排除：即使误入允许清单也剔除
EXCLUDE_NAMES = {".env", "config.yaml", "out", "__pycache__", ".pytest_cache"}


def collect_files(root: Path) -> list[Path]:
    selected = {root / name for name in ROOT_FILES}
    for pattern in PATTERNS:
        selected.update(root.glob(pattern))

    files: list[Path] = []
    for path in sorted(selected, key=lambda p: p.relative_to(root).as_posix()):
        rel = path.relative_to(root)
        if any(part in EXCLUDE_NAMES for part in rel.parts):
            continue
        if not path.is_file():
            raise ValueError(f"缺少分发文件：{rel}")
        if any((root / Path(*rel.parts[:i])).is_symlink()
               for i in range(1, len(rel.parts) + 1)):
            raise ValueError(f"分发文件不能是符号链接：{rel}")
        if path.name == ".env.example":
            for line in path.read_text(encoding="utf-8").splitlines():
                name, sep, value = line.partition("=")
                if sep and name.strip() in {"ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"}:
                    if value.strip().strip('"\'') not in {"", "sk-ant-xxx"}:
                        raise ValueError(f"{rel} 含非占位凭证，请恢复模板再打包")
        files.append(path)
    return files


def package(root: Path, output: Path) -> tuple[int, int]:
    files = collect_files(root)
    if output.resolve() in {p.resolve() for p in files}:
        raise ValueError("输出路径不能覆盖分发源文件")
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".rag-eval-", suffix=".zip", dir=output.parent)
    os.close(fd)
    try:
        with ZipFile(temporary, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
            for path in files:
                archive.write(path, "rag-eval/" + path.relative_to(root).as_posix())
        os.replace(temporary, output)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return len(files), output.stat().st_size


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-o", "--out", type=Path, default=ROOT / "dist/rag-eval.zip")
    args = parser.parse_args()
    try:
        count, size = package(ROOT, args.out)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"打包失败：{exc}\n")
    print(f"已生成：{args.out.resolve()}（{count} 个文件，{size / 1024:.1f} KiB）")


if __name__ == "__main__":
    main()
