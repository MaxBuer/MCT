# -*- coding: utf-8 -*-
"""
材质包 / 光影包 汉化助手 - Resource Pack & Shader Pack Helper

支持「文件夹」或「.zip」两种形态的材质包(resource pack) / 光影包(shader pack)：

扫描可翻译文本：
  - lang 语言文件：
      * assets/*/lang/*.json   -> 翻译每个键对应的值（键是标识符，不翻译）
      * 任意 *.lang            -> 光影包 key=value 语言文件（shaders/lang/en_US.lang 等）
  - texts 文本文件：assets/*/texts/*.txt（splashes/credits/end，每行一条）
  - pack.mcmeta 的 description 字段
  - 其他 JSON 文件中白名单显示字段（text/title/subtitle/description/message 等）

写回译文（自动 .bak 备份；zip 整体备份后重建，未改动条目保持原压缩方式）：
  - lang JSON / 其他 JSON：解析后按键路径替换值再序列化（保留缩进与键顺序）
  - *.lang：逐行按 key=value 替换值（保留行尾与 = 前空格）
  - texts/*.txt：按行替换

location 约定：
  - 文件夹包：location = 文件完整路径
  - zip 包：   location = "<zip绝对路径>|<包内路径>"（'|' 在 Windows 文件名中非法，可安全作分隔符）
"""

import json
import os
import re
import shutil
import zipfile

from utils.logger import get_logger
from utils.text_filter import is_translatable_text

_LOC_SEP = "|"          # zip location 分隔符（Windows 文件名禁止 '|'）

# 非 lang 的通用 JSON 中视为「显示文本」的字段白名单（避免误改技术字段）
DISPLAY_KEYS = {
    "text", "title", "subtitle", "description", "message", "tooltip", "hint",
    "header", "footer", "label", "display_name", "displayName", "credits",
    "splash", "button", "warning", "info", "prompt", "placeholder",
}

# Minecraft 资源定位符（minecraft:xxx / modid:path），非自然语言，跳过
_RESOURCE_LOC_RE = re.compile(r"^[a-z0-9_.-]+:[a-z0-9_./-]+$")

# pack.mcmeta pack_format -> MC 版本（常用值）
PACK_FORMAT_VERSIONS = {
    1: "1.6.1 – 1.8.9", 2: "1.9 – 1.10.2", 3: "1.11 – 1.12.2",
    4: "1.13 – 1.14.4", 5: "1.15 – 1.16.1", 6: "1.16.2 – 1.16.5",
    7: "1.17 – 1.17.1", 8: "1.18 – 1.18.2", 9: "1.19 – 1.19.2",
    12: "1.19.3", 13: "1.19.4", 15: "1.20 – 1.20.1", 18: "1.20.2",
    22: "1.20.3 – 1.20.4", 32: "1.20.5 – 1.20.6", 34: "1.21 – 1.21.1",
    42: "1.21.2 – 1.21.3", 46: "1.21.4", 55: "1.21.5", 57: "1.21.6 – 1.21.7",
    61: "1.21.8", 63: "1.21.9+",
}

# Mod 元数据文件（任一存在即视为 Mod，小写比较）
_MOD_META_FILES = ("fabric.mod.json", "mcmod.info", "meta-inf/mods.toml")


def _is_archive(path: str) -> bool:
    return os.path.isfile(path) and path.lower().endswith((".zip", ".jar"))


# ---------------------------------------------------------------------------
# 基础工具
# ---------------------------------------------------------------------------
def _norm(p: str) -> str:
    """统一为 '/' 分隔的相对路径，便于按包内路径规则匹配"""
    return p.replace("\\", "/")


def _decode_bytes(data: bytes):
    """解码文件字节，返回 (文本, 写回时应使用的编码)。
    仅当文件带 UTF-8 BOM 时才用 utf-8-sig 写回（保留 BOM），否则用纯 utf-8。"""
    if data.startswith(b"\xef\xbb\xbf"):
        try:
            return data.decode("utf-8-sig"), "utf-8-sig"
        except UnicodeDecodeError:
            pass
    for enc in ("utf-8", "gbk", "latin-1"):
        try:
            return data.decode(enc), enc
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace"), "utf-8"


