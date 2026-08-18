# -*- coding: utf-8 -*-
"""
MCA 区域文件读写助手 - MCA Region File Helper

Minecraft Java 版 region 文件格式:
  - 8KB 头部: 1024 个 location 条目(4字节: 3字节扇区偏移+1字节扇区数), 后接 1024 个 timestamp 条目
  - 数据区: 每 chunk 以 4 字节长度 + 1 字节压缩类型 + 压缩数据 存储
  - 压缩类型: 1=gzip, 2=zlib, 3=deflate(1.15+)
"""
import os
import io
import re
import json
import zlib
import gzip
import struct
import nbtlib
from nbtlib import File

SECTOR = 4096

# ---------------------------------------------------------------------------
# Java Modified UTF-8 (CESU-8) <-> 标准 UTF-8 双向转换 (NBT 感知)
# Minecraft Java 版 NBT 使用 Java Modified UTF-8: 补充平面字符(U+10000+, 如 emoji)
# 编码为 CESU-8 代理对(6字节: ED A0-BF xx ED B0-BF xx), 而非标准 UTF-8 的 4 字节。
# nbtlib 用标准 UTF-8 解码时会把这些代理对替换成 U+FFFD, 导致 emoji 变乱码。
# 注意: 必须只在 NBT 字符串(tag 8)内部转换, 不能在整个字节流上替换,
#       否则 LongArray/ByteArray 等二进制数据中恰好匹配的字节会被误改。
# ---------------------------------------------------------------------------
_CESU8_PATTERN = re.compile(b'\xed[\xa0-\xaf][\x80-\xbf]\xed[\xb0-\xbf][\x80-\xbf]')

def _cesu8_surrogate_to_utf8_bytes(b: bytes) -> bytes:
    """将 6 字节 CESU-8 代理对转换为 4 字节标准 UTF-8"""
    high = ((b[0] & 0x0F) << 12) | ((b[1] & 0x3F) << 6) | (b[2] & 0x3F)
    low = ((b[3] & 0x0F) << 12) | ((b[4] & 0x3F) << 6) | (b[5] & 0x3F)
    cp = 0x10000 + ((high - 0xD800) << 10) + (low - 0xDC00)
    return bytes([
        0xF0 | ((cp >> 18) & 0x07),
        0x80 | ((cp >> 12) & 0x3F),
        0x80 | ((cp >> 6) & 0x3F),
        0x80 | (cp & 0x3F),
    ])

def _utf8_4byte_to_cesu8(b: bytes) -> bytes:
    """将 4 字节标准 UTF-8 转换为 6 字节 CESU-8 代理对"""
    cp = ((b[0] & 0x07) << 18) | ((b[1] & 0x3F) << 12) | ((b[2] & 0x3F) << 6) | (b[3] & 0x3F)
    if cp < 0x10000:
        return b
    high = 0xD800 + ((cp - 0x10000) >> 10)
    low = 0xDC00 + ((cp - 0x10000) & 0x3FF)
    return bytes([
        0xED, 0xA0 | ((high >> 6) & 0x0F), 0x80 | (high & 0x3F),
        0xED, 0xB0 | ((low >> 6) & 0x0F), 0x80 | (low & 0x3F),
    ])

