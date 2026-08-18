# -*- coding: utf-8 -*-
"""
MCT · Minecraft 地图汉化助手 v2（基于开源项目 MCC-i18n 重构）
功能：
  1. 选择世界存档 → 扫描游戏内对话文本（基于 MCA 真实解析，支持 1.21+）
  2. 文本列表默认全选，可手动勾选决定哪些要汉化；支持正则排除
  3. AI 翻译引擎：本地 Ollama（translategemma:4b）/ 百度通用文本翻译 / 在线 OpenAI 兼容 API
  4. JSON 感知翻译（只译 text，保留 color/bold 等结构）
  5. 写回前自动备份（.bak），支持一键恢复/删除备份
  6. 材质包 / 光影包汉化：扫描 lang/*.json、shader *.lang、texts/*.txt、
     pack.mcmeta 描述与其他 JSON 显示字段（text/title/description 等），支持文件夹或 .zip
"""

import json
import os
import re
import shutil
import sys

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QIcon
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QLineEdit, QComboBox, QCheckBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QProgressBar, QFrame, QStackedWidget,
    QFileDialog, QMessageBox, QTextEdit, QScrollArea, QSizePolicy,
)

from workers.scan_worker import ScanWorker
from workers.write_worker import WriteWorker
from workers.pack_scan_worker import PackScanWorker
from workers.pack_write_worker import PackWriteWorker
from utils.ai_translator import build_translator
from utils.logger import get_logger
from utils.config import Config
from utils import pack_helper

# ---------------------------------------------------------------- 主题

LIGHT_QSS = """
* { font-family: "Microsoft YaHei", "PingFang SC", "Segoe UI", sans-serif; font-size: 13px; }
QMainWindow, QWidget#root { background: #f2f5f7; }
QFrame#card { background: #ffffff; border: 1px solid #e3e9ee; border-radius: 12px; }
QLabel#page_title { font-size: 21px; font-weight: 600; color: #17324d; }
QLabel#hint { color: #6b7f92; font-size: 12px; }
QLabel#stat_num { font-size: 26px; font-weight: 700; color: #0d9c8a; }
QLabel#stat_label { color: #6b7f92; font-size: 12px; }
QPushButton { background: #0d9c8a; color: white; border: none; border-radius: 8px;
              padding: 8px 16px; font-weight: 600; }
QPushButton:hover { background: #0a8576; }
QPushButton:pressed { background: #086d60; }
QPushButton:disabled { background: #b9c4cc; }
QPushButton#ghost { background: transparent; color: #17324d; border: 1px solid #cdd8e0; }
QPushButton#ghost:hover { background: #eef3f6; }
QPushButton#danger { background: #e2574c; }
QPushButton#danger:hover { background: #c94338; }
QLineEdit, QComboBox, QTextEdit { background: #ffffff; border: 1px solid #cdd8e0;
              border-radius: 8px; padding: 7px 10px; color: #17324d; }
QLineEdit:focus, QComboBox:focus, QTextEdit:focus { border: 2px solid #0d9c8a; }
QTableWidget { background: white; border: 1px solid #e3e9ee; border-radius: 10px;
               gridline-color: #eef2f5; }
QTableWidget::item { padding: 4px 6px; }
QTableWidget::item:selected { background: #d9f2ec; color: #17324d; }
QHeaderView::section { background: #f6f9fa; color: #45617a; font-weight: 600;
               border: none; border-bottom: 1px solid #e3e9ee; padding: 8px; }
QProgressBar { background: #e6ecf0; border: none; border-radius: 7px; height: 14px; text-align: center; }
QProgressBar::chunk { background: #0d9c8a; border-radius: 7px; }
QScrollBar:vertical { background: transparent; width: 10px; }
QScrollBar::handle:vertical { background: #c4d0d8; border-radius: 5px; min-height: 30px; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; }
QCheckBox { color: #17324d; }
QCheckBox::indicator { width: 18px; height: 18px; }
QCheckBox::indicator:unchecked { border: 2px solid #b6c2cc; background: white; border-radius: 5px; }
QCheckBox::indicator:checked { border: 2px solid #0d9c8a; background: #0d9c8a; border-radius: 5px; }
QFrame#nav { background: #16324a; border-radius: 14px; }
QFrame#dropzone { border: 2px dashed #b6c2cc; border-radius: 12px; background: #f6f9fa; }
QFrame#dropzone:hover { border-color: #0d9c8a; background: #eef7f5; }
QLabel#nav_title { color: white; font-size: 16px; font-weight: 700; }
QLabel#nav_sub { color: #8fa7ba; font-size: 11px; }
QPushButton#nav_btn { background: transparent; color: #9db4c6; text-align: left;
              padding: 10px 14px; border-radius: 8px; font-weight: 600; }
QPushButton#nav_btn:hover { background: #21415c; color: white; }
QPushButton#nav_btn:checked { background: #0d9c8a; color: white; }
QFrame#stepnum { background: #33506b; color: white; border-radius: 12px; min-width: 24px;
              max-width: 24px; min-height: 24px; max-height: 24px; }
"""

DARK_QSS = """
* { font-family: "Microsoft YaHei", "PingFang SC", "Segoe UI", sans-serif; font-size: 13px; }
QMainWindow, QWidget#root { background: #111a24; }
QFrame#card { background: #1a2530; border: 1px solid #2a3a48; border-radius: 12px; }
QLabel#page_title { font-size: 21px; font-weight: 600; color: #e6eef5; }
QLabel#hint { color: #8aa0b3; font-size: 12px; }
QLabel#stat_num { font-size: 26px; font-weight: 700; color: #34d3bd; }
QLabel#stat_label { color: #8aa0b3; font-size: 12px; }
QPushButton { background: #12b3a0; color: white; border: none; border-radius: 8px;
              padding: 8px 16px; font-weight: 600; }
QPushButton:hover { background: #0fa08e; }
QPushButton:pressed { background: #0c8a7a; }
QPushButton:disabled { background: #3a4a57; }
QPushButton#ghost { background: transparent; color: #d7e2ea; border: 1px solid #3a4a57; }
QPushButton#ghost:hover { background: #22303c; }
QPushButton#danger { background: #e2574c; }
QPushButton#danger:hover { background: #c94338; }
QLineEdit, QComboBox, QTextEdit { background: #141f29; border: 1px solid #3a4a57;
              border-radius: 8px; padding: 7px 10px; color: #e6eef5; }
QLineEdit:focus, QComboBox:focus, QTextEdit:focus { border: 2px solid #12b3a0; }
QTableWidget { background: #141f29; border: 1px solid #2a3a48; border-radius: 10px;
               gridline-color: #22303c; }
QTableWidget::item { padding: 4px 6px; color: #d7e2ea; }
QTableWidget::item:selected { background: #1d4a43; color: white; }
QHeaderView::section { background: #1a2530; color: #9fb4c5; font-weight: 600;
               border: none; border-bottom: 1px solid #2a3a48; padding: 8px; }
QProgressBar { background: #22303c; border: none; border-radius: 7px; height: 14px; text-align: center; }
QProgressBar::chunk { background: #12b3a0; border-radius: 7px; }
QScrollBar:vertical { background: transparent; width: 10px; }
QScrollBar::handle:vertical { background: #3a4a57; border-radius: 5px; min-height: 30px; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; }
QCheckBox { color: #d7e2ea; }
QCheckBox::indicator { width: 18px; height: 18px; }
QCheckBox::indicator:unchecked { border: 2px solid #56697a; background: #141f29; border-radius: 5px; }
QCheckBox::indicator:checked { border: 2px solid #12b3a0; background: #12b3a0; border-radius: 5px; }
QFrame#nav { background: #0d1620; border-radius: 14px; }
QFrame#dropzone { border: 2px dashed #3a4a57; border-radius: 12px; background: #141f29; }
QFrame#dropzone:hover { border-color: #12b3a0; background: #16242f; }
QLabel#nav_title { color: white; font-size: 16px; font-weight: 700; }
QLabel#nav_sub { color: #5f7a8e; font-size: 11px; }
QPushButton#nav_btn { background: transparent; color: #7f97a9; text-align: left;
              padding: 10px 14px; border-radius: 8px; font-weight: 600; }
QPushButton#nav_btn:hover { background: #16242f; color: white; }
QPushButton#nav_btn:checked { background: #12b3a0; color: white; }
QFrame#stepnum { background: #20303e; color: #9fb4c5; border-radius: 12px; min-width: 24px;
              max-width: 24px; min-height: 24px; max-height: 24px; }
"""