def _encode_bytes(text: str, encoding: str) -> bytes:
    return text.encode(encoding)


def _iter_pack_files(source: str):
    """枚举包内所有文件，yield (inner_path, is_zip)；跳过 .bak/.tmp 及压缩包自身的备份"""
    if _is_archive(source):
        try:
            with zipfile.ZipFile(source) as zf:
                for info in zf.infolist():
                    if info.is_dir():
                        continue
                    n = info.filename
                    if n.endswith(".bak") or n.endswith(".tmp"):
                        continue
                    yield n, True
        except Exception as e:
            get_logger().debug(f"读取 zip 失败 {source}: {e}")
    elif os.path.isdir(source):
        for root, _, files in os.walk(source):
            for f in files:
                if f.endswith(".bak") or f.endswith(".tmp"):
                    continue
                p = os.path.join(root, f)
                yield _norm(os.path.relpath(p, source)), False


def _read_bytes(source: str, inner: str, is_zip: bool) -> bytes:
    if is_zip:
        with zipfile.ZipFile(source) as zf:
            return zf.read(inner)
    path = os.path.join(source, *inner.split("/"))
    with open(path, "rb") as f:
        return f.read()


def make_location(source: str, inner: str, is_zip: bool) -> str:
    """把包内文件编码为统一 location 字符串"""
    if is_zip:
        return f"{source}{_LOC_SEP}{inner}"
    return os.path.join(source, *inner.split("/"))


def split_location(location: str):
    """解析 location -> (container, inner, is_zip)。
    文件夹：container=文件完整路径, inner=''；zip：container=zip 路径, inner=包内路径"""
    if _LOC_SEP in location:
        container, inner = location.split(_LOC_SEP, 1)
        if os.path.isfile(container):
            return container, inner, True
    return location, "", False


def _entry_names(source: str) -> list:
    """返回包内条目名列表（文件夹为相对路径，zip/jar 为内部路径）"""
    entries = []
    if _is_archive(source):
        try:
            with zipfile.ZipFile(source) as zf:
                entries = [n for n in zf.namelist() if not n.endswith("/")]
        except Exception as e:
            get_logger().debug(f"读取压缩包失败 {source}: {e}")
    elif os.path.isdir(source):
        for root, _, files in os.walk(source):
            for f in files:
                entries.append(_norm(os.path.relpath(os.path.join(root, f), source)))
    return entries


def has_mod_meta(source: str) -> bool:
    """判断是否为 Mod（含 fabric.mod.json / mcmod.info / META-INF/mods.toml 任一）"""
    names = [n.lower() for n in _entry_names(source)]
    return any(n == "fabric.mod.json" or n == "mcmod.info"
               or n.endswith("meta-inf/mods.toml") for n in names)


def detect_pack(source: str):
    """检测类型。返回 (kind, msg)；kind ∈ mod/resource/shader/mixed/unknown/error"""
    if not os.path.exists(source):
        return "error", "路径不存在"
    if not (_is_archive(source) or os.path.isdir(source)):
        return "error", "请选择文件夹或 .zip / .jar 文件"
    entries = _entry_names(source)
    entries_l = [n.lower() for n in entries]

    if has_mod_meta(source):
        signed = any(n.endswith((".sf", ".rsa", ".sig")) for n in entries_l)
        extra = "（带数字签名，写回后签名会失效，一般仍可正常加载）" if signed else ""
        return "mod", f"检测到 Mod 元数据 → Mod 模组{extra}"

    has_mcmeta = any(n.endswith("pack.mcmeta") for n in entries)
    has_shader = any(n.startswith("shaders/") for n in entries)
    has_lang = any(n.endswith(".lang") for n in entries)
    if has_mcmeta and (has_shader or has_lang):
        return "mixed", "检测到 pack.mcmeta 与 shaders/ → 按「材质包 + 光影包」同时扫描"
    if has_mcmeta:
        return "resource", "检测到 pack.mcmeta → 材质包 (Resource Pack)"
    if has_shader or has_lang:
        return "shader", "检测到 shaders/ 或 .lang → 光影包 (Shader Pack)"
    return "unknown", "未检测到 pack.mcmeta / shaders / Mod 元数据，仍将按通用 JSON 与文本扫描"


