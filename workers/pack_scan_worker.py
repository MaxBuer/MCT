# -*- coding: utf-8 -*-
"""
材质包 / 光影包 扫描工作线程 - Pack Scan Worker Thread
"""

from PyQt6.QtCore import QThread, pyqtSignal

from utils.logger import get_logger
from utils import pack_helper


class PackScanWorker(QThread):
    """扫描材质包/光影包（文件夹或 zip）内的可翻译文本"""

    progress_updated = pyqtSignal(int, int, str)
    scan_finished = pyqtSignal(list)
    error_occurred = pyqtSignal(str)

    def __init__(self, pack_path: str, scan_lang=True, scan_texts=True,
                 scan_json=True, scan_mcmeta=True):
        super().__init__()
        self.pack_path = pack_path
        self.scan_lang = scan_lang
        self.scan_texts = scan_texts
        self.scan_json = scan_json
        self.scan_mcmeta = scan_mcmeta
        self.logger = get_logger()
        self.stop_flag = False

    def run(self):
        try:
            results = pack_helper.scan_pack(
                self.pack_path,
                scan_lang=self.scan_lang,
                scan_texts=self.scan_texts,
                scan_json=self.scan_json,
                scan_mcmeta=self.scan_mcmeta,
                progress=self._on_progress,
                stop_flag=lambda: self.stop_flag,
            )
            if self.stop_flag:
                return
            self.scan_finished.emit(results)
            self.logger.info(f"材质包/光影包扫描完成，找到 {len(results)} 条文本")
        except Exception as e:
            self.logger.error(f"材质包/光影包扫描出错: {e}")
            self.error_occurred.emit(f"材质包/光影包扫描出错: {e}")

    def _on_progress(self, cur, total, msg):
        self.progress_updated.emit(cur, total, msg)

    def stop(self):
        self.stop_flag = True
