# -*- coding: utf-8 -*-
"""
可翻译文本过滤器 - Shared translatable-text filter

供世界扫描(scan_worker)与材质包/光影包扫描(pack_helper)共用。
规则与原来 scan_worker.is_translatable_text 保持一致：
过滤纯数字/符号/UUID/坐标/命令前缀等明显非自然语言的字符串。
"""

import re

_UUID_RE = re.compile(r'^[a-fA-F0-9-]{36}$')
_COORD_RE = re.compile(r'^-?\d+(?:\s+-?\d+){1,2}$')


def is_translatable_text(text, allow_prefix: bool = False, max_len: int = 1000) -> bool:
    """
    判断字符串是否为可翻译的自然语言文本。

    allow_prefix=True 时跳过对 / @ # 开头内容的过滤
    （用于已从命令/键值对中提取出的纯文本，如材质包 lang 值、告示牌文字）。
    """
    if not text or not isinstance(text, str):
        return False
    if len(text.strip()) < 2 or len(text) > max_len:
        return False
    # 纯数字、符号或代码（如 "===="、"--3"）
    if re.match(r'^[\d\s\W]+$', text):
        return False
    # 明显的命令或代码前缀（仅对整段文本生效）
    if not allow_prefix:
        if text.startswith('/') or text.startswith('@') or text.startswith('#'):
            return False
    # UUID 等标识符
    if _UUID_RE.match(text):
        return False
    # 坐标等数字串
    if _COORD_RE.match(text.strip()):
        return False
    return True