# ---------------------------------------------------------------------------
# 扫描
# ---------------------------------------------------------------------------
# 只读取/翻译英文语言文件（en_us / en_US，大小写不敏感），
# 跳过 zh_cn / de_de / ru_ru 等其他语言文件，避免重复扫描与误翻。
_EN_LANG_JSON = "en_us.json"
_EN_LANG_PROP = "en_us.lang"


def _is_en_basename(inner: str, target: str) -> bool:
    n = _norm(inner).lower()
    return n == target or n.endswith("/" + target)


def _is_lang_json(inner: str) -> bool:
    n = _norm(inner).lower()
    return n.endswith(".json") and "/lang/" in "/" + n and _is_en_basename(inner, _EN_LANG_JSON)


def _is_shader_lang(inner: str) -> bool:
    return _is_en_basename(inner, _EN_LANG_PROP)


def _is_texts_txt(inner: str) -> bool:
    n = _norm(inner).lower()
    return n.endswith(".txt") and "/texts/" in "/" + n


def _is_mcmeta(inner: str) -> bool:
    return _norm(inner).lower().endswith("pack.mcmeta")


def _add_result(results, original, typ, location, key, inner):
    if not is_translatable_text(original, allow_prefix=True):
        return
    if _RESOURCE_LOC_RE.match(original.strip()):
        return
    results.append({
        "original": original.strip(),
        "type": typ,
        "location": location,
        "key": key,
        "file": inner.split("/")[-1],
    })


def _scan_lang_json(source, inner, is_zip, results):
    data = _read_bytes(source, inner, is_zip)
    text, _enc = _decode_bytes(data)
    obj = json.loads(text)
    if not isinstance(obj, dict):
        return
    loc = make_location(source, inner, is_zip)
    for key, value in obj.items():
        if isinstance(value, str):
            _add_result(results, value, "lang_json", loc, key, inner)


def _scan_shader_lang(source, inner, is_zip, results):
    data = _read_bytes(source, inner, is_zip)
    text, _enc = _decode_bytes(data)
    loc = make_location(source, inner, is_zip)
    for line in text.splitlines():
        body = line.strip()
        if not body or body.startswith("#") or body.startswith("!") or "=" not in body:
            continue
        key, _, value = body.partition("=")
        key = key.strip()
        value = value.strip()
        if key and value:
            _add_result(results, value, "shader_lang", loc, key, inner)


def _scan_txt_file(source, inner, is_zip, results):
    data = _read_bytes(source, inner, is_zip)
    text, _enc = _decode_bytes(data)
    loc = make_location(source, inner, is_zip)
    for line in text.splitlines():
        _add_result(results, line, "txt_line", loc, "", inner)


def _walk_display_fields(obj, path, add):
    """递归遍历 JSON，收集白名单显示字段下的字符串值"""
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{path}/{k}" if path else k
            if k in DISPLAY_KEYS and isinstance(v, str):
                add(v, p)
            elif isinstance(v, (dict, list)):
                _walk_display_fields(v, p, add)
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            if isinstance(item, (dict, list)):
                _walk_display_fields(item, f"{path}[{i}]", add)


def _scan_json_file(source, inner, is_zip, results, pack_mcmeta=False):
    data = _read_bytes(source, inner, is_zip)
    text, _enc = _decode_bytes(data)
    obj = json.loads(text)
    if not isinstance(obj, (dict, list)):
        return
    loc = make_location(source, inner, is_zip)
    typ = "mcmeta_desc" if pack_mcmeta else "json_display"
    _walk_display_fields(obj, "", lambda v, p: _add_result(results, v, typ, loc, p, inner))