# ---------------------------------------------------------------- AI 翻译线程

def _collect_json_text_holders(node, out):
    """递归收集 JSON 中所有含 text 字段的字典节点"""
    if isinstance(node, dict):
        if isinstance(node.get("text"), str):
            out.append(node)
        for v in node.values():
            _collect_json_text_holders(v, out)
    elif isinstance(node, list):
        for v in node:
            _collect_json_text_holders(v, out)


def _is_json_with_text(raw):
    """判断文本是否为含 text 字段的 JSON 结构"""
    try:
        obj = json.loads(raw)
    except Exception:
        return False
    holders = []
    _collect_json_text_holders(obj, holders)
    return bool(holders)


def translate_json_aware(raw, translator):
    """
    对整段 JSON 做"只翻译 text 内容"的处理：
    例如 {"text":"STELMONT","color":"yellow","bold":true} -> 只翻译 STELMONT，
    color/bold 等结构与键名原样保留。
    若 raw 不是 JSON 或无 text 字段则返回 None（由调用方走普通翻译）。
    """
    try:
        obj = json.loads(raw)
    except Exception:
        return None
    if not isinstance(obj, (dict, list)):
        return None
    holders = []
    _collect_json_text_holders(obj, holders)
    if not holders:
        return None
    for h in holders:
        t = h["text"]
        if t and t.strip():
            h["text"] = translator.translate(t)
    return json.dumps(obj, ensure_ascii=False)


class AiTranslateWorker(QThread):
    progress = pyqtSignal(int, int)
    one_done = pyqtSignal(int, str)      # (表格原索引, 译文)
    finished_ok = pyqtSignal(int, int)   # (成功数, 失败数)
    failed = pyqtSignal(str)

    def __init__(self, texts, translator, parent=None):
        super().__init__(parent)
        self.texts = texts          # [(row, original_text, json_flag), ...]
        self.translator = translator
        self.stop_flag = False

    def run(self):
        total = len(self.texts)
        ok = fail = 0
        for i, (row, text, jf) in enumerate(self.texts):
            if self.stop_flag:
                break
            try:
                if jf:
                    translated = translate_json_aware(text, self.translator)
                    if translated is None:
                        translated = self.translator.translate(text)
                else:
                    translated = self.translator.translate(text)
                ok += 1
                self.one_done.emit(row, translated)
            except Exception as e:
                fail += 1
                self.failed.emit(str(e))
            self.progress.emit(i + 1, total)
        self.finished_ok.emit(ok, fail)


# ---------------------------------------------------------------- 工具

def make_label(text, obj="hint"):
    lbl = QLabel(text)
    lbl.setObjectName(obj)
    return lbl


class DropZone(QFrame):
    """拖放区域：接收拖入的文件/文件夹路径（首个 URL）"""

    dropped = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("dropzone")
        self.setAcceptDrops(True)
        self.setMinimumHeight(110)
        lay = QVBoxLayout(self)
        self.drop_label = make_label(
            "将文件拖到此处，自动识别类型：\n"
            "世界存档（文件夹） / 材质包 / 光影包 / Mod (.jar/.zip)\n"
            "识别后点击「开始扫描」")
        self.drop_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.drop_label)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dragMoveEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        urls = e.mimeData().urls()
        if urls:
            p = urls[0].toLocalFile()
            if p:
                self.dropped.emit(p)


# ---------------------------------------------------------------- 页面 1：世界 & 扫描

