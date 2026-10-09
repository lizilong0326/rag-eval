"""敏感输入脱敏：手机号、邮箱、身份证号占位替换。

首版只做确定性模式匹配；姓名等需词典的脱敏由配置扩展。
"""
from __future__ import annotations

import re

_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"1[3-9]\d{9}"), "[手机号]"),
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "[邮箱]"),
    (re.compile(r"\b\d{17}[\dXx]\b"), "[身份证]"),
]


def redact(text: str) -> tuple[str, bool]:
    """返回 (脱敏后文本, 是否发生替换)。"""
    changed = False
    out = text
    for pat, repl in _PATTERNS:
        out, n = pat.subn(repl, out)
        if n:
            changed = True
    return out, changed