def _convert_nbt_strings(data: bytes, pos: int, end: int, converter) -> bytes:
    """
    NBT 感知的字节转换器: 递归解析 NBT 二进制结构, 只对 tag 8 (String) 的
    字符串数据部分调用 converter 函数。
    data: 完整 NBT 字节流
    pos: 当前解析位置(指向 tag type 或 compound 内子标签的 type)
    end: 数据结束位置
    converter: 函数 bytes -> bytes, 转换字符串内的字节
    返回: 转换后的字节(从 pos 到 end 的片段)
    """
    result = bytearray()
    i = pos
    while i < end:
        tag_type = data[i]
        i += 1
        if tag_type == 0:  # End
            result.append(0)
            break
        # 读 name (字符串: 2字节长度 + 字节)
        name_len = int.from_bytes(data[i:i+2], 'big')
        i += 2
        name_bytes = data[i:i+name_len]
        i += name_len
        # 转换 name 中的 CESU-8
        name_bytes = converter(name_bytes)
        result.append(tag_type)
        result.extend(len(name_bytes).to_bytes(2, 'big'))
        result.extend(name_bytes)
        # 读 payload
        if tag_type == 1:  # Byte
            result.append(data[i]); i += 1
        elif tag_type == 2:  # Short
            result.extend(data[i:i+2]); i += 2
        elif tag_type == 3:  # Int
            result.extend(data[i:i+4]); i += 4
        elif tag_type == 4:  # Long
            result.extend(data[i:i+8]); i += 8
        elif tag_type == 5:  # Float
            result.extend(data[i:i+4]); i += 4
        elif tag_type == 6:  # Double
            result.extend(data[i:i+8]); i += 8
        elif tag_type == 7:  # ByteArray
            length = int.from_bytes(data[i:i+4], 'big'); i += 4
            result.extend(length.to_bytes(4, 'big'))
            result.extend(data[i:i+length]); i += length
        elif tag_type == 8:  # String
            str_len = int.from_bytes(data[i:i+2], 'big'); i += 2
            str_bytes = data[i:i+str_len]; i += str_len
            str_bytes = converter(str_bytes)
            result.extend(len(str_bytes).to_bytes(2, 'big'))
            result.extend(str_bytes)
        elif tag_type == 9:  # List
            elem_type = data[i]; i += 1
            list_len = int.from_bytes(data[i:i+4], 'big'); i += 4
            result.append(elem_type)
            result.extend(list_len.to_bytes(4, 'big'))
            # 每个元素没有 name, 直接是 payload
            for _ in range(list_len):
                if elem_type == 0:
                    break
                elif elem_type == 1:
                    result.append(data[i]); i += 1
                elif elem_type == 2:
                    result.extend(data[i:i+2]); i += 2
                elif elem_type == 3:
                    result.extend(data[i:i+4]); i += 4
                elif elem_type == 4:
                    result.extend(data[i:i+8]); i += 8
                elif elem_type == 5:
                    result.extend(data[i:i+4]); i += 4
                elif elem_type == 6:
                    result.extend(data[i:i+8]); i += 8
                elif elem_type == 7:
                    blen = int.from_bytes(data[i:i+4], 'big'); i += 4
                    result.extend(blen.to_bytes(4, 'big'))
                    result.extend(data[i:i+blen]); i += blen
                elif elem_type == 8:
                    slen = int.from_bytes(data[i:i+2], 'big'); i += 2
                    sbytes = data[i:i+slen]; i += slen
                    sbytes = converter(sbytes)
                    result.extend(len(sbytes).to_bytes(2, 'big'))
                    result.extend(sbytes)
                elif elem_type == 9:
                    # 嵌套 list: 需要递归, 但 NBT 中 list of list 极少见
                    # 简化处理: 直接复制原始字节(不转换嵌套 list 中的字符串)
                    # 实际上 list of list 在标准 NBT 中不存在(没有 ListEnd 标记)
                    result.extend(data[i:i+1]); i += 1  # elem_type
                    llen = int.from_bytes(data[i:i+4], 'big'); i += 4
                    result.extend(llen.to_bytes(4, 'big'))
                    # 跳过(无法精确解析)
                    result.extend(data[i:i+1])  # 至少复制一个字节
                    i += 1
                elif elem_type == 10:
                    # List of Compound: 递归解析每个 compound
                    # 找到 compound 的结束位置
                    comp_start = i
                    # 解析一个 compound 来获取长度
                    conv, new_i = _convert_compound(data, i, converter)
                    result.extend(conv)
                    i = new_i
                elif elem_type == 11:
                    ilen = int.from_bytes(data[i:i+4], 'big'); i += 4
                    result.extend(ilen.to_bytes(4, 'big'))
                    result.extend(data[i:i+ilen*4]); i += ilen*4
                elif elem_type == 12:
                    llen = int.from_bytes(data[i:i+4], 'big'); i += 4
                    result.extend(llen.to_bytes(4, 'big'))
                    result.extend(data[i:i+llen*8]); i += llen*8
                else:
                    # 未知类型, 中断
                    i = end
        elif tag_type == 10:  # Compound
            conv, new_i = _convert_compound(data, i, converter)
            result.extend(conv)
            i = new_i
        elif tag_type == 11:  # IntArray
            length = int.from_bytes(data[i:i+4], 'big'); i += 4
            result.extend(length.to_bytes(4, 'big'))
            result.extend(data[i:i+length*4]); i += length*4
        elif tag_type == 12:  # LongArray
            length = int.from_bytes(data[i:i+4], 'big'); i += 4
            result.extend(length.to_bytes(4, 'big'))
            result.extend(data[i:i+length*8]); i += length*8
        else:
            # 未知 tag, 停止
            break
    return bytes(result)

