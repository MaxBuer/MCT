# -*- coding: utf-8 -*-
"""
日志工具 - Logger Utilities
"""

import logging
import os
import sys
from typing import Optional
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QTextEdit


class QTextEditHandler(logging.Handler):
    """自定义日志处理器，输出到QTextEdit"""
    
    def __init__(self, text_edit: QTextEdit):
        super().__init__()
        self.text_edit = text_edit
        self.setFormatter(logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s'
        ))
    
    def emit(self, record):
        """发送日志记录"""
        msg = self.format(record)
        
        # 根据日志级别设置颜色
        if record.levelno >= logging.ERROR:
            color = "#ff4444"  # 红色
        elif record.levelno >= logging.WARNING:
            color = "#ffaa00"  # 橙色
        elif record.levelno >= logging.INFO:
            color = "#44ff44"  # 绿色
        else:
            color = "#ffffff"  # 白色
        
        # 在QTextEdit中添加带颜色的文本
        self.text_edit.append(f'<span style="color: {color};">{msg}</span>')
        
        # 自动滚动到底部
        scrollbar = self.text_edit.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())


class LoggerManager:
    """日志管理器"""
    
    _instance = None
    _initialized = False
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if LoggerManager._initialized:
            return
        
        LoggerManager._initialized = True
        self.logger = None
        self.text_edit_handler = None
    
    def setup_logger(self, log_file: str = "mct.log", 
                     text_edit: Optional[QTextEdit] = None,
                     log_level: str = "INFO"):
        """设置日志系统"""
        # 创建日志目录
        log_dir = os.path.dirname(log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir)
        
        # 创建logger
        self.logger = logging.getLogger('mct')
        self.logger.setLevel(getattr(logging, log_level.upper()))
        
        # 清除现有处理器
        self.logger.handlers.clear()
        
        # 创建文件处理器
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s'
        )
        file_handler.setFormatter(file_formatter)
        self.logger.addHandler(file_handler)
        
        # 创建控制台处理器
        console_handler = logging.StreamHandler(sys.stdout)
        console_formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s'
        )
        console_handler.setFormatter(console_formatter)
        self.logger.addHandler(console_handler)
        
        # 创建QTextEdit处理器（如果提供了text_edit）
        if text_edit:
            self.text_edit_handler = QTextEditHandler(text_edit)
            self.logger.addHandler(self.text_edit_handler)
        
        self.logger.info("日志系统初始化完成")
        return self.logger
    
    def get_logger(self):
        """获取logger实例"""
        if self.logger is None:
            self.setup_logger()
        return self.logger


# 全局日志管理器实例
_logger_manager = LoggerManager()


def setup_logger(log_file: str = "mct.log", 
                 text_edit: Optional[QTextEdit] = None,
                 log_level: str = "INFO"):
    """设置日志系统"""
    return _logger_manager.setup_logger(log_file, text_edit, log_level)


def get_logger():
    """获取logger实例"""
    return _logger_manager.get_logger()