class ScanPage(QWidget):
    def __init__(self, app_ctx):
        super().__init__()
        self.ctx = app_ctx
        self.worker = None
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 24, 24, 24)
        lay.setSpacing(14)

        self.title_label = QLabel("① 选择世界存档并扫描文本")
        self.title_label.setObjectName("page_title")
        lay.addWidget(self.title_label)

        # 拖放选择区
        self.dropzone = DropZone()
        self.dropzone.dropped.connect(self._on_file_dropped)
        lay.addWidget(self.dropzone)

        # 文件详情卡片（拖入/校验后展示）
        self.details_card = QFrame(); self.details_card.setObjectName("card")
        self.details_card.setVisible(False)
        dl = QHBoxLayout(self.details_card); dl.setContentsMargins(16, 12, 16, 12); dl.setSpacing(14)
        self.detail_icon = QLabel()
        self.detail_icon.setFixedSize(64, 64)
        self.detail_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dl.addWidget(self.detail_icon)
        self.detail_text = make_label("")
        self.detail_text.setTextFormat(Qt.TextFormat.PlainText)
        self.detail_text.setWordWrap(True)
        dl.addWidget(self.detail_text, 1)
        lay.addWidget(self.details_card)

        # 扫描源类型：世界存档 / 材质包·光影包
        mode_card = QFrame(); mode_card.setObjectName("card")
        ml = QHBoxLayout(mode_card); ml.setContentsMargins(16, 12, 16, 12); ml.setSpacing(10)
        ml.addWidget(make_label("扫描源类型"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItems([
            "世界存档（.mca / .dat 对话文本）",
            "材质包 / 光影包 / Mod（文件夹或 .zip/.jar）",
        ])
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        ml.addWidget(self.mode_combo)
        ml.addStretch(1)
        lay.addWidget(mode_card)

        # 路径卡片
        card = QFrame(); card.setObjectName("card")
        cl = QVBoxLayout(card); cl.setContentsMargins(16, 14, 16, 14); cl.setSpacing(10)
        self.path_label = make_label("世界存档文件夹（包含 level.dat 的目录）")
        cl.addWidget(self.path_label)
        row = QHBoxLayout()
        self.path_edit = QLineEdit(); self.path_edit.setPlaceholderText("例如: E:\\MapTest\\Bayville v10")
        row.addWidget(self.path_edit, 1)
        btn_browse = QPushButton("浏览文件…"); btn_browse.setObjectName("ghost")
        btn_browse.setToolTip("选择 .zip / .jar 文件（材质包、光影包、Mod）")
        btn_browse.clicked.connect(self.browse)
        row.addWidget(btn_browse)
        self.folder_btn = QPushButton("选择文件夹…"); self.folder_btn.setObjectName("ghost")
        self.folder_btn.setToolTip("选择世界存档文件夹或解压后的材质包/光影包/Mod 文件夹")
        self.folder_btn.clicked.connect(self.browse_folder)
        row.addWidget(self.folder_btn)
        self.check_btn = QPushButton("校验世界"); self.check_btn.setObjectName("ghost")
        self.check_btn.clicked.connect(self.check_world)
        row.addWidget(self.check_btn)
        cl.addLayout(row)
        self.check_label = make_label("未校验")
        cl.addWidget(self.check_label)
        lay.addWidget(card)

        # 扫描选项卡片
        card2 = QFrame(); card2.setObjectName("card")
        c2 = QVBoxLayout(card2); c2.setContentsMargins(16, 14, 16, 14); c2.setSpacing(10)
        self.scope_label = make_label("扫描范围（对话文本在 region / entities 里）")
        c2.addWidget(self.scope_label)
        # 世界存档选项
        self.world_opts_widget = QWidget()
        wo = QHBoxLayout(self.world_opts_widget); wo.setContentsMargins(0, 0, 0, 0); wo.setSpacing(12)
        self.cb_region = QCheckBox("区域区块 region (.mca)"); self.cb_region.setChecked(True)
        self.cb_entities = QCheckBox("实体区块 entities (.mca)"); self.cb_entities.setChecked(True)
        self.cb_data = QCheckBox("世界数据 data (.dat)"); self.cb_data.setChecked(True)
        self.cb_player = QCheckBox("玩家数据 playerdata"); self.cb_player.setChecked(False)
        for w in (self.cb_region, self.cb_entities, self.cb_data, self.cb_player):
            wo.addWidget(w)
        c2.addWidget(self.world_opts_widget)
        # 材质包/光影包选项
        self.pack_opts_widget = QWidget()
        po = QHBoxLayout(self.pack_opts_widget); po.setContentsMargins(0, 0, 0, 0); po.setSpacing(12)
        self.cb_pk_lang = QCheckBox("语言文件 lang (*.json / *.lang)"); self.cb_pk_lang.setChecked(True)
        self.cb_pk_texts = QCheckBox("文本文件 texts/*.txt"); self.cb_pk_texts.setChecked(True)
        self.cb_pk_json = QCheckBox("其他 JSON 显示字段 (text/title/…)"); self.cb_pk_json.setChecked(True)
        self.cb_pk_mcmeta = QCheckBox("pack.mcmeta 描述"); self.cb_pk_mcmeta.setChecked(True)
        for w in (self.cb_pk_lang, self.cb_pk_texts, self.cb_pk_json, self.cb_pk_mcmeta):
            po.addWidget(w)
        c2.addWidget(self.pack_opts_widget)
        self.pack_opts_widget.setVisible(False)
        # 开始按钮行
        start_row = QHBoxLayout()
        self.scan_btn = QPushButton("开始扫描")
        self.scan_btn.clicked.connect(self.start_scan)
        start_row.addWidget(self.scan_btn)
        start_row.addStretch(1)
        c2.addLayout(start_row)
        self.scan_progress = QProgressBar(); self.scan_progress.setVisible(False)
        c2.addWidget(self.scan_progress)
        lay.addWidget(card2)

        # 扫描结果统计卡
        card3 = QFrame(); card3.setObjectName("card")
        c3 = QHBoxLayout(card3); c3.setContentsMargins(16, 14, 16, 14); c3.setSpacing(24)
        self.stat_total = make_label("0", "stat_num")
        self.stat_files = make_label("0", "stat_num")
        col1 = QVBoxLayout()
        col1.addWidget(self.stat_total); col1.addWidget(make_label("待汉化文本数"))
        col2 = QVBoxLayout()
        col2.addWidget(self.stat_files); col2.addWidget(make_label("扫描文件数"))
        c3.addLayout(col1); c3.addStretch(1); c3.addLayout(col2); c3.addStretch(2)
        lay.addWidget(card3)

        self.log_text = QTextEdit(); self.log_text.setReadOnly(True)
        self.log_text.setPlaceholderText("扫描日志…")
        self.log_text.setMaximumHeight(150)
        lay.addWidget(self.log_text)

        # 原项目署名
        credit = QLabel(
            '基于开源项目 <a href="https://github.com/BiliBiliACEGE/MCC-i18n" '
            'style="color:#0d9c8a;text-decoration:none;">MCC-i18n</a>'
            '（原作者 BiliBiliACEGE）· GitHub 开源')
        credit.setOpenExternalLinks(True)
        credit.setObjectName("hint")
        lay.addWidget(credit)
        lay.addStretch(1)

    # ---- 行为
    def is_pack_mode(self):
        return self.mode_combo.currentIndex() == 1

    def _on_mode_changed(self, idx=None):
        """切换 世界存档 / 材质包·光影包 模式：更新文案与可见控件"""
        pack = self.is_pack_mode()
        self.title_label.setText(
            "① 选择材质包/光影包并扫描文本" if pack else "① 选择世界存档并扫描文本")
        self.path_label.setText(
            "材质包 / 光影包 / Mod（文件夹 或 .zip/.jar 文件，如 BSL_v8.4.01.2.zip）"
            if pack else "世界存档文件夹（包含 level.dat 的目录）")
        self.path_edit.setPlaceholderText(
            "例如: E:\\MapTest\\BSL_v8.4.01.2.zip" if pack else "例如: E:\\MapTest\\Bayville v10")
        self.check_btn.setText("校验包" if pack else "校验世界")
        self.scope_label.setText(
            "扫描范围（材质包/光影包内的文本类型）" if pack else "扫描范围（对话文本在 region / entities 里）")
        self.world_opts_widget.setVisible(not pack)
        self.pack_opts_widget.setVisible(pack)
        self.check_label.setText("未校验")

    def browse(self):
        """浏览文件：.zip / .jar（材质包、光影包、Mod）"""
        path, _ = QFileDialog.getOpenFileName(
            self, "选择材质包/光影包/Mod (.zip / .jar)", "",
            "材质包/光影包/Mod (*.zip *.jar);;所有文件 (*)")
        if path:
            self._select_source(path)

    def browse_folder(self):
        """选择文件夹：世界存档、解压后的材质包/光影包/Mod"""
        folder = QFileDialog.getExistingDirectory(self, "选择世界存档/材质包/Mod 文件夹")
        if folder:
            self._select_source(folder)

    # ---- 选择/拖入路径：自动识别类型 + 切换模式 + 刷新详情（不自动扫描）
    def _select_source(self, path):
        """选择（拖入/浏览）路径后统一处理：识别类型、切换模式、刷新详情卡片。
        返回 True 表示识别成功并已应用。"""
        path = path.strip().strip('"')
        if not os.path.exists(path):
            QMessageBox.warning(self, "提示", f"路径不存在：\n{path}")
            return False
        from utils.source_detect import detect_source
        kind, meta, msg = detect_source(path)
        if kind == "error":
            self.check_label.setText(f"识别结果: {msg}")
            self.ctx.log(f"选择文件识别失败: {msg}")
            QMessageBox.critical(self, "无法识别", msg)
            return False
        if kind == "unknown":
            self.check_label.setText(f"识别结果: {msg}")
            self.ctx.log(f"选择文件识别: {msg}")
            QMessageBox.information(self, "无法识别", msg + "\n\n仍可手动选择模式后点击「开始扫描」。")
            return False
        if kind == "world_zip":
            self.check_label.setText(f"识别结果: {msg}")
            QMessageBox.information(self, "提示", msg)
            return False
        self.path_edit.setText(path)
        # 切换到对应模式
        if kind == "world":
            self.mode_combo.setCurrentIndex(0)
            self.ctx.scan_mode = "world"
            self.ctx.world_path = path
            self.ctx.pack_path = None
        else:
            self.mode_combo.setCurrentIndex(1)
            self.ctx.scan_mode = "pack"
            self.ctx.pack_path = path
            self.ctx.world_path = None
            # 按类型调整扫描范围默认勾选
            self.cb_pk_lang.setChecked(True)
            self.cb_pk_json.setChecked(True)
            self.cb_pk_texts.setChecked(kind in ("resource", "mixed"))
            self.cb_pk_mcmeta.setChecked(kind in ("resource", "mixed"))
        self.check_label.setText(f"识别结果: {msg}")
        self.ctx.log(f"选择文件识别: {msg}")
        self._show_details(kind, meta)
        return True

    def _on_file_dropped(self, path):
        self._select_source(path)

    def _refresh_details(self, path):
        """校验通过后刷新详情卡片（不切换模式、不自动扫描）"""
        from utils.source_detect import detect_source
        kind, meta, _msg = detect_source(path)
        if kind in ("error", "unknown", "world_zip"):
            self.details_card.setVisible(False)
            return
        self._show_details(kind, meta)

    def _logo_pixmap(self):
        from PyQt6.QtGui import QPixmap
        base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo")
        for name in ("logo.png", "logo.ico", "logo.jpg", "logo.bmp"):
            p = os.path.join(base, name)
            if os.path.exists(p):
                pix = QPixmap(p)
                if not pix.isNull():
                    return pix.scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatio,
                                      Qt.TransformationMode.SmoothTransformation)
        return QPixmap()

    def _show_details(self, kind, meta):
        from PyQt6.QtGui import QPixmap
        type_name = {
            "world": "世界存档 (Java)",
            "resource": "材质包 (Resource Pack)",
            "shader": "光影包 (Shader Pack)",
            "mod": "Mod (模组)",
            "mixed": "材质包 + 光影包",
        }.get(kind, kind)
        name = (meta.get("name") or "").strip() or "—"
        version = (meta.get("version") or "").strip() or "—"
        desc = (meta.get("description") or "").strip()
        lines = [f"类型：{type_name}", f"名称：{name}", f"适用版本：{version}"]
        if desc:
            lines.append(f"描述：{desc[:140]}")
        self.detail_text.setText("\n".join(lines))
        pix = QPixmap()
        icon_bytes = meta.get("icon_bytes")
        if icon_bytes and pix.loadFromData(icon_bytes):
            self.detail_icon.setPixmap(
                pix.scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatio,
                           Qt.TransformationMode.SmoothTransformation))
        else:
            self.detail_icon.setPixmap(self._logo_pixmap())
        self.details_card.setVisible(True)

    def check_world(self):
        if self.is_pack_mode():
            self.check_pack()
            return
        from utils.nbt_helper import validate_world
        path = self.path_edit.text().strip()
        if not os.path.isdir(path):
            QMessageBox.warning(self, "提示", "请先选择有效的世界存档文件夹")
            return
        ok, msg = validate_world(path)
        self.check_label.setText(f"校验结果: {msg}")
        self.ctx.log(f"世界校验: {msg}")
        if ok:
            self._refresh_details(path)

    def check_pack(self):
        path = self.path_edit.text().strip()
        if not os.path.exists(path):
            QMessageBox.warning(self, "提示", "请先选择有效的材质包/光影包/Mod 文件夹或 .zip/.jar 文件")
            return
        kind, msg = pack_helper.detect_pack(path)
        self.check_label.setText(f"校验结果: {msg}")
        self.ctx.log(f"包校验: {msg}")
        if kind not in ("error", "unknown"):
            self._refresh_details(path)

    def start_scan(self):
        path = self.path_edit.text().strip()
        if not os.path.exists(path):
            QMessageBox.warning(self, "提示", "请先选择有效的路径（文件夹或 .zip/.jar）")
            return
        # 若上一次扫描仍在运行，先停止
        if getattr(self, "worker", None) is not None and self.worker.isRunning():
            try:
                self.worker.stop()
                self.worker.wait(1500)
            except Exception:
                pass
        if self.is_pack_mode():
            self._start_pack_scan(path)
            return
        if not os.path.isdir(path):
            QMessageBox.warning(self, "提示", "世界存档必须是文件夹")
            return
        self.ctx.world_path = path
        self.ctx.scan_mode = "world"
        self.scan_btn.setEnabled(False)
        self.scan_progress.setVisible(True); self.scan_progress.setValue(0)
        self.worker = ScanWorker(
            path,
            scan_region=self.cb_region.isChecked(),
            scan_data=self.cb_data.isChecked(),
            scan_entities=self.cb_entities.isChecked(),
            scan_playerdata=self.cb_player.isChecked(),
        )
        self.worker.progress_updated.connect(self.on_progress)
        self.worker.scan_finished.connect(self.on_finished)
        self.worker.error_occurred.connect(self.on_error)
        self.worker.start()
        self.ctx.log("开始扫描…")

    def _start_pack_scan(self, path):
        self.ctx.scan_mode = "pack"
        self.ctx.pack_path = path
        self.scan_btn.setEnabled(False)
        self.scan_progress.setVisible(True); self.scan_progress.setValue(0)
        self.worker = PackScanWorker(
            path,
            scan_lang=self.cb_pk_lang.isChecked(),
            scan_texts=self.cb_pk_texts.isChecked(),
            scan_json=self.cb_pk_json.isChecked(),
            scan_mcmeta=self.cb_pk_mcmeta.isChecked(),
        )
        self.worker.progress_updated.connect(self.on_progress)
        self.worker.scan_finished.connect(self.on_finished)
        self.worker.error_occurred.connect(self.on_error)
        self.worker.start()
        self.ctx.log("开始扫描材质包/光影包…")

    def on_progress(self, cur, total, msg):
        self.scan_progress.setMaximum(max(total, 1)); self.scan_progress.setValue(cur)
        self.ctx.log(msg)

    def on_error(self, msg):
        self.scan_btn.setEnabled(True)
        QMessageBox.critical(self, "扫描出错", msg)
        self.ctx.log(f"错误: {msg}")

    def on_finished(self, results):
        self.scan_btn.setEnabled(True)
        self.ctx.log(f"扫描完成，共 {len(results)} 条原始文本")
        self.ctx.scan_results = results
        self.stat_total.setText(str(len(results)))
        if self.is_pack_mode():
            self.stat_files.setText(str(len({r.get("file", "") for r in results})))
        else:
            self.stat_files.setText("0")
        self.ctx.translate_page.load_scan_results(results)
        self.ctx.goto_page(1)
        QMessageBox.information(self, "扫描完成", f"提取到 {len(results)} 条文本，请到「选择并翻译」页面核对勾选。")