def scan_pack(source: str, scan_lang=True, scan_texts=True, scan_json=True,
              scan_mcmeta=True, progress=None, stop_flag=None) -> list:
    """
    扫描材质包/光影包内可翻译文本。
    progress(cur, total, msg)；stop_flag() -> bool 为 True 时提前停止。
    返回结果列表：[{original, type, location, key, file}, ...]
    """
    results = []
    files = list(_iter_pack_files(source))
    total = len(files)
    for i, (inner, is_zip) in enumerate(files):
        if stop_flag is not None and stop_flag():
            break
        if progress is not None:
            progress(i + 1, total, f"扫描: {inner}")
        try:
            if _is_shader_lang(inner):
                if scan_lang:
                    _scan_shader_lang(source, inner, is_zip, results)
            elif _is_mcmeta(inner):
                if scan_mcmeta:
                    _scan_json_file(source, inner, is_zip, results, pack_mcmeta=True)
            elif _is_lang_json(inner):
                if scan_lang:
                    _scan_lang_json(source, inner, is_zip, results)
            elif _is_texts_txt(inner):
                if scan_texts:
                    _scan_txt_file(source, inner, is_zip, results)
            elif _norm(inner).lower().endswith(".json"):
                if scan_json:
                    _scan_json_file(source, inner, is_zip, results)
        except Exception as e:
            get_logger().debug(f"扫描 {inner} 出错: {e}")
    return results


# ---------------------------------------------------------------------------
# 写回
# ---------------------------------------------------------------------------
def _detect_json_indent(text: str):
    m = re.search(r"\{\r?\n(\s+)\"", text)
    if m:
        ws = m.group(1)
        if "\t" in ws:
            return "\t"
        if 0 < len(ws) <= 8:
            return ws
    return 4


def _replace_json_path(node, path: str, orig: str, trans: str) -> bool:
    """按 '/' 分隔路径（含 [n] 列表下标）替换字符串值，返回是否成功"""
    parts = [p for p in path.split("/") if p]
    for idx, part in enumerate(parts):
        last = idx == len(parts) - 1
        m = re.fullmatch(r"(.+)\[(\d+)\]", part)
        if m:
            name, i = m.group(1), int(m.group(2))
            if isinstance(node, dict) and name in node and isinstance(node[name], list) \
                    and i < len(node[name]):
                if last:
                    if isinstance(node[name][i], str) and node[name][i] == orig:
                        node[name][i] = trans
                        return True
                    return False
                node = node[name][i]
            else:
                return False
        else:
            if isinstance(node, dict) and part in node:
                if last:
                    if isinstance(node[part], str) and node[part] == orig:
                        node[part] = trans
                        return True
                    return False
                node = node[part]
            else:
                return False
    return False


def _apply_json(text: str, entries: list):
    """JSON 写回：lang_json 按顶层键替换；json_display/mcmeta_desc 按路径替换。
    返回 (新文本, 已满足的条目下标集合)"""
    obj = json.loads(text)
    satisfied = set()
    for ei, e in enumerate(entries):
        if e["type"] == "lang_json":
            key = e["key"]
            if isinstance(obj, dict) and key in obj and isinstance(obj[key], str) \
                    and obj[key] == e["original"]:
                obj[key] = e["translation"]
                satisfied.add(ei)
        else:
            if _replace_json_path(obj, e["key"], e["original"], e["translation"]):
                satisfied.add(ei)
    indent = _detect_json_indent(text)
    out = json.dumps(obj, ensure_ascii=False, indent=indent)
    if text.endswith("\n"):
        out += "\n"
    return out, satisfied


def _apply_properties(text: str, entries: list):
    """*.lang（key=value）写回：按键定位、值匹配原文后替换，保留行尾与 '=' 前空格。
    返回 (新文本, 已满足的条目下标集合)"""
    lines = text.splitlines(keepends=True)
    by_key = {}
    for ei, e in enumerate(entries):
        by_key.setdefault(e["key"], []).append(ei)
    satisfied = set()
    for i, line in enumerate(lines):
        body = line.rstrip("\r\n")
        if not body or body.lstrip().startswith("#") or body.lstrip().startswith("!") \
                or "=" not in body:
            continue
        idx = body.index("=")
        key = body[:idx].strip()
        val = body[idx + 1:].strip()
        if key not in by_key:
            continue
        for ei in by_key[key]:
            e = entries[ei]
            if val == e["original"]:
                eol = "\r\n" if line.endswith("\r\n") else ("\n" if line.endswith("\n") else "")
                lines[i] = body[:idx] + "=" + e["translation"] + eol
                satisfied.add(ei)
                break
    return "".join(lines), satisfied