def _convert_compound(data: bytes, pos: int, converter) -> tuple:
    """
    解析 NBT Compound (从第一个子标签的 type 开始), 转换其中的字符串。
    返回 (转换后的字节, 结束位置)
    """
    result = bytearray()
    i = pos
    while i < len(data):
        tag_type = data[i]
        i += 1
        result.append(tag_type)
        if tag_type == 0:  # End
            break
        # name
        name_len = int.from_bytes(data[i:i+2], 'big')
        i += 2
        name_bytes = data[i:i+name_len]
        i += name_len
        name_bytes = converter(name_bytes)
        result.extend(len(name_bytes).to_bytes(2, 'big'))
        result.extend(name_bytes)
        # payload
        if tag_type == 1:
            result.append(data[i]); i += 1
        elif tag_type == 2:
            result.extend(data[i:i+2]); i += 2
        elif tag_type == 3:
            result.extend(data[i:i+4]); i += 4
        elif tag_type == 4:
            result.extend(data[i:i+8]); i += 8
        elif tag_type == 5:
            result.extend(data[i:i+4]); i += 4
        elif tag_type == 6:
            result.extend(data[i:i+8]); i += 8
        elif tag_type == 7:
            length = int.from_bytes(data[i:i+4], 'big'); i += 4
            result.extend(length.to_bytes(4, 'big'))
            result.extend(data[i:i+length]); i += length
        elif tag_type == 8:
            str_len = int.from_bytes(data[i:i+2], 'big'); i += 2
            str_bytes = data[i:i+str_len]; i += str_len
            str_bytes = converter(str_bytes)
            result.extend(len(str_bytes).to_bytes(2, 'big'))
            result.extend(str_bytes)
        elif tag_type == 9:
            elem_type = data[i]; i += 1
            list_len = int.from_bytes(data[i:i+4], 'big'); i += 4
            result.append(elem_type)
            result.extend(list_len.to_bytes(4, 'big'))
            for _ in range(list_len):
                if elem_type == 0:
                    break
                elif elem_type == 1:
                    result.append(data[i]); i += 1
                elif elem_type == 2:
                    result.extend(data[i:i+2]); i += 2
                elif elem_type == 3:
                    result.extend(data[i:i+4]); i += 4
                elif elem_type == 4:
                    result.extend(data[i:i+8]); i += 8
                elif elem_type == 5:
                    result.extend(data[i:i+4]); i += 4
                elif elem_type == 6:
                    result.extend(data[i:i+8]); i += 8
                elif elem_type == 7:
                    blen = int.from_bytes(data[i:i+4], 'big'); i += 4
                    result.extend(blen.to_bytes(4, 'big'))
                    result.extend(data[i:i+blen]); i += blen
                elif elem_type == 8:
                    slen = int.from_bytes(data[i:i+2], 'big'); i += 2
                    sbytes = data[i:i+slen]; i += slen
                    sbytes = converter(sbytes)
                    result.extend(len(sbytes).to_bytes(2, 'big'))
                    result.extend(sbytes)
                elif elem_type == 10:
                    conv, new_i = _convert_compound(data, i, converter)
                    result.extend(conv)
                    i = new_i
                elif elem_type == 11:
                    ilen = int.from_bytes(data[i:i+4], 'big'); i += 4
                    result.extend(ilen.to_bytes(4, 'big'))
                    result.extend(data[i:i+ilen*4]); i += ilen*4
                elif elem_type == 12:
                    llen = int.from_bytes(data[i:i+4], 'big'); i += 4
                    result.extend(llen.to_bytes(4, 'big'))
                    result.extend(data[i:i+llen*8]); i += llen*8
                else:
                    i = len(data)
        elif tag_type == 10:
            conv, new_i = _convert_compound(data, i, converter)
            result.extend(conv)
            i = new_i
        elif tag_type == 11:
            length = int.from_bytes(data[i:i+4], 'big'); i += 4
            result.extend(length.to_bytes(4, 'big'))
            result.extend(data[i:i+length*4]); i += length*4
        elif tag_type == 12:
            length = int.from_bytes(data[i:i+4], 'big'); i += 4
            result.extend(length.to_bytes(4, 'big'))
            result.extend(data[i:i+length*8]); i += length*8
        else:
            break
    return bytes(result), i

