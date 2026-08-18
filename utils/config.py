# -*- coding: utf-8 -*-
"""
配置管理 - Configuration Management
"""

import os
import json
from typing import Any, Dict, Optional
from pathlib import Path


class Config:
    """配置管理类"""
    
    def __init__(self, config_file: str = "config.json"):
        self.config_file = config_file
        self.config_dir = self.get_config_dir()
        self.config_path = os.path.join(self.config_dir, config_file)
        self.data = {}
        self.load()
    
    def get_config_dir(self) -> str:
        """获取配置目录（MCT）。
        首选系统配置目录；若不可写（如无权限/只读环境），依次回退到用户目录与系统临时目录。"""
        # 获取用户主目录
        home_dir = os.path.expanduser("~")
        
        # 候选配置目录
        if os.name == 'nt':  # Windows
            candidates = [os.path.join(home_dir, 'AppData', 'Roaming', 'MCT')]
        elif os.name == 'posix':  # Linux/Mac
            candidates = [os.path.join(home_dir, '.config', 'mct')]
        else:
            candidates = []
        candidates.append(os.path.join(home_dir, '.mct'))
        
        for d in candidates:
            try:
                os.makedirs(d, exist_ok=True)
                # 验证可写性
                probe = os.path.join(d, '.mct_write_probe')
                with open(probe, 'w', encoding='utf-8') as f:
                    f.write('')
                os.remove(probe)
                return d
            except Exception:
                continue
        
        # 最终回退：系统临时目录
        import tempfile
        d = os.path.join(tempfile.gettempdir(), 'MCT')
        try:
            os.makedirs(d, exist_ok=True)
            return d
        except Exception:
            return home_dir

    def _legacy_config_paths(self) -> list:
        """旧版 MCC-I18n-Plus 的配置路径（用于迁移，保留用户已有的 API Key 等设置）"""
        home_dir = os.path.expanduser("~")
        if os.name == 'nt':
            return [os.path.join(home_dir, 'AppData', 'Roaming', 'MCCi18n', 'config.json')]
        if os.name == 'posix':
            return [os.path.join(home_dir, '.config', 'mcc_i18n', 'config.json')]
        return [os.path.join(home_dir, '.mcc_i18n', 'config.json')]

    def load(self):
        """加载配置（新位置缺失时尝试从旧版 MCC-I18n-Plus 迁移）"""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    self.data = json.load(f)
            else:
                migrated = False
                for old in self._legacy_config_paths():
                    if os.path.exists(old):
                        try:
                            with open(old, 'r', encoding='utf-8') as f:
                                self.data = json.load(f)
                            self.save()
                            migrated = True
                            break
                        except Exception:
                            continue
                if not migrated:
                    # 创建默认配置
                    self.data = self.get_default_config()
                    self.save()
        except Exception as e:
            print(f"加载配置文件失败: {e}")
            self.data = self.get_default_config()
    
    def save(self):
        """保存配置"""
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存配置文件失败: {e}")
    
    def get_default_config(self) -> Dict[str, Any]:
        """获取默认配置"""
        return {
            "version": "1.0.0",
            "language": "zh-CN",
            "theme": "light_teal.xml",
            "window": {
                "width": 1400,
                "height": 900,
                "maximized": False
            },
            "scan": {
                "scan_region": True,
                "scan_data": True,
                "scan_entities": True,
                "scan_playerdata": False,
                "file_extensions": [".mca", ".dat"],
                "max_file_size": 100,
                "max_text_length": 1000,
                "text_patterns": [
                    r"Command:\s*\"([^\"]*)\"",
                    r"CustomName:\s*\"([^\"]*)\"",
                    r"text:\s*\"([^\"]*)\"",
                    r"name:\s*\"([^\"]*)\""
                ]
            },
            "nbt": {
                "ignore_data_version": False,
                "strict_mode": False,
                "validate_json": True,
                "gzipped": True
            },
            "translation": {
                "auto_translate": False,
                "source_language": "en",
                "target_language": "zh-CN",
                "translation_service": "google",
                "batch_size": 10,
                "delay_between_requests": 1.0
            },
            "export": {
                "include_world": True,
                "include_lang_file": True,
                "compress_files": True,
                "default_format": "mcworld"
            },
            "backup": {
                "auto_backup": True,
                "backup_format": "zip",
                "keep_old_backups": 5
            },
            "logging": {
                "level": "INFO",
                "file": "mct.log",
                "max_size": "10MB",
                "backup_count": 3
            }
        }
    
    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值"""
        keys = key.split('.')
        value = self.data
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value
    
    def set(self, key: str, value: Any):
        """设置配置值"""
        keys = key.split('.')
        data = self.data
        
        for k in keys[:-1]:
            if k not in data:
                data[k] = {}
            data = data[k]
        
        data[keys[-1]] = value
        self.save()
    
    def get_scan_config(self) -> Dict[str, Any]:
        """获取扫描配置"""
        return self.get('scan', {})
    
    def get_translation_config(self) -> Dict[str, Any]:
        """获取翻译配置"""
        return self.get('translation', {})
    
    def get_export_config(self) -> Dict[str, Any]:
        """获取导出配置"""
        return self.get('export', {})
    
    def get_backup_config(self) -> Dict[str, Any]:
        """获取备份配置"""
        return self.get('backup', {})
    
    def get_nbt_config(self) -> Dict[str, Any]:
        """获取NBT配置"""
        return self.get('nbt', {})
    
    def get_logging_config(self) -> Dict[str, Any]:
        """获取日志配置"""
        return self.get('logging', {})
    
    def get_window_config(self) -> Dict[str, Any]:
        """获取窗口配置"""
        return self.get('window', {})
    
    def set_window_size(self, width: int, height: int):
        """设置窗口大小"""
        self.set('window.width', width)
        self.set('window.height', height)
    
    def set_window_maximized(self, maximized: bool):
        """设置窗口最大化状态"""
        self.set('window.maximized', maximized)
    
    def get_theme(self) -> str:
        """获取主题"""
        return self.get('theme', 'light_teal.xml')
    
    def set_theme(self, theme: str):
        """设置主题"""
        self.set('theme', theme)
    
    def get_language(self) -> str:
        """获取语言"""
        return self.get('language', 'zh-CN')
    
    def set_language(self, language: str):
        """设置语言"""
        self.set('language', language)