def _apply_txt(text: str, entries: list):
    """texts/*.txt 写回：整行匹配原文后替换（保留行首空白与行尾换行）。
    返回 (新文本, 已满足的条目下标集合)"""
    lines = text.splitlines(keepends=True)
    by_orig = {}
    for ei, e in enumerate(entries):
        by_orig.setdefault(e["original"], []).append(ei)
    satisfied = set()
    for i, line in enumerate(lines):
        body = line.rstrip("\r\n")
        s = body.strip()
        if s and s in by_orig:
            eol = "\r\n" if line.endswith("\r\n") else ("\n" if line.endswith("\n") else "")
            lead = body[:len(body) - len(body.lstrip())]
            ei = by_orig[s][0]
            lines[i] = lead + entries[ei]["translation"] + eol
            satisfied.update(by_orig[s])
    return "".join(lines), satisfied


def _apply_entries(data: bytes, fname: str, entries: list):
    """对单个文件字节应用条目替换。返回 (新字节, satisfied集合, errors)。
    按条目类型路由（文件夹场景只传得到 basename，路径规则不可靠）：
    shader_lang -> *.lang 键值对；txt_line -> texts/*.txt 整行；其余 -> JSON。
    文件级失败(无法解析等)抛 ValueError。"""
    text, enc = _decode_bytes(data)
    n = _norm(fname).lower()
    typ0 = entries[0]["type"] if entries else ""
    if n.endswith(".lang") or typ0 == "shader_lang":
        out, satisfied = _apply_properties(text, entries)
    elif typ0 == "txt_line":
        out, satisfied = _apply_txt(text, entries)
    else:
        out, satisfied = _apply_json(text, entries)
    return _encode_bytes(out, enc), satisfied, []


def _write_folder_file(path: str, entries: list):
    """写回单个文件夹内的文件（自动 .bak）。返回 (成功数, 错误列表)"""
    try:
        with open(path, "rb") as f:
            data = f.read()
        new_data, satisfied, errs = _apply_entries(data, os.path.basename(path), entries)
    except ValueError as e:
        return 0, [f"文件 {os.path.basename(path)} 处理失败: {e}"]
    except Exception as e:
        return 0, [f"文件 {os.path.basename(path)} 读取失败: {e}"]
    if satisfied:
        bak = path + ".bak"
        if os.path.exists(bak):
            os.remove(bak)
        shutil.copy2(path, bak)
        with open(path, "wb") as f:
            f.write(new_data)
    for ei in range(len(entries)):
        if ei not in satisfied:
            orig = entries[ei].get("original", "")
            key = entries[ei].get("key", "")
            errs.append(f"未找到原文 '{orig[:60]}' (键: {key or '—'})")
    return len(satisfied), errs


def _write_zip(zip_path: str, changes: dict):
    """写回 zip 内若干条目（自动整体 .bak），未改动条目保持原压缩方式。
    changes: {inner: [entries]}。返回 (成功数, 错误列表)"""
    errors = []
    new_data_map = {}
    total_ok = 0
    for inner, entries in changes.items():
        try:
            with zipfile.ZipFile(zip_path) as zf:
                data = zf.read(inner)
            new_data, satisfied, _errs = _apply_entries(data, inner, entries)
            for ei in range(len(entries)):
                if ei not in satisfied:
                    orig = entries[ei].get("original", "")
                    key = entries[ei].get("key", "")
                    errors.append(f"未找到原文 '{orig[:60]}' (键: {key or '—'})")
            total_ok += len(satisfied)
            new_data_map[inner] = new_data
        except KeyError:
            errors.append(f"zip 内找不到文件: {inner}")
        except ValueError as e:
            errors.append(f"{inner} 处理失败: {e}")
        except Exception as e:
            errors.append(f"{inner} 处理失败: {e}")
    if not new_data_map:
        return total_ok, errors
    bak = zip_path + ".bak"
    if os.path.exists(bak):
        os.remove(bak)
    shutil.copy2(zip_path, bak)
    tmp = zip_path + ".tmp"
    try:
        with zipfile.ZipFile(zip_path, "r") as zin, \
                zipfile.ZipFile(tmp, "w") as zout:
            for info in zin.infolist():
                data = zin.read(info)
                if info.filename in new_data_map:
                    data = new_data_map[info.filename]
                zout.writestr(info, data)
        os.replace(tmp, zip_path)
    except Exception as e:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
        errors.append(f"重建 zip 失败: {e}")
    return total_ok, errors