def _cesu8_to_utf8(data: bytes) -> bytes:
    """将 NBT 字节流中字符串内的 CESU-8 代理对转换为标准 UTF-8"""
    if not data:
        return data
    # NBT 根: 第一个字节是 root tag type (通常是 10 Compound), 然后是 name, 然后 payload
    # 跳过 root tag type 和 name, 直接解析 compound payload
    root_type = data[0]
    pos = 1
    name_len = int.from_bytes(data[pos:pos+2], 'big')
    pos += 2 + name_len
    if root_type == 10:
        converted, _ = _convert_compound(data, pos, lambda s: _CESU8_PATTERN.sub(
            lambda m: _cesu8_surrogate_to_utf8_bytes(m.group()), s))
        return data[:pos] + converted
    else:
        # 其他根类型, 用通用解析
        converted = _convert_nbt_strings(data, 0, len(data), lambda s: _CESU8_PATTERN.sub(
            lambda m: _cesu8_surrogate_to_utf8_bytes(m.group()), s))
        return converted

_UTF8_4BYTE_PATTERN = re.compile(b'[\xf0-\xf4][\x80-\xbf][\x80-\xbf][\x80-\xbf]')

def _utf8_to_cesu8(data: bytes) -> bytes:
    """将 NBT 字节流中字符串内的标准 UTF-8 4 字节补充字符转回 CESU-8 代理对"""
    if not data:
        return data
    root_type = data[0]
    pos = 1
    name_len = int.from_bytes(data[pos:pos+2], 'big')
    pos += 2 + name_len
    if root_type == 10:
        converted, _ = _convert_compound(data, pos, lambda s: _UTF8_4BYTE_PATTERN.sub(
            lambda m: _utf8_4byte_to_cesu8(m.group()), s))
        return data[:pos] + converted
    else:
        converted = _convert_nbt_strings(data, 0, len(data), lambda s: _UTF8_4BYTE_PATTERN.sub(
            lambda m: _utf8_4byte_to_cesu8(m.group()), s))
        return converted

def _decompress(ctype: int, chunk_data: bytes) -> bytes:
    """按压缩类型解压 chunk 数据"""
    try:
        if ctype == 1:
            return gzip.decompress(chunk_data)
        if ctype == 2:
            return zlib.decompress(chunk_data)
        if ctype == 3:
            return zlib.decompress(chunk_data, -zlib.MAX_WBITS)
        return chunk_data
    except Exception:
        return None