# ---------------------------------------------------------------- 页面 2：选择 & AI 翻译

class TranslatePage(QWidget):
    def __init__(self, app_ctx):
        super().__init__()
        self.ctx = app_ctx
        self.translation_data = []   # 每项含 original/translation/type/count/locations/selected
        self.ai_worker = None
        self.excluded_by_regex = set()   # 被正则排除的 translation_data 索引
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 24, 24, 24)
        lay.setSpacing(12)

        title = QLabel("② 选择要汉化的文本")
        title.setObjectName("page_title")
        lay.addWidget(title)
        lay.addWidget(make_label("默认全部勾选，取消勾选 = 不翻译、不写回。可在此手动微调译文。"))

        # 顶部工具栏
        bar = QFrame(); bar.setObjectName("card")
        bl = QHBoxLayout(bar); bl.setContentsMargins(12, 8, 12, 8); bl.setSpacing(8)
        self.search_edit = QLineEdit(); self.search_edit.setPlaceholderText("搜索原文/译文…")
        self.search_edit.textChanged.connect(self.filter_data)
        bl.addWidget(self.search_edit, 1)
        self.btn_all = QPushButton("全选"); self.btn_all.setObjectName("ghost")
        self.btn_none = QPushButton("全不选"); self.btn_none.setObjectName("ghost")
        self.btn_untrans = QPushButton("仅未翻译"); self.btn_untrans.setObjectName("ghost")
        self.btn_export = QPushButton("导出译文"); self.btn_export.setObjectName("ghost")
        self.btn_import = QPushButton("导入译文"); self.btn_import.setObjectName("ghost")
        self.btn_all.clicked.connect(lambda: self.set_all(True))
        self.btn_none.clicked.connect(lambda: self.set_all(False))
        self.btn_untrans.clicked.connect(self.filter_untranslated)
        self.btn_export.clicked.connect(self.export_data)
        self.btn_import.clicked.connect(self.import_data)
        bl.addWidget(self.btn_all); bl.addWidget(self.btn_none); bl.addWidget(self.btn_untrans)
        bl.addWidget(self.btn_export); bl.addWidget(self.btn_import)
        self.sel_label = make_label("已选 0 项")
        bl.addWidget(self.sel_label)
        lay.addWidget(bar)

        # 正则排除行
        rbar = QFrame(); rbar.setObjectName("card")
        rl = QHBoxLayout(rbar); rl.setContentsMargins(12, 8, 12, 8); rl.setSpacing(8)
        self.regex_edit = QLineEdit()
        self.regex_edit.setPlaceholderText("正则表达式：匹配到的条目自动取消勾选（排除不翻译），例如  �  或  {\"text\":")
        self.regex_edit.returnPressed.connect(self.apply_regex_exclude)
        rl.addWidget(self.regex_edit, 1)
        self.btn_excl = QPushButton("排除匹配"); self.btn_excl.setObjectName("ghost")
        self.btn_excl.clicked.connect(self.apply_regex_exclude)
        rl.addWidget(self.btn_excl)
        self.btn_restore = QPushButton("撤销排除"); self.btn_restore.setObjectName("ghost")
        self.btn_restore.clicked.connect(self.undo_regex_exclude)
        rl.addWidget(self.btn_restore)
        self.regex_status = make_label("")
        rl.addWidget(self.regex_status)
        lay.addWidget(rbar)

        # 表格
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["汉化", "原文", "译文", "类型", "次数"])
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed); self.table.setColumnWidth(0, 56)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setEditTriggers(QTableWidget.EditTrigger.DoubleClicked)
        self.table.cellChanged.connect(self.on_cell_changed)
        lay.addWidget(self.table, 1)

        # AI 设置卡
        ai_card = QFrame(); ai_card.setObjectName("card")
        al = QVBoxLayout(ai_card); al.setContentsMargins(12, 10, 12, 10); al.setSpacing(8)
        head = QHBoxLayout()
        head.addWidget(make_label("AI 翻译引擎", "stat_label"))
        head.addStretch(1)
        self.engine_combo = QComboBox()
        self.engine_combo.addItems([
            "Ollama 本地 (translategemma:4b)",
            "百度翻译（通用文本 API）",
            "在线 API Key (OpenAI 兼容)",
        ])
        self.engine_combo.currentIndexChanged.connect(self.on_engine_changed)
        head.addWidget(self.engine_combo)
        al.addLayout(head)

        grid = QGridLayout(); grid.setHorizontalSpacing(8); grid.setVerticalSpacing(6)
        # Ollama 行
        self.lbl_ollama_url = make_label("Ollama 地址")
        grid.addWidget(self.lbl_ollama_url, 0, 0)
        self.ollama_url = QLineEdit("http://localhost:11434")
        grid.addWidget(self.ollama_url, 0, 1)
        self.lbl_ollama_model = make_label("模型")
        grid.addWidget(self.lbl_ollama_model, 0, 2)
        self.ollama_model = QLineEdit("translategemma:4b")
        grid.addWidget(self.ollama_model, 0, 3)
        # 百度行
        self.lbl_baidu_appid = make_label("百度 APP ID")
        grid.addWidget(self.lbl_baidu_appid, 1, 0)
        self.baidu_appid = QLineEdit()
        self.baidu_appid.setPlaceholderText("fanyi-api.baidu.com 申请的 APP ID")
        grid.addWidget(self.baidu_appid, 1, 1)
        self.lbl_baidu_secret = make_label("百度密钥")
        grid.addWidget(self.lbl_baidu_secret, 1, 2)
        self.baidu_secret = QLineEdit()
        self.baidu_secret.setPlaceholderText("百度翻译开放平台密钥")
        self.baidu_secret.setEchoMode(QLineEdit.EchoMode.Password)
        grid.addWidget(self.baidu_secret, 1, 3)
        # OpenAI 行
        self.lbl_api_url = make_label("API 地址")
        grid.addWidget(self.lbl_api_url, 2, 0)
        self.api_url = QLineEdit("https://api.openai.com/v1")
        grid.addWidget(self.api_url, 2, 1)
        self.lbl_api_key = make_label("API Key")
        grid.addWidget(self.lbl_api_key, 2, 2)
        self.api_key = QLineEdit(); self.api_key.setPlaceholderText("sk-…")
        self.api_key.setEchoMode(QLineEdit.EchoMode.Password)
        grid.addWidget(self.api_key, 2, 3)
        self.lbl_api_model = make_label("模型")
        grid.addWidget(self.lbl_api_model, 3, 0)
        self.api_model = QLineEdit("gpt-4o-mini")
        grid.addWidget(self.api_model, 3, 1)
        al.addLayout(grid)

        btn_row = QHBoxLayout()
        self.test_btn = QPushButton("测试连接"); self.test_btn.setObjectName("ghost")
        self.test_btn.clicked.connect(self.test_conn)
        self.translate_btn = QPushButton("▶ 翻译勾选的未翻译文本")
        self.translate_btn.setObjectName("danger")
        self.translate_btn.clicked.connect(self.start_translate)
        self.stop_btn = QPushButton("停止"); self.stop_btn.setObjectName("ghost")
        self.stop_btn.setEnabled(False); self.stop_btn.clicked.connect(self.stop_translate)
        btn_row.addWidget(self.test_btn)
        btn_row.addWidget(self.translate_btn)
        btn_row.addWidget(self.stop_btn)
        btn_row.addStretch(1)
        al.addLayout(btn_row)
        self.cb_json_only = QCheckBox("JSON 条目只翻译 text 内容（保留 color/bold 等结构，如 {\"text\":\"STELMONT\",\"color\":\"yellow\"} 只译 STELMONT）")
        self.cb_json_only.setChecked(True)
        al.addWidget(self.cb_json_only)
        self.ai_status = make_label("未配置引擎")
        al.addWidget(self.ai_status)
        self.ai_progress = QProgressBar(); self.ai_progress.setVisible(False)
        al.addWidget(self.ai_progress)
        lay.addWidget(ai_card)
        lay.addWidget(make_label("提示：翻译需要本地 Ollama 已运行（ollama serve），或配置有效的在线 API Key。文本量大时建议先小范围勾选验证效果。"))

        self.load_cfg()

    # ---- 配置
    def load_cfg(self):
        c = self.ctx.config
        self.ollama_url.setText(c.get("translation.ollama_url", "http://localhost:11434"))
        self.ollama_model.setText(c.get("translation.ollama_model", "translategemma:4b"))
        self.baidu_appid.setText(c.get("translation.baidu_appid", ""))
        self.baidu_secret.setText(c.get("translation.baidu_secret", ""))
        self.api_url.setText(c.get("translation.api_url", "https://api.openai.com/v1"))
        self.api_key.setText(c.get("translation.api_key", ""))
        self.api_model.setText(c.get("translation.api_model", "gpt-4o-mini"))
        svc = c.get("translation.translation_service", "ollama")
        self.engine_combo.setCurrentIndex({"ollama": 0, "baidu": 1, "openai": 2}.get(svc, 0))
        self.on_engine_changed()

    def save_cfg(self):
        c = self.ctx.config
        c.set("translation.ollama_url", self.ollama_url.text().strip() or "http://localhost:11434")
        c.set("translation.ollama_model", self.ollama_model.text().strip() or "translategemma:4b")
        c.set("translation.baidu_appid", self.baidu_appid.text().strip())
        c.set("translation.baidu_secret", self.baidu_secret.text().strip())
        c.set("translation.api_url", self.api_url.text().strip() or "https://api.openai.com/v1")
        c.set("translation.api_key", self.api_key.text().strip())
        c.set("translation.api_model", self.api_model.text().strip() or "gpt-4o-mini")
        c.set("translation.translation_service",
              {0: "ollama", 1: "baidu", 2: "openai"}[self.engine_combo.currentIndex()])

    def current_engine(self):
        self.save_cfg()
        idx = self.engine_combo.currentIndex()
        if idx == 0:
            return "ollama", {
                "ollama_url": self.ollama_url.text().strip() or "http://localhost:11434",
                "ollama_model": self.ollama_model.text().strip() or "translategemma:4b",
            }
        if idx == 1:
            return "baidu", {
                "baidu_appid": self.baidu_appid.text().strip(),
                "baidu_secret": self.baidu_secret.text().strip(),
                "baidu_from": "en", "baidu_to": "zh",
            }
        return "openai", {
            "api_url": self.api_url.text().strip() or "https://api.openai.com/v1",
            "api_key": self.api_key.text().strip(),
            "api_model": self.api_model.text().strip() or "gpt-4o-mini",
        }

    def on_engine_changed(self):
        idx = self.engine_combo.currentIndex()
        for w in (self.lbl_ollama_url, self.ollama_url,
                  self.lbl_ollama_model, self.ollama_model):
            w.setVisible(idx == 0)
        for w in (self.lbl_baidu_appid, self.baidu_appid,
                  self.lbl_baidu_secret, self.baidu_secret):
            w.setVisible(idx == 1)
        for w in (self.lbl_api_url, self.api_url, self.lbl_api_key, self.api_key,
                  self.lbl_api_model, self.api_model):
            w.setVisible(idx == 2)
        self.ai_status.setText({
            0: "引擎：Ollama 本地（需运行 ollama serve）",
            1: "引擎：百度通用文本翻译（需在 fanyi-api.baidu.com 申请 APP ID 与密钥）",
            2: "引擎：在线 API（OpenAI 兼容，支持 DeepSeek/通义/硅基流动等）",
        }.get(idx, ""))

    # ---- 数据加载
    def load_scan_results(self, results):
        text_count = {}
        for r in results:
            original = r.get("original", "")
            if not original:
                continue
            loc = r.get("location", "")
            typ = r.get("type", "unknown")
            if original not in text_count:
                text_count[original] = {"count": 0, "locations": [], "type": typ}
            text_count[original]["count"] += 1
            text_count[original]["locations"].append(
                {"path": loc, "type": typ, "key": r.get("key", "")})
        self.translation_data = []
        for original, info in text_count.items():
            self.translation_data.append({
                "original": original,
                "translation": "",
                "type": info["type"],
                "count": info["count"],
                "locations": info["locations"],
                "selected": True,
            })
        self.update_table()
        self.update_sel_label()

    def visible_indices(self):
        """返回当前表格行 -> translation_data 索引列表（叠加未翻译过滤与搜索）"""
        if getattr(self, "_untrans_filter", False):
            base = [i for i, it in enumerate(self.translation_data) if not it["translation"]]
        else:
            base = list(range(len(self.translation_data)))
        txt = self.search_edit.text().strip().lower()
        if txt:
            base = [i for i in base
                    if txt in self.translation_data[i]["original"].lower()
                    or txt in self.translation_data[i]["translation"].lower()]
        return base

    def update_table(self):
        self.table.blockSignals(True)
        rows = self.visible_indices()
        self.table.setRowCount(len(rows))
        for r, di in enumerate(rows):
            item = self.translation_data[di]
            # 勾选
            cb = QCheckBox()
            cb.setChecked(item["selected"])
            cb.setToolTip("勾选 = 参与汉化与写回")
            cb.stateChanged.connect(lambda st, row=r: self.on_check_changed(row, st))
            self.table.setCellWidget(r, 0, cb)
            # 原文
            oi = QTableWidgetItem(item["original"])
            oi.setData(Qt.ItemDataRole.UserRole, di)
            oi.setToolTip(item["original"])
            self.table.setItem(r, 1, oi)
            # 译文
            ti = QTableWidgetItem(item["translation"])
            ti.setToolTip(item["translation"])
            self.table.setItem(r, 2, ti)
            # 类型
            ti2 = QTableWidgetItem(item["type"])
            ti2.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(r, 3, ti2)
            # 次数
            ci = QTableWidgetItem(str(item["count"]))
            ci.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(r, 4, ci)
            # 勾选状态底色
            self._apply_check_visual(r, item["selected"])
        self.table.blockSignals(False)

    def _apply_check_visual(self, row, selected):
        bg = QColor_selected() if selected else QColor_light()
        for col in (1, 2, 3, 4):
            it = self.table.item(row, col)
            if it:
                it.setBackground(bg)

    def on_check_changed(self, row, state):
        rows = self.visible_indices()
        if row >= len(rows):
            return
        di = rows[row]
        self.translation_data[di]["selected"] = bool(state)
        self._apply_check_visual(row, bool(state))
        self.update_sel_label()

    def set_all(self, checked):
        for item in self.translation_data:
            item["selected"] = checked
        self.update_table()
        self.update_sel_label()

    def filter_untranslated(self):
        self._untrans_filter = not getattr(self, "_untrans_filter", False)
        self.btn_untrans.setText("取消过滤" if self._untrans_filter else "仅未翻译")
        self.search_edit.clear()
        self.update_table()
        self.update_sel_label()

    # ---- 正则排除
    def apply_regex_exclude(self):
        """用正则匹配原文，匹配到的条目自动取消勾选（排除不翻译）"""
        pat = self.regex_edit.text()
        if not pat.strip():
            QMessageBox.information(self, "提示", "请输入要排除的正则表达式，例如：� 或 {\\\"text\\\":")
            return
        try:
            rx = re.compile(pat)
        except re.error as e:
            QMessageBox.warning(self, "正则表达式错误", f"无法编译正则：{e}")
            return
        self.excluded_by_regex = set()
        for i, it in enumerate(self.translation_data):
            try:
                if rx.search(it["original"]):
                    self.excluded_by_regex.add(i)
                    it["selected"] = False
            except Exception:
                continue
        self.regex_status.setText(f"已排除 {len(self.excluded_by_regex)} 项（可用\"撤销排除\"恢复）")
        self.update_table()
        self.update_sel_label()

    def undo_regex_exclude(self):
        """恢复被正则排除的条目（重新勾选）"""
        for i in list(self.excluded_by_regex):
            if i < len(self.translation_data):
                self.translation_data[i]["selected"] = True
        n = len(self.excluded_by_regex)
        self.excluded_by_regex = set()
        self.regex_status.setText(f"已恢复 {n} 项")
        self.update_table()
        self.update_sel_label()

    def filter_data(self):
        self.update_table()
        self.update_sel_label()

    def on_cell_changed(self, row, column):
        if column != 2:
            return
        item0 = self.table.item(row, 1)
        if not item0:
            return
        di = item0.data(Qt.ItemDataRole.UserRole)
        ti = self.table.item(row, 2)
        if ti is None:
            return
        self.translation_data[di]["translation"] = ti.text()

    def update_sel_label(self):
        n = sum(1 for it in self.translation_data if it["selected"])
        self.sel_label.setText(f"已选 {n} 项")

    # ---- 翻译
    def test_conn(self):
        self.save_cfg()
        engine, cfg = self.current_engine()
        tr = build_translator(engine, cfg)
        self.ai_status.setText("连接测试中…")
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(50, lambda: self._do_test(tr))

    def _do_test(self, tr):
        msg = tr.check_connection()
        self.ai_status.setText(msg)
        self.ctx.log(f"连接测试: {msg}")

    def start_translate(self):
        engine, cfg = self.current_engine()
        if engine == "openai" and not cfg["api_key"]:
            QMessageBox.warning(self, "提示", "请填写在线 API 的 API Key")
            return
        if engine == "baidu" and (not cfg.get("baidu_appid") or not cfg.get("baidu_secret")):
            QMessageBox.warning(self, "提示", "请填写百度翻译的 APP ID 与密钥")
            return
        # 只翻译：勾选 且 未翻译；JSON 条目若开启"只译 text"，标记 json_flag
        use_json = self.cb_json_only.isChecked()
        todo = []
        for i, it in enumerate(self.translation_data):
            if it["selected"] and not it["translation"]:
                jf = use_json and _is_json_with_text(it["original"])
                todo.append((i, it["original"], jf))
        if not todo:
            QMessageBox.information(self, "提示", "没有需要翻译的勾选文本")
            return
        try:
            tr = build_translator(engine, cfg)
        except Exception as e:
            QMessageBox.critical(self, "错误", f"创建翻译器失败: {e}")
            return
        self.ai_worker = AiTranslateWorker(todo, tr)
        self.ai_worker.progress.connect(self.on_ai_progress)
        self.ai_worker.one_done.connect(self.on_ai_one)
        self.ai_worker.finished_ok.connect(self.on_ai_finished)
        self.ai_worker.failed.connect(self.on_ai_failed)
        self.ai_progress.setVisible(True); self.ai_progress.setMaximum(len(todo)); self.ai_progress.setValue(0)
        self.translate_btn.setEnabled(False); self.stop_btn.setEnabled(True)
        self.ai_status.setText(f"正在翻译 {len(todo)} 条…")
        self.ctx.log(f"开始 AI 翻译 {len(todo)} 条，引擎={engine}")
        self.ai_worker.start()

    def stop_translate(self):
        if self.ai_worker:
            self.ai_worker.stop_flag = True
            self.ai_status.setText("正在停止…")

    def on_ai_progress(self, cur, total):
        self.ai_progress.setValue(cur)
        self.ai_status.setText(f"翻译进度 {cur}/{total}")

    def on_ai_one(self, di, translated):
        if di < len(self.translation_data):
            self.translation_data[di]["translation"] = translated
        self.refresh_row_of(di)

    def refresh_row_of(self, di):
        rows = self.visible_indices()
        if di not in rows:
            return
        r = rows.index(di)
        ti = self.table.item(r, 2)
        if ti:
            ti.setText(self.translation_data[di]["translation"])

    def on_ai_finished(self, ok, fail):
        self.ai_progress.setVisible(False)
        self.translate_btn.setEnabled(True); self.stop_btn.setEnabled(False)
        self.ai_status.setText(f"翻译完成：成功 {ok}，失败 {fail}")
        self.ctx.log(f"AI 翻译完成：成功 {ok}，失败 {fail}")
        self.update_table()
        if fail:
            QMessageBox.warning(self, "翻译结果", f"成功 {ok} 条，失败 {fail} 条。请检查引擎配置。")

    def on_ai_failed(self, msg):
        self.ctx.log(f"翻译失败: {msg}")

    def get_selected_translated(self):
        """返回写回用数据列表"""
        out = []
        for it in self.translation_data:
            if not it["selected"] or not it["translation"]:
                continue
            for loc in it["locations"]:
                out.append({
                    "original": it["original"],
                    "translation": it["translation"],
                    "location": loc["path"],
                    "type": loc["type"],
                    "key": loc.get("key", ""),
                })
        return out

    # ---- 导出 / 导入（方便后续维护）
    def export_data(self):
        """导出当前翻译数据（原文+译文+类型+位置+勾选状态）为 JSON"""
        if not self.translation_data:
            QMessageBox.information(self, "提示", "当前没有可导出的翻译数据")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "导出翻译数据", "translations_export.json", "JSON 文件 (*.json)")
        if not path:
            return
        payload = {
            "version": 1,
            "count": len(self.translation_data),
            "entries": [
                {
                    "original": it["original"],
                    "translation": it["translation"],
                    "type": it["type"],
                    "count": it["count"],
                    "selected": it["selected"],
                    "locations": it["locations"],
                }
                for it in self.translation_data
            ],
        }
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
        except Exception as e:
            QMessageBox.critical(self, "导出失败", str(e))
            return
        self.ctx.log(f"已导出 {len(self.translation_data)} 条翻译数据 -> {path}")
        QMessageBox.information(self, "导出成功", f"已导出 {len(self.translation_data)} 条到：\n{path}")

    def import_data(self):
        """导入 JSON，按 original 匹配回填译文与勾选状态；未匹配的条目追加为新条目"""
        if not self.translation_data:
            QMessageBox.information(self, "提示", "请先在\"① 选择世界 & 扫描\"扫描后再导入")
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "导入翻译数据", "", "JSON 文件 (*.json)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            entries = payload.get("entries") if isinstance(payload, dict) else payload
            if not isinstance(entries, list):
                raise ValueError("JSON 格式不正确：缺少 entries 列表")
        except Exception as e:
            QMessageBox.critical(self, "导入失败", f"无法解析文件：{e}")
            return
        by_original = {it["original"]: it for it in self.translation_data}
        updated = added = 0
        for e in entries:
            orig = e.get("original", "")
            if not orig:
                continue
            if orig in by_original:
                it = by_original[orig]
                if e.get("translation"):
                    it["translation"] = e["translation"]
                    updated += 1
                if "selected" in e:
                    it["selected"] = bool(e["selected"])
            else:
                self.translation_data.append({
                    "original": orig,
                    "translation": e.get("translation", ""),
                    "type": e.get("type", "text"),
                    "count": e.get("count", 1),
                    "locations": e.get("locations", []),
                    "selected": e.get("selected", True),
                })
                by_original[orig] = self.translation_data[-1]
                added += 1
        self.update_table()
        self.update_sel_label()
        self.ctx.log(f"已导入 {len(entries)} 条：更新译文 {updated}，新增条目 {added}")
        QMessageBox.information(
            self, "导入完成",
            f"导入 {len(entries)} 条：\n更新译文 {updated} 条\n新增条目 {added} 条")