def write_translations(translations: list, progress=None, stop_flag=None) -> dict:
    """
    写回译文到材质包/光影包（文件夹或 zip 均可）。
    translations: [{original, translation, location, type, key}, ...]
    progress(cur, total, msg)；stop_flag() -> bool。
    返回 {"success_count","error_count","total_count","errors":[...]}
    """
    results = {"success_count": 0, "error_count": 0, "total_count": 0, "errors": []}
    zip_groups = {}      # zip路径 -> {inner: [entries]}
    folder_groups = {}   # 文件路径 -> [entries]
    for tr in translations:
        original = tr.get("original", "")
        translated = tr.get("translation", "")
        location = tr.get("location", "")
        if not original or not translated or original == translated or not location:
            continue
        entry = {
            "original": original,
            "translation": translated,
            "type": tr.get("type", ""),
            "key": tr.get("key", ""),
        }
        container, inner, is_zip = split_location(location)
        if is_zip:
            zip_groups.setdefault(container, {}).setdefault(inner, []).append(entry)
        else:
            folder_groups.setdefault(container, []).append(entry)

    total_ok = 0
    total_err = 0
    tasks = []
    for path, entries in folder_groups.items():
        tasks.append((path, None, entries))
    for zpath, changes in zip_groups.items():
        tasks.append((zpath, changes, None))
    total_tasks = len(tasks)
    for i, (path, changes, entries) in enumerate(tasks):
        if stop_flag is not None and stop_flag():
            break
        name = os.path.basename(path)
        if progress is not None:
            progress(i + 1, total_tasks, f"写回: {name}")
        try:
            if changes is not None:
                ok, errs = _write_zip(path, changes)
            else:
                ok, errs = _write_folder_file(path, entries)
            total_ok += ok
            total_err += len(errs)
            results["errors"].extend(errs)
        except Exception as e:
            total_err += 1
            results["errors"].append(f"写回 {path} 失败: {e}")
    results["success_count"] = total_ok
    results["error_count"] = total_err
    results["total_count"] = total_ok + total_err
    return results


# ---------------------------------------------------------------------------
# 备份管理
# ---------------------------------------------------------------------------
def find_backups(source: str):
    """返回 [(bak_path, original_path), ...]。文件夹：递归 *.bak；zip/jar：source+'.bak'"""
    if not source:
        return []
    if _is_archive(source):
        bak = source + ".bak"
        return [(bak, source)] if os.path.exists(bak) else []
    if os.path.isdir(source):
        found = []
        for root, _, files in os.walk(source):
            for f in files:
                if f.endswith(".bak"):
                    p = os.path.join(root, f)
                    found.append((p, p[:-4]))
        return found
    return []


def restore_backups(source: str):
    """用 .bak 覆盖当前文件。返回 (成功数, 失败数, 消息列表)"""
    ok = fail = 0
    msgs = []
    for bak, orig in find_backups(source):
        try:
            shutil.copy2(bak, orig)
            ok += 1
            msgs.append(f"已恢复: {os.path.basename(orig)}")
        except Exception as e:
            fail += 1
            msgs.append(f"恢复失败 {orig}: {e}")
    return ok, fail, msgs


def delete_backups(source: str):
    """删除所有备份。返回 (成功数, 失败数, 消息列表)"""
    ok = fail = 0
    msgs = []
    for bak, _orig in find_backups(source):
        try:
            os.remove(bak)
            ok += 1
        except Exception as e:
            fail += 1
            msgs.append(f"删除失败 {bak}: {e}")
    return ok, fail, msgs


# ---------------------------------------------------------------------------
# 元数据提取（详情卡片：名称 / 版本 / 描述 / 图标）
# ---------------------------------------------------------------------------
def _display_base_name(source: str) -> str:
    b = os.path.basename(os.path.normpath(source))
    if b.lower().endswith((".zip", ".jar")):
        b = os.path.splitext(b)[0]
    return b