def _compress(raw: bytes, ctype: int = 2) -> bytes:
    """压缩 chunk 数据(默认 zlib)"""
    if ctype == 1:
        return gzip.compress(raw)
    if ctype == 3:
        co = zlib.compressobj(level=6, wbits=-zlib.MAX_WBITS)
        return co.compress(raw) + co.flush()
    return zlib.compress(raw)

def _find_json_end(s: str, start: int) -> int:
    """从 start(指向 { 或 [) 找到括号配平的 JSON 结束位置(不含), 找不到返回 -1"""
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(s)):
        c = s[i]
        if in_str:
            if esc:
                esc = False
            elif c == '\\':
                esc = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c in '{[':
            depth += 1
        elif c in '}]':
            depth -= 1
            if depth == 0:
                return i + 1
    return -1

def iter_json_components(text: str):
    """
    迭代字符串中所有配平且可解析的 JSON 对象/数组组件。
    返回 (start, end, obj); 嵌套组件会被外层组件覆盖(不重复返回)。
    用于从 minecraft 命令字符串中提取 tellraw/title 等命令的 JSON 文本组件。
    """
    covered = -1
    for start, c in enumerate(text):
        if c not in '{[':
            continue
        if start < covered:
            continue
        end = _find_json_end(text, start)
        if end < 0:
            continue
        try:
            obj = json.loads(text[start:end])
        except Exception:
            continue
        covered = end
        yield start, end, obj

def load_mca(path: str):
    """
    解析 .mca 文件。
    返回:
      chunks: list[(index, nbt_File_or_None)] 按 index 排序
      info: dict, 记录每个 index 的原始字节布局 (offset, sector_count, data_start, length, ctype, raw_decompressed)
    """
    with open(path, 'rb') as f:
        data = f.read()

    chunks = []
    info = {}
    # 空文件 / 不足 8KB 头部的占位文件: 直接返回空(无 chunk)
    if len(data) < 8192:
        for i in range(1024):
            chunks.append((i, None))
            info[i] = None
        return chunks, info

    for i in range(1024):
        loc = data[i*4:(i+1)*4]
        offset = int.from_bytes(loc[:3], 'big')
        sector_count = loc[3]
        if offset == 0 or sector_count == 0:
            chunks.append((i, None))
            info[i] = None
            continue
        data_start = offset * SECTOR
        if data_start + 5 > len(data):
            chunks.append((i, None))
            info[i] = None
            continue
        length = int.from_bytes(data[data_start:data_start+4], 'big')
        ctype = data[data_start+4]
        chunk_bytes = data[data_start+5:data_start+5+length]
        raw = _decompress(ctype, chunk_bytes)
        nbt = None
        prefix_len = 0
        if raw is not None:
            # 1.21+ 部分 chunk 头部带 DataVersion 前缀(4字节)
            for pfx in (0, 4, 2):
                try:
                    nbt = File.parse(io.BytesIO(raw[pfx:]), byteorder='big')
                    prefix_len = pfx
                    break
                except Exception:
                    continue
            if nbt is not None and prefix_len == 0:
                # 无 DataVersion 前缀, 直接转换整个 raw
                raw = _cesu8_to_utf8(raw)
                nbt = File.parse(io.BytesIO(raw), byteorder='big')
            elif nbt is not None and prefix_len > 0:
                # 有前缀: 只转换 NBT 部分, 保留前缀
                prefix = raw[:prefix_len]
                nbt_part = _cesu8_to_utf8(raw[prefix_len:])
                raw = prefix + nbt_part
                nbt = File.parse(io.BytesIO(raw[prefix_len:]), byteorder='big')
        chunks.append((i, nbt))
        info[i] = {
            'offset': offset, 'sector_count': sector_count,
            'data_start': data_start, 'length': length,
            'ctype': ctype, 'raw': raw, 'prefix_len': prefix_len,
            'timestamp': int.from_bytes(data[4096+i*4:4096+i*4+4], 'big'),
            'compressed': chunk_bytes,
        }
    return chunks, info

