# -*- coding: utf-8 -*-
"""
写入工作线程 - Write Worker Thread
安全版 + 多线程版：
- 只在白名单字段替换（Command / CustomName / 告示牌text / 书页 / JSON文本组件text）
- 绝不碰 block_states / biomes / Name(方块ID) / Properties / id 等技术字段
- 单文件单遍替换 + 文件级多线程并行
"""

import os
import json
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Tuple, Set

from PyQt6.QtCore import QThread, pyqtSignal

import nbtlib
from nbtlib import File, Compound, List as NBTList, String

from utils.logger import get_logger
from utils.json_validator import validate_json_text
from utils.config import Config
from utils.mca_helper import load_mca, save_mca, iter_json_components


class WriteWorker(QThread):
    """多线程安全写入工作线程"""

    progress_updated = pyqtSignal(int, int, str)
    write_finished = pyqtSignal(dict)
    write_error = pyqtSignal(str)

    def __init__(self, world_path: str, translations: List[Dict[str, Any]],
                 validate_json: bool = True, overwrite_existing: bool = False,
                 max_workers: int = 0):
        super().__init__()
        self.world_path = world_path
        self.translations = translations
        self.validate_json = validate_json
        self.overwrite_existing = overwrite_existing
        self.max_workers = max_workers
        self.logger = get_logger()
        self.config = Config()
        self.stop_flag = False

    def run(self):
        try:
            results = {
                'success_count': 0,
                'error_count': 0,
                'total_count': len(self.translations),
                'errors': [],
                'world_path': self.world_path,
            }
            self.logger.info(f"开始写入 {len(self.translations)} 条翻译到世界文件")

            write_map = self.create_write_map()
            total_files = len(write_map)
            if total_files == 0:
                self.write_finished.emit(results)
                return

            processed = [0]
            lock = threading.Lock()

            def process_file(file_path: str, trans_list: List[Dict]):
                if self.stop_flag:
                    return
                sc, errs = self.write_to_file(file_path, trans_list)
                with lock:
                    results['success_count'] += sc
                    results['error_count'] += len(errs)
                    results['errors'].extend(errs)
                    processed[0] += 1
                    self.progress_updated.emit(
                        processed[0], total_files,
                        f"[{processed[0]}/{total_files}] {os.path.basename(file_path)}"
                    )

            if self.max_workers <= 0:
                cpu = os.cpu_count() or 4
                workers = max(2, min(8, cpu, total_files))
            else:
                workers = max(1, min(self.max_workers, total_files))

            self.logger.info(f"使用 {workers} 个线程并行处理 {total_files} 个文件")

            with ThreadPoolExecutor(max_workers=workers) as ex:
                futures = {ex.submit(process_file, fp, tr): fp
                           for fp, tr in write_map.items()}
                for fut in as_completed(futures):
                    if self.stop_flag:
                        for f in futures:
                            f.cancel()
                        break
                    exc = fut.exception()
                    if exc:
                        fp = futures[fut]
                        with lock:
                            results['error_count'] += len(write_map[fp])
                            results['errors'].append(f"处理文件 {fp} 异常: {exc}")

            self.write_finished.emit(results)
            self.logger.info(
                f"写入完成，成功: {results['success_count']}, 失败: {results['error_count']}")

        except Exception as e:
            self.logger.error(f"写入过程中发生错误: {e}")
            self.write_error.emit(str(e))

    # ------------------------------------------------------------------
    def create_write_map(self) -> Dict[str, List[Dict[str, Any]]]:
        write_map: Dict[str, List[Dict]] = {}
        for translation in self.translations:
            original = translation.get('original', '')
            translated = translation.get('translation', original)
            location = translation.get('location', '')
            if not location or not os.path.exists(location):
                continue
            if not original or original == translated:
                continue
            write_map.setdefault(location, []).append({
                'original': original,
                'translated': translated,
                'type': translation.get('type', 'text'),
            })
        return write_map

    def write_to_file(self, file_path: str, translations: List[Dict[str, Any]]) -> Tuple[int, List[str]]:
        try:
            if file_path.endswith('.dat'):
                return self._write_dat(file_path, translations)
            if file_path.endswith('.mca'):
                return self._write_mca(file_path, translations)
            return 0, [f"不支持的文件类型: {file_path}"]
        except Exception as e:
            return 0, [f"写入文件 {file_path} 失败: {e}"]

    # ------------------------------------------------------------------
    # 按类型分桶
    # ------------------------------------------------------------------
    @staticmethod
    def _bucket(translations: List[Dict[str, Any]]) -> Dict[str, Dict[str, str]]:
        """
        按文本类型分桶，返回 {type: {original: translated}}。
        映射关系：
          command_json / nbt_command -> "command"
          sign_text                   -> "sign"
          entity_name / nbt_customname-> "name"
          book_text                   -> "book"
          text / json_text / nbt_name-> "text"
        """
        buckets = {"command": {}, "sign": {}, "name": {}, "book": {}, "text": {}}
        for tr in translations:
            orig = tr['original']
            trans = tr['translated']
            if not orig or orig == trans:
                continue
            t = tr.get('type', 'text')
            if t in ('command_json', 'nbt_command'):
                buckets["command"][orig] = trans
            elif t == 'sign_text':
                buckets["sign"][orig] = trans
            elif t in ('entity_name', 'nbt_customname'):
                buckets["name"][orig] = trans
            elif t == 'book_text':
                buckets["book"][orig] = trans
            elif t == 'nbt_name':
                # .dat 文件里的 Name 字段（玩家名/实体名），安全
                buckets["name"][orig] = trans
            else:
                # text / json_text / 其他
                buckets["text"][orig] = trans
        return buckets

    # ------------------------------------------------------------------
    # 安全的 NBT 遍历：只在白名单字段替换
    # ------------------------------------------------------------------
    # 绝不替换的路径关键词（技术数据路径）
    TECH_PATH_PARTS = (
        'block_states', 'biomes', 'structures', 'Heightmaps',
        'block_ticks', 'fluid_ticks', 'blending_data', 'PostProcessing',
    )

    def _is_safe_path(self, path: str) -> bool:
        """判断路径是否安全（非技术数据路径）"""
        for part in self.TECH_PATH_PARTS:
            if part in path:
                return False
        return True

    def _walk_and_replace(self, data: Any, repls: Dict[str, Dict[str, str]],
                          hit: Set[str], path: str = "") -> bool:
        """
        白名单字段替换：
        - Command 键: command 桶（JSON组件text替换）
        - CustomName/custom_name 键: name 桶（JSON感知替换）
        - front_text/back_text 下 messages 里的 text 键: sign 桶
        - written_book 路径下的字符串: book 桶
        - 其他 text 键（安全路径）: text 桶
        绝不碰 Name(方块ID)/id/Properties/block_states/biomes 等。
        """
        changed = False
        if isinstance(data, Compound):
            for key, value in list(data.items()):
                cur_path = f"{path}.{key}" if path else key

                if isinstance(value, String):
                    new_val = None
                    hits = set()

                    if key == 'Command' and repls["command"]:
                        new_val, c, hits = self._apply_command(str(value), repls["command"])
                    elif key in ('CustomName', 'custom_name') and repls["name"]:
                        new_val, c, hits = self._apply_name(str(value), repls["name"])
                    elif key == 'text' and repls["sign"] and \
                            ('front_text' in path or 'back_text' in path):
                        new_val, c, hits = self._apply_plain(str(value), repls["sign"])
                    elif key == 'text' and repls["text"] and self._is_safe_path(cur_path):
                        new_val, c, hits = self._apply_plain(str(value), repls["text"])
                    elif repls["book"] and 'written_book' in path:
                        new_val, c, hits = self._apply_plain(str(value), repls["book"])

                    if new_val is not None and c:
                        data[key] = String(new_val)
                        changed = True
                        hit.update(hits)

                elif isinstance(value, (Compound, NBTList)):
                    if self._walk_and_replace(value, repls, hit, cur_path):
                        changed = True

        elif isinstance(data, NBTList):
            for i, item in enumerate(list(data)):
                cur_path = f"{path}[{i}]"
                if isinstance(item, str):
                    # 列表里的纯字符串：成书 pages（旧格式）
                    if repls["book"] and 'written_book' in path:
                        new_val, c, hits = self._apply_plain(str(item), repls["book"])
                        if c:
                            data[i] = String(new_val)
                            changed = True
                            hit.update(hits)
                elif isinstance(item, (Compound, NBTList)):
                    if self._walk_and_replace(item, repls, hit, cur_path):
                        changed = True
        return changed

    # ------------------------------------------------------------------
    # 替换原语
    # ------------------------------------------------------------------
    @staticmethod
    def _apply_plain(value: str, repl: Dict[str, str]) -> Tuple[str, bool, Set[str]]:
        """纯文本多原文替换（用于告示牌文字、书页等）"""
        new_val = value
        hits: Set[str] = set()
        for orig, trans in repl.items():
            if orig in new_val:
                new_val = new_val.replace(orig, trans)
                hits.add(orig)
        return (new_val, True, hits) if hits else (value, False, hits)

    def _apply_name(self, value: str, repl: Dict[str, str]) -> Tuple[str, bool, Set[str]]:
        """CustomName 替换：可能是 JSON 壳（{text:"..."}），JSON感知；否则纯文本"""
        s = value.strip()
        hits: Set[str] = set()
        if (s.startswith('{') or s.startswith('[')) and any(o in value for o in repl):
            try:
                obj = json.loads(value)
                if self._replace_all_in_json(obj, repl, hits):
                    return json.dumps(obj, ensure_ascii=False), True, hits
            except Exception:
                pass
        new_val = value
        for orig, trans in repl.items():
            if orig in new_val:
                new_val = new_val.replace(orig, trans)
                hits.add(orig)
        return (new_val, True, hits) if hits else (value, False, hits)

    def _apply_command(self, command: str, repl: Dict[str, str]) -> Tuple[str, bool, Set[str]]:
        """命令字符串：对每个 JSON 组件的 text 字段替换"""
        hits: Set[str] = set()
        parts = []
        last = 0
        changed = False
        for start, end, obj in iter_json_components(command):
            parts.append(command[last:start])
            if self._replace_all_in_json(obj, repl, hits):
                parts.append(json.dumps(obj, ensure_ascii=False))
                changed = True
            else:
                parts.append(command[start:end])
            last = end
        parts.append(command[last:])
        return (''.join(parts), True, hits) if changed else (command, False, hits)

    def _replace_all_in_json(self, data: Any, repl: Dict[str, str], hits: Set[str]) -> bool:
        """JSON 结构里替换所有 text 字段/字符串元素"""
        changed = False
        if isinstance(data, dict):
            for k, v in data.items():
                if k == 'text' and isinstance(v, str):
                    for orig, trans in repl.items():
                        if orig in v:
                            data[k] = v.replace(orig, trans)
                            changed = True
                            hits.add(orig)
                elif isinstance(v, (dict, list)):
                    if self._replace_all_in_json(v, repl, hits):
                        changed = True
        elif isinstance(data, list):
            for i, item in enumerate(data):
                if isinstance(item, str):
                    for orig, trans in repl.items():
                        if orig in item:
                            data[i] = item.replace(orig, trans)
                            changed = True
                            hits.add(orig)
                elif isinstance(item, (dict, list)):
                    if self._replace_all_in_json(item, repl, hits):
                        changed = True
        return changed

    # ------------------------------------------------------------------
    def _write_dat(self, file_path: str, translations: List[Dict[str, Any]]) -> Tuple[int, List[str]]:
        nbt_file = File.load(file_path, gzipped=True)
        repls = self._bucket(translations)
        hit: Set[str] = set()
        self._walk_and_replace(nbt_file, repls, hit)

        if hit:
            backup_path = file_path + '.bak'
            if os.path.exists(backup_path):
                os.remove(backup_path)
            shutil.move(file_path, backup_path)
            nbt_file.save(file_path)

        all_origs = set()
        for r in repls.values():
            all_origs.update(r.keys())
        errors = [f"未找到原文 '{o[:60]}'" for o in (all_origs - hit)]
        return len(hit), errors

    def _write_mca(self, file_path: str, translations: List[Dict[str, Any]]) -> Tuple[int, List[str]]:
        chunks, info = load_mca(file_path)
        if not chunks:
            return 0, [f"无法解析MCA文件: {file_path}"]

        repls = self._bucket(translations)
        modified_chunks: Set[int] = set()
        hit: Set[str] = set()

        for i, nbt in chunks:
            if nbt is None:
                continue
            if self._walk_and_replace(nbt, repls, hit):
                modified_chunks.add(i)

        if modified_chunks:
            backup_path = file_path + '.bak'
            if os.path.exists(backup_path):
                os.remove(backup_path)
            shutil.copy2(file_path, backup_path)
            save_mca(file_path, chunks, info, modified=modified_chunks)
            self.logger.info(
                f"已回写 {len(modified_chunks)}/{len(chunks)} 个chunk: {os.path.basename(file_path)}")

        all_origs = set()
        for r in repls.values():
            all_origs.update(r.keys())
        errors = [f"未找到原文 '{o[:60]}'" for o in (all_origs - hit)]
        return len(hit), errors

    def stop(self):
        self.stop_flag = True
