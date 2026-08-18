# -*- coding: utf-8 -*-
"""
材质包 / 光影包 写回工作线程 - Pack Write Worker Thread
"""

from PyQt6.QtCore import QThread, pyqtSignal

from utils.logger import get_logger
from utils import pack_helper


class PackWriteWorker(QThread):
    """把译文写回材质包/光影包（文件夹或 zip，自动 .bak 备份）"""

    progress_updated = pyqtSignal(int, int, str)
    write_finished = pyqtSignal(dict)
    write_error = pyqtSignal(str)

    def __init__(self, translations: list):
        super().__init__()
        self.translations = translations
        self.logger = get_logger()
        self.stop_flag = False

    def run(self):
        try:
            results = pack_helper.write_translations(
                self.translations,
                progress=self._on_progress,
                stop_flag=lambda: self.stop_flag,
            )
            if self.stop_flag:
                return
            self.write_finished.emit(results)
            self.logger.info(
                f"材质包/光影包写回完成，成功 {results['success_count']}，"
                f"失败 {results['error_count']}")
        except Exception as e:
            self.logger.error(f"材质包/光影包写回出错: {e}")
            self.write_error.emit(f"材质包/光影包写回出错: {e}")

    def _on_progress(self, cur, total, msg):
        self.progress_updated.emit(cur, total, msg)

    def stop(self):
        self.stop_flag = True