def _serialize_nbt(nbt) -> bytes:
    buf = io.BytesIO()
    nbt.write(buf)
    return buf.getvalue()

def save_mca(path: str, chunks, info, compress_ctype: int = 2, modified: set = None) -> bool:
    """
    根据修改后的 chunks 重建 .mca 文件。
    chunks: list[(index, nbt_File_or_None)]
    modified: 需要重新序列化的 index 集合; 不在集合内的 chunk 一律沿用原压缩字节,
              保证未触碰的区块 100% 无损。None 表示全部沿用原始字节(纯重排)。
    """
    if modified is None:
        modified = set()
    # 1) 计算每个 chunk 的新压缩数据
    new_chunk_data = {}   # index -> bytes(含 4字节长度 + 1字节类型 + 压缩数据)
    for i, nbt in chunks:
        inf = info.get(i)
        # 未修改或未解析到的 chunk: 沿用原压缩字节
        if i not in modified or nbt is None:
            if inf is None:
                continue
            payload = inf['compressed']
            ctype = inf['ctype']
            new_chunk_data[i] = struct_len(len(payload)) + bytes([ctype]) + payload
            continue
        raw = _serialize_nbt(nbt)
        # 将标准 UTF-8 4 字节补充字符转回 Java Modified UTF-8 (CESU-8) 代理对
        raw = _utf8_to_cesu8(raw)
        # 若原 chunk 带 DataVersion 前缀, 保留前缀
        prefix = b''
        if inf is not None and inf.get('prefix_len') and inf.get('raw'):
            prefix = inf['raw'][:inf['prefix_len']]
        new_raw = prefix + raw
        payload = _compress(new_raw, compress_ctype)
        new_chunk_data[i] = struct_len(len(payload)) + bytes([compress_ctype]) + payload

    # 2) 重建文件 (数据区从 8KB 头部之后开始, 即第 2 个扇区)
    header_locations = bytearray(4096)
    header_timestamps = bytearray(4096)
    body = bytearray()
    body_size = 2 * SECTOR   # 跳过 8KB 头部
    used = {}

    # 先处理所有 index, 分配扇区
    # 对于未修改且位置靠前的 chunk, 尽量保持原位(减少文件变化)
    # 简化策略: 全部按序追加到 body, 更新 header
    for i in range(1024):
        if i not in new_chunk_data:
            continue
        chunk_bytes = new_chunk_data[i]
        sectors = (len(chunk_bytes) + SECTOR - 1) // SECTOR
        # 追加到 body
        offset_sector = body_size // SECTOR
        # 对齐
        pad = (SECTOR - (body_size % SECTOR)) % SECTOR
        body.extend(b'\x00' * pad)
        body_size += pad
        offset_sector = body_size // SECTOR
        body.extend(chunk_bytes)
        body.extend(b'\x00' * (sectors * SECTOR - len(chunk_bytes)))
        body_size += sectors * SECTOR
        used[i] = (offset_sector, sectors)

    # 写 header
    for i in range(1024):
        if i in used:
            off, sec = used[i]
            header_locations[i*4:i*4+3] = off.to_bytes(3, 'big')
            header_locations[i*4+3] = sec
            # 保留原 timestamp
            if info.get(i) is not None:
                header_timestamps[i*4:i*4+4] = info[i]['timestamp'].to_bytes(4, 'big')
        # else: 0 表示无 chunk

    out = bytes(header_locations) + bytes(header_timestamps) + bytes(body)
    # 写回(带 .bak 备份由调用方处理)
    tmp = path + '.tmp'
    with open(tmp, 'wb') as f:
        f.write(out)
    os.replace(tmp, path)
    return True

def struct_len(n: int) -> bytes:
    return n.to_bytes(4, 'big')