def _collect_json_texts(data, out: list):
    """递归收集 JSON 文本组件里的 text 字符串"""
    if isinstance(data, dict):
        if isinstance(data.get("text"), str):
            out.append(data["text"])
        for v in data.values():
            _collect_json_texts(v, out)
    elif isinstance(data, list):
        for v in data:
            _collect_json_texts(v, out)


def _parse_pack_mcmeta(data: bytes) -> dict:
    out = {"name": "", "description": "", "version": ""}
    try:
        obj = json.loads(data.decode("utf-8-sig", errors="replace"))
        pack = obj.get("pack", {}) if isinstance(obj, dict) else {}
        desc = pack.get("description", "")
        if isinstance(desc, (dict, list)):
            texts = []
            _collect_json_texts(desc, texts)
            desc = " ".join(t for t in texts if t)
        out["description"] = str(desc).strip()
        pf = pack.get("pack_format")
        if pf is not None:
            v = PACK_FORMAT_VERSIONS.get(int(pf))
            out["version"] = f"pack_format {pf}" + (f"（{v}）" if v else "")
        elif pack.get("min_format") is not None and pack.get("max_format") is not None:
            out["version"] = f"pack_format {pack['min_format']} – {pack['max_format']}"
    except Exception:
        pass
    return out


def _zip_read(zf):
    names = set(zf.namelist())

    def read(inner: str):
        return zf.read(inner) if inner in names else None
    return read


def _dir_read(source: str):
    def read(inner: str):
        p = os.path.join(source, *inner.split("/"))
        if os.path.exists(p):
            try:
                with open(p, "rb") as f:
                    return f.read()
            except Exception:
                return None
        return None
    return read


def extract_pack_meta(source: str, kind="resource") -> dict:
    """提取材质包/光影包展示信息：{name, description, version, icon_bytes, icon_fmt}"""
    meta = {"name": "", "description": "", "version": "",
            "icon_bytes": None, "icon_fmt": "", "icon_inner": ""}
    try:
        if _is_archive(source):
            with zipfile.ZipFile(source) as zf:
                names = set(zf.namelist())
                if "pack.mcmeta" in names:
                    meta.update(_parse_pack_mcmeta(zf.read("pack.mcmeta")))
                if "pack.png" in names:
                    meta["icon_bytes"] = zf.read("pack.png")
                    meta["icon_fmt"] = "png"
                    meta["icon_inner"] = "pack.png"
        elif os.path.isdir(source):
            p = os.path.join(source, "pack.mcmeta")
            if os.path.exists(p):
                with open(p, "rb") as f:
                    meta.update(_parse_pack_mcmeta(f.read()))
            ip = os.path.join(source, "pack.png")
            if os.path.exists(ip):
                with open(ip, "rb") as f:
                    meta["icon_bytes"] = f.read()
                    meta["icon_fmt"] = "png"
    except Exception as e:
        get_logger().debug(f"读取包元数据失败: {e}")
    if not meta.get("name"):
        meta["name"] = _display_base_name(source)
    return meta


def _parse_fabric_mod(read) -> dict:
    raw = read("fabric.mod.json")
    if raw is None:
        return {}
    obj = json.loads(raw.decode("utf-8", errors="replace"))
    out = {}
    out["name"] = str(obj.get("name") or obj.get("id") or "")
    out["version"] = str(obj.get("version") or "")
    dep = obj.get("depends", {}).get("minecraft")
    if dep:
        if isinstance(dep, list):
            dep = ", ".join(str(d) for d in dep)
        out["version"] = (out["version"] + "  ·  MC " + str(dep)).strip(" ·")
    desc = obj.get("description")
    out["description"] = str(desc).strip() if desc else ""
    icon = obj.get("icon")
    if isinstance(icon, dict):
        icon = icon.get("default", "")
    if isinstance(icon, str) and icon:
        ib = read(icon)
        if ib is not None:
            out["icon_bytes"] = ib
            out["icon_fmt"] = icon.rsplit(".", 1)[-1].lower()
            out["icon_inner"] = icon
    return out