def QColor_light():
    from PyQt6.QtGui import QColor
    return QColor(245, 248, 250)


def QColor_selected():
    from PyQt6.QtGui import QColor
    return QColor(224, 245, 240)


# ---------------------------------------------------------------- 页面 3：写回

class WritePage(QWidget):
    def __init__(self, app_ctx):
        super().__init__()
        self.ctx = app_ctx
        self.worker = None
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 24, 24, 24)
        lay.setSpacing(14)
        title = QLabel("③ 写回存档（自动备份）")
        title.setObjectName("page_title")
        lay.addWidget(title)
        lay.addWidget(make_label("仅写回「勾选且有译文」的文本。写回前每个文件会自动生成 .bak 备份（zip 包为整体备份）。"))

        card = QFrame(); card.setObjectName("card")
        cl = QVBoxLayout(card); cl.setContentsMargins(16, 14, 16, 14); cl.setSpacing(10)
        self.summary_label = make_label("尚未扫描/翻译", "stat_label")
        cl.addWidget(self.summary_label)
        row = QHBoxLayout()
        self.write_btn = QPushButton("开始写回（先备份）")
        self.write_btn.clicked.connect(self.start_write)
        row.addWidget(self.write_btn)
        self.back_btn = QPushButton("返回上一步"); self.back_btn.setObjectName("ghost")
        self.back_btn.clicked.connect(lambda: self.ctx.goto_page(1))
        row.addWidget(self.back_btn)
        self.restore_btn = QPushButton("从 .bak 恢复"); self.restore_btn.setObjectName("ghost")
        self.restore_btn.clicked.connect(self.restore_backups)
        row.addWidget(self.restore_btn)
        self.del_bak_btn = QPushButton("删除备份"); self.del_bak_btn.setObjectName("ghost")
        self.del_bak_btn.clicked.connect(self.delete_backups)
        row.addWidget(self.del_bak_btn)
        row.addStretch(1)
        cl.addLayout(row)
        self.progress = QProgressBar(); self.progress.setVisible(False)
        cl.addWidget(self.progress)
        lay.addWidget(card)

        self.log_text = QTextEdit(); self.log_text.setReadOnly(True)
        self.log_text.setPlaceholderText("写回日志…")
        lay.addWidget(self.log_text, 1)

    def refresh_summary(self):
        data = self.ctx.translate_page.get_selected_translated()
        self.pending = data
        files = len({d["location"] for d in data if d["location"]})
        if getattr(self.ctx, "scan_mode", "world") == "pack":
            self.summary_label.setText(
                f"将写回 {len(data)} 条替换到 {files} 个文件（材质包/光影包，自动 .bak 备份）")
        else:
            self.summary_label.setText(
                f"将写回 {len(data)} 条替换到 {files} 个文件（仅勾选且有译文的文本）")
        self.write_btn.setEnabled(bool(data))

    def start_write(self):
        data = self.ctx.translate_page.get_selected_translated()
        if not data:
            QMessageBox.information(self, "提示", "没有可写回的内容")
            return
        pack_mode = getattr(self.ctx, "scan_mode", "world") == "pack"
        if pack_mode:
            if not self.ctx.pack_path:
                QMessageBox.warning(self, "提示", "缺少材质包/光影包路径")
                return
        else:
            if not self.ctx.world_path:
                QMessageBox.warning(self, "提示", "缺少世界路径")
                return
        self.write_btn.setEnabled(False)
        self.back_btn.setEnabled(False)
        self.restore_btn.setEnabled(False)
        self.del_bak_btn.setEnabled(False)
        self.progress.setVisible(True); self.progress.setValue(0)
        if pack_mode:
            self.worker = PackWriteWorker(data)
        else:
            self.worker = WriteWorker(self.ctx.world_path, data)
        self.worker.progress_updated.connect(self.on_progress)
        self.worker.write_finished.connect(self.on_finished)
        self.worker.write_error.connect(self.on_error)
        self.worker.start()
        self.ctx.log(f"开始写回 {len(data)} 条（多线程）…")

    def on_progress(self, cur, total, msg):
        self.progress.setMaximum(max(total, 1)); self.progress.setValue(cur)
        self.log_text.append(msg)

    def _finish_buttons(self):
        """写回结束（成功/失败）后恢复按钮状态"""
        self.write_btn.setEnabled(True)
        self.back_btn.setEnabled(True)
        self.restore_btn.setEnabled(True)
        self.del_bak_btn.setEnabled(True)

    def on_error(self, msg):
        self._finish_buttons()
        QMessageBox.critical(self, "写回出错", msg)
        self.log_text.append(f"错误: {msg}")

    def on_finished(self, results):
        self._finish_buttons()
        self.log_text.append(
            f"完成：成功 {results.get('success_count', 0)}，失败 {results.get('error_count', 0)}")
        for e in results.get("errors", [])[:20]:
            self.log_text.append(f"  - {e}")
        self.ctx.log("写回完成")
        pack_mode = getattr(self.ctx, "scan_mode", "world") == "pack"
        tip = "已将原始文件备份为 .bak（zip 包为整体备份）。请到游戏内验证效果。"
        if pack_mode:
            tip = "已自动备份 .bak（zip 包为整体备份）。请到游戏内验证汉化效果。"
        QMessageBox.information(
            self, "写回完成",
            f"成功 {results.get('success_count', 0)} 条，失败 {results.get('error_count', 0)} 条。\n{tip}"
        )

    # ---- 备份管理
    def _find_backups(self):
        """返回 (bak_path, original_path) 列表：材质包走 pack_helper，世界目录递归查找"""
        if getattr(self.ctx, "scan_mode", "world") == "pack":
            return pack_helper.find_backups(self.ctx.pack_path)
        if not self.ctx.world_path:
            return []
        found = []
        for root, _, files in os.walk(self.ctx.world_path):
            for f in files:
                if f.endswith(".bak"):
                    bak = os.path.join(root, f)
                    found.append((bak, bak[:-4]))  # 去掉 .bak 得到原文件路径
        return found

    def restore_backups(self):
        """用 .bak 覆盖当前文件，二次确认"""
        backups = self._find_backups()
        if not backups:
            QMessageBox.information(self, "提示", "未找到任何 .bak 备份文件")
            return
        r = QMessageBox.question(
            self, "确认恢复",
            f"找到 {len(backups)} 个备份文件，将用 .bak 覆盖当前文件。\n确定恢复？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if r != QMessageBox.StandardButton.Yes:
            return
        if getattr(self.ctx, "scan_mode", "world") == "pack":
            ok, fail, msgs = pack_helper.restore_backups(self.ctx.pack_path)
            for m in msgs:
                self.log_text.append(m)
            self.ctx.log(f"备份恢复完成：成功 {ok}，失败 {fail}")
            QMessageBox.information(self, "恢复完成", f"成功恢复 {ok} 个文件，失败 {fail} 个")
            return
        ok = fail = 0
        for bak, orig in backups:
            try:
                shutil.copy2(bak, orig)
                ok += 1
                self.log_text.append(f"已恢复: {os.path.relpath(orig, self.ctx.world_path)}")
            except Exception as e:
                fail += 1
                self.log_text.append(f"恢复失败 {orig}: {e}")
        self.ctx.log(f"备份恢复完成：成功 {ok}，失败 {fail}")
        QMessageBox.information(self, "恢复完成", f"成功恢复 {ok} 个文件，失败 {fail} 个")

    def delete_backups(self):
        """删除所有 .bak，二次确认"""
        backups = self._find_backups()
        if not backups:
            QMessageBox.information(self, "提示", "未找到任何 .bak 备份文件")
            return
        r = QMessageBox.warning(
            self, "确认删除",
            f"找到 {len(backups)} 个备份文件，删除后将无法恢复。\n确定删除所有备份？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if r != QMessageBox.StandardButton.Yes:
            return
        if getattr(self.ctx, "scan_mode", "world") == "pack":
            ok, fail, msgs = pack_helper.delete_backups(self.ctx.pack_path)
            for m in msgs:
                self.log_text.append(m)
            self.ctx.log(f"备份删除完成：成功 {ok}，失败 {fail}")
            QMessageBox.information(self, "删除完成", f"成功删除 {ok} 个备份，失败 {fail} 个")
            return
        ok = fail = 0
        for bak, _ in backups:
            try:
                os.remove(bak)
                ok += 1
            except Exception as e:
                fail += 1
                self.log_text.append(f"删除失败 {bak}: {e}")
        self.ctx.log(f"备份删除完成：成功 {ok}，失败 {fail}")
        QMessageBox.information(self, "删除完成", f"成功删除 {ok} 个备份，失败 {fail} 个")


# ---------------------------------------------------------------- 主窗口

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MCT · Minecraft 地图汉化助手")
        self.setWindowIcon(self._load_icon())
        self.resize(1240, 840)
        self.config = Config()
        self.world_path = None
        self.pack_path = None
        self.scan_mode = "world"   # "world" | "pack"
        self.scan_results = []
        self.dark = False
        self._build()

    @staticmethod
    def _load_icon():
        """加载软件 logo：优先 .ico，其次 .png（从软件目录 logo/ 下寻找）"""
        base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo")
        for name in ("logo.ico", "logo.png", "logo.jpg", "logo.bmp"):
            p = os.path.join(base, name)
            if os.path.exists(p):
                return QIcon(p)
        return QIcon()

    def _build(self):
        root = QWidget(); root.setObjectName("root")
        self.setCentralWidget(root)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(16)

        # 左侧导航
        nav = QFrame(); nav.setObjectName("nav")
        nav.setFixedWidth(210)
        nl = QVBoxLayout(nav); nl.setContentsMargins(14, 20, 14, 20); nl.setSpacing(6)
        title = QLabel("MC Translation"); title.setObjectName("nav_title")
        nl.addWidget(title)
        sub = QLabel("Minecraft 地图汉化助手 v2"); sub.setObjectName("nav_sub")
        nl.addWidget(sub)
        nl.addSpacing(14)
        self.nav_buttons = []
        for i, (text, hint) in enumerate([
            ("选择", "① 提取文本"),
            ("翻译", "② 勾选 + 翻译"),
            ("回写", "③ 备份 + 写入"),
        ]):
            btn = QPushButton(f"{i+1}  {text}")
            btn.setObjectName("nav_btn"); btn.setCheckable(True)
            btn.clicked.connect(lambda _, p=i: self.goto_page(p))
            self.nav_buttons.append(btn)
            nl.addWidget(btn)
            tip = QLabel(hint); tip.setObjectName("nav_sub")
            nl.addWidget(tip)
            nl.addSpacing(4)
        nl.addStretch(1)
        self.open_log_btn = QPushButton("📄 打开日志")
        self.open_log_btn.setObjectName("nav_btn")
        self.open_log_btn.clicked.connect(self.open_log)
        nl.addWidget(self.open_log_btn)
        self.theme_btn = QPushButton("🌙 深色模式" if not self.dark else "☀ 浅色模式")
        self.theme_btn.setObjectName("nav_btn")
        self.theme_btn.clicked.connect(self.toggle_theme)
        nl.addWidget(self.theme_btn)
        outer.addWidget(nav)

        # 右侧页面
        self.stack = QStackedWidget()
        self.scan_page = ScanPage(self)
        self.translate_page = TranslatePage(self)
        self.write_page = WritePage(self)
        self.stack.addWidget(self.scan_page)
        self.stack.addWidget(self.translate_page)
        self.stack.addWidget(self.write_page)
        outer.addWidget(self.stack, 1)

        self.apply_theme(False)
        self.goto_page(0)

    def log(self, msg):
        from datetime import datetime
        ts = datetime.now().strftime("%H:%M:%S")
        for page in (self.scan_page, self.write_page):
            if hasattr(page, "log_text"):
                page.log_text.append(f"[{ts}] {msg}")

    def goto_page(self, idx):
        self.stack.setCurrentIndex(idx)
        for i, b in enumerate(self.nav_buttons):
            b.setChecked(i == idx)
        if idx == 2:
            self.write_page.refresh_summary()

    def toggle_theme(self):
        self.dark = not self.dark
        self.apply_theme(self.dark)

    def apply_theme(self, dark):
        qss = DARK_QSS if dark else LIGHT_QSS
        self.setStyleSheet(qss)
        self.theme_btn.setText("☀ 浅色模式" if dark else "🌙 深色模式")

    # ---- 日志管理
    @staticmethod
    def _log_path():
        """日志文件路径：优先软件目录，其次当前工作目录"""
        base = os.path.dirname(os.path.abspath(__file__))
        p = os.path.join(base, "mct.log")
        if os.path.exists(p):
            return p
        p2 = os.path.abspath("mct.log")
        return p2 if os.path.exists(p2) else p

    def open_log(self):
        path = self._log_path()
        if not os.path.exists(path):
            QMessageBox.information(self, "提示", "日志文件不存在（尚未产生日志输出）")
            return
        try:
            if sys.platform == "win32":
                os.startfile(path)
            else:
                import subprocess
                subprocess.Popen(["xdg-open", path])
        except Exception as e:
            QMessageBox.warning(self, "打开失败", f"无法打开日志文件：{e}")


def main():
    # 屏蔽 Qt 字体相关的 OpenType 警告（不影响功能，避免在 cmd 里刷屏）
    os.environ.setdefault("QT_LOGGING_RULES", "qt.qpa.fonts.warning=false")
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
