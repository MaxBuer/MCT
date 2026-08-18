# -*- coding: utf-8 -*-
"""
拖入文件/文件夹的统一类型识别与信息提取 - Source Detect

把「世界存档 / 材质包 / 光影包 / Mod」识别为统一 kind 并提取展示信息
（类型、名称、适用版本、图标字节），供第一步拖拽选择后自动分流。
"""

import os
import zipfile

from utils import pack_helper
from utils import nbt_helper


def detect_source(path: str):
    """
    识别路径类型。返回 (kind, meta, message)：
      kind: world / world_zip / resource / shader / mixed / mod / unknown / error
      meta: {name, version, description, icon_bytes, icon_fmt}
    """
    if not os.path.exists(path):
        return "error", {}, "路径不存在"

    if os.path.isfile(path):
        if not path.lower().endswith((".zip", ".jar")):
            return "error", {}, "请拖入文件夹，或 .zip / .jar 压缩包"
        return _detect_archive(path)

    if os.path.isdir(path):
        # 世界存档优先（level.dat）
        if os.path.exists(os.path.join(path, "level.dat")):
            return "world", nbt_helper.get_world_meta(path), "识别为 世界存档 (Java)"
        # 解压后的 Mod 文件夹
        if pack_helper.has_mod_meta(path):
            return "mod", pack_helper.extract_mod_meta(path), "识别为 Mod（模组文件夹）"
        # 材质包 / 光影包
        entries = pack_helper._entry_names(path)
        if any(n.endswith("pack.mcmeta") for n in entries):
            has_shader = any(n.startswith("shaders/") for n in entries)
            kind = "shader" if has_shader else "resource"
            meta = pack_helper.extract_pack_meta(path, kind)
            msg = "识别为 材质包 + 光影包（含 shaders）" if has_shader else "识别为 材质包"
            return kind, meta, msg
        if any(n.startswith("shaders/") for n in entries):
            return "shader", pack_helper.extract_pack_meta(path, "shader"), "识别为 光影包"
        return "unknown", {}, "无法识别：不是 世界存档 / Mod / 材质包 / 光影包"

    return "error", {}, "请拖入文件夹或文件"


def _detect_archive(path: str):
    """识别 zip/jar 压缩包类型"""
    # 1) Mod 元数据
    if pack_helper.has_mod_meta(path):
        meta = pack_helper.extract_mod_meta(path)
        msg = "识别为 Mod（模组）"
        try:
            with zipfile.ZipFile(path) as zf:
                names_l = [n.lower() for n in zf.namelist()]
        except Exception:
            names_l = []
        if any(n.endswith((".sf", ".rsa", ".sig")) for n in names_l):
            msg += "（带数字签名，写回后签名会失效，一般仍可正常加载）"
        return "mod", meta, msg
    # 2) 材质包 / 光影包
    try:
        with zipfile.ZipFile(path) as zf:
            entries = [n for n in zf.namelist() if not n.endswith("/")]
    except Exception as e:
        return "error", {}, f"无法读取压缩包: {e}"
    if any(n.endswith("pack.mcmeta") for n in entries):
        has_shader = any(n.startswith("shaders/") for n in entries)
        kind = "shader" if has_shader else "resource"
        meta = pack_helper.extract_pack_meta(path, kind)
        msg = "识别为 材质包 + 光影包（含 shaders）" if has_shader else "识别为 材质包"
        return kind, meta, msg
    if any(n.startswith("shaders/") for n in entries):
        return "shader", pack_helper.extract_pack_meta(path, "shader"), "识别为 光影包"
    if any(n.endswith("level.dat") for n in entries):
        return "world_zip", {}, "压缩包内包含 level.dat（世界压缩包暂不支持直接扫描，请先解压为文件夹）"
    return "unknown", {}, "无法识别：不是 Mod / 材质包 / 光影包"