def _rough_toml(text: str) -> dict:
    """无 tomllib 时的极简 TOML 解析：仅取 [[mods]] / [dependencies.minecraft] 常见键"""
    obj = {"mods": [], "dependencies": {"minecraft": []}}
    cur_mod = None
    cur_dep = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[[mods]]"):
            cur_mod = {}
            obj["mods"].append(cur_mod)
            cur_dep = None
            continue
        if line.startswith("[[dependencies.minecraft]]"):
            cur_dep = {}
            obj["dependencies"]["minecraft"].append(cur_dep)
            cur_mod = None
            continue
        if "=" in line:
            k, _, v = line.partition("=")
            k = k.strip()
            v = v.strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in ('"', "'"):
                v = v[1:-1]
            if cur_dep is not None:
                cur_dep[k] = v
            elif cur_mod is not None:
                cur_mod[k] = v
            else:
                obj[k] = v
    return obj


def _parse_mods_toml(read) -> dict:
    raw = read("META-INF/mods.toml")
    if raw is None:
        return {}
    text = raw.decode("utf-8", errors="replace")
    try:
        import tomllib
        obj = tomllib.loads(text)
    except Exception:
        obj = _rough_toml(text)
    out = {}
    mods = obj.get("mods") or []
    first = mods[0] if mods else {}
    out["name"] = str(first.get("displayName") or first.get("modId") or "")
    out["version"] = str(first.get("version") or obj.get("version") or "")
    ranges = []
    deps = obj.get("dependencies", {}).get("minecraft") or []
    for d in deps:
        if isinstance(d, dict) and d.get("versionRange"):
            ranges.append(str(d["versionRange"]))
    if ranges:
        out["version"] = (out["version"] + "  ·  MC " + ", ".join(ranges)).strip(" ·")
    out["description"] = str(first.get("description") or obj.get("description") or "")
    logo = first.get("logoFile") or obj.get("logoFile")
    if logo:
        ib = read(str(logo))
        if ib is not None:
            out["icon_bytes"] = ib
            out["icon_fmt"] = str(logo).rsplit(".", 1)[-1].lower()
            out["icon_inner"] = str(logo)
    return out


def _parse_mcmod_info(read) -> dict:
    raw = read("mcmod.info")
    if raw is None:
        return {}
    arr = json.loads(raw.decode("utf-8", errors="replace"))
    out = {}
    if isinstance(arr, list) and arr:
        first = arr[0]
        out["name"] = str(first.get("name") or first.get("modid") or "")
        out["version"] = str(first.get("version") or "")
        out["description"] = str(first.get("description") or "")
        logo = first.get("logoFile")
        if logo:
            ib = read(str(logo))
            if ib is not None:
                out["icon_bytes"] = ib
                out["icon_fmt"] = str(logo).rsplit(".", 1)[-1].lower()
                out["icon_inner"] = str(logo)
    return out


def extract_mod_meta(source: str) -> dict:
    """从 Mod（jar/zip 或解压文件夹）提取展示信息：{name, version, description, icon_bytes}"""
    meta = {"name": _display_base_name(source), "description": "", "version": "",
            "icon_bytes": None, "icon_fmt": "", "icon_inner": ""}
    try:
        if _is_archive(source):
            with zipfile.ZipFile(source) as zf:
                names = set(zf.namelist())
                read = _zip_read(zf)
                if "fabric.mod.json" in names:
                    meta.update(_parse_fabric_mod(read))
                elif "META-INF/mods.toml" in names:
                    meta.update(_parse_mods_toml(read))
                elif "mcmod.info" in names:
                    meta.update(_parse_mcmod_info(read))
        elif os.path.isdir(source):
            read = _dir_read(source)
            if os.path.exists(os.path.join(source, "fabric.mod.json")):
                meta.update(_parse_fabric_mod(read))
            elif os.path.exists(os.path.join(source, "META-INF", "mods.toml")):
                meta.update(_parse_mods_toml(read))
            elif os.path.exists(os.path.join(source, "mcmod.info")):
                meta.update(_parse_mcmod_info(read))
    except Exception as e:
        get_logger().debug(f"读取 mod 元数据失败: {e}")
    return meta
