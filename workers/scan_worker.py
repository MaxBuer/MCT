# -*- coding: utf-8 -*-
"""
扫描工作线程 - Scan Worker Thread
"""

import os
import re
import json
from typing import List, Dict, Any, Optional
from PyQt6.QtCore import QThread, pyqtSignal

import nbtlib
from nbtlib import File, Compound, List as NBTList

from utils.logger import get_logger
from utils.config import Config
from utils.text_filter import is_translatable_text
# 真正的 MCA 区域文件解析(压缩数据 -> NBT)
from utils.mca_helper import load_mca, iter_json_components


class ScanWorker(QThread):
    """扫描工作线程"""
    
    progress_updated = pyqtSignal(int, int, str)
    scan_finished = pyqtSignal(list)
    error_occurred = pyqtSignal(str)
    
    def __init__(self, world_path: str, scan_region: bool = True, 
                 scan_data: bool = True, scan_entities: bool = True,
                 scan_playerdata: bool = False):
        super().__init__()
        self.world_path = world_path
        self.scan_region = scan_region
        self.scan_data = scan_data
        self.scan_entities = scan_entities
        self.scan_playerdata = scan_playerdata
        self.logger = get_logger()
        self.config = Config()
        self.results = []
        self.stop_flag = False
    
    def run(self):
        """运行扫描"""
        try:
            self.results = []
            total_files = 0
            processed_files = 0
            
            # 统计总文件数
            if self.scan_region:
                region_path = os.path.join(self.world_path, "region")
                if os.path.exists(region_path):
                    total_files += len([f for f in os.listdir(region_path) if f.endswith('.mca')])
            
            if self.scan_data:
                data_path = os.path.join(self.world_path, "data")
                if os.path.exists(data_path):
                    total_files += len([f for f in os.listdir(data_path) if f.endswith('.dat')])
            
            if self.scan_entities:
                entities_path = os.path.join(self.world_path, "entities")
                if os.path.exists(entities_path):
                    total_files += len([f for f in os.listdir(entities_path) if f.endswith('.mca')])
            
            self.logger.info(f"开始扫描，总计 {total_files} 个文件")
            
            # 扫描各个区域
            if self.scan_region:
                processed_files = self.scan_region_files(processed_files, total_files)
            
            if self.scan_data:
                processed_files = self.scan_data_files(processed_files, total_files)
            
            if self.scan_entities:
                processed_files = self.scan_entity_files(processed_files, total_files)
            
            if self.scan_playerdata:
                processed_files = self.scan_playerdata_files(processed_files, total_files)
            
            # 完成信号
            self.scan_finished.emit(self.results)
            self.logger.info(f"扫描完成，找到 {len(self.results)} 条文本")
            
        except Exception as e:
            error_msg = f"扫描过程中发生错误: {str(e)}"
            self.logger.error(error_msg)
            self.error_occurred.emit(error_msg)
    
    def scan_region_files(self, current: int, total: int) -> int:
        """扫描region文件"""
        region_path = os.path.join(self.world_path, "region")
        if not os.path.exists(region_path):
            return current
        
        mca_files = [f for f in os.listdir(region_path) if f.endswith('.mca')]
        
        for mca_file in mca_files:
            if self.stop_flag:
                break
            
            file_path = os.path.join(region_path, mca_file)
            self.progress_updated.emit(current + 1, total, f"扫描: {mca_file}")
            
            try:
                self.scan_mca_file(file_path)
            except Exception as e:
                self.logger.warning(f"扫描文件 {mca_file} 失败: {e}")
            
            current += 1
        
        return current
    
    def scan_data_files(self, current: int, total: int) -> int:
        """扫描data文件"""
        data_path = os.path.join(self.world_path, "data")
        if not os.path.exists(data_path):
            return current
        
        dat_files = [f for f in os.listdir(data_path) if f.endswith('.dat')]
        
        for dat_file in dat_files:
            if self.stop_flag:
                break
            
            file_path = os.path.join(data_path, dat_file)
            self.progress_updated.emit(current + 1, total, f"扫描: {dat_file}")
            
            try:
                self.scan_dat_file(file_path)
            except Exception as e:
                self.logger.warning(f"扫描文件 {dat_file} 失败: {e}")
            
            current += 1
        
        return current
    
    def scan_playerdata_files(self, current: int, total: int) -> int:
        """扫描玩家数据文件"""
        playerdata_path = os.path.join(self.world_path, "playerdata")
        if not os.path.exists(playerdata_path):
            return current
        
        dat_files = [f for f in os.listdir(playerdata_path) if f.endswith('.dat')]
        
        for dat_file in dat_files:
            if self.stop_flag:
                break
            
            file_path = os.path.join(playerdata_path, dat_file)
            self.progress_updated.emit(current + 1, total, f"扫描玩家数据: {dat_file}")
            
            try:
                self.scan_dat_file(file_path)
            except Exception as e:
                self.logger.warning(f"扫描玩家数据文件 {dat_file} 失败: {e}")
            
            current += 1
        
        return current
    
    def scan_entity_files(self, current: int, total: int) -> int:
        """扫描实体文件"""
        entities_path = os.path.join(self.world_path, "entities")
        if not os.path.exists(entities_path):
            return current
        
        mca_files = [f for f in os.listdir(entities_path) if f.endswith('.mca')]
        
        for mca_file in mca_files:
            if self.stop_flag:
                break
            
            file_path = os.path.join(entities_path, mca_file)
            self.progress_updated.emit(current + 1, total, f"扫描实体: {mca_file}")
            
            try:
                self.scan_entity_file(file_path)
            except Exception as e:
                self.logger.warning(f"扫描实体文件 {mca_file} 失败: {e}")
            
            current += 1
        
        return current
    
    def scan_mca_file(self, file_path: str):
        """扫描MCA文件(region) - 真正解析压缩数据, 提取区块 NBT 中的文本"""
        try:
            self._scan_mca_parsed(file_path)
        except Exception as e:
            self.logger.debug(f"扫描MCA文件 {file_path} 时出错: {e}")

    def scan_entity_file(self, file_path: str):
        """扫描实体文件(entities) - 与 region 相同结构, 用同一解析器"""
        try:
            self._scan_mca_parsed(file_path)
        except Exception as e:
            self.logger.debug(f"扫描实体文件 {file_path} 时出错: {e}")

    def _scan_mca_parsed(self, file_path: str):
        """解析 .mca 的所有区块, 按字段分类提取可翻译文本"""
        chunks, _info = load_mca(file_path)
        for _i, nbt in chunks:
            if nbt is None:
                continue
            self.scan_chunk_nbt(nbt, file_path, "")

    def scan_chunk_nbt(self, data: Any, file_path: str, path: str = ""):
        """递归遍历区块 NBT, 按路径提取文本:
        - Command 字段: 解析命令内嵌 JSON 的 text 值(对话核心)
        - front_text.messages[].text: 告示牌文字
        - CustomName / custom_name: 实体/物品自定义名称
        - written_book_content: 成书内容
        """
        if isinstance(data, Compound):
            for key, value in data.items():
                current_path = f"{path}.{key}" if path else key

                # 命令方块命令: 提取内嵌 JSON 的 text 对话
                if key == 'Command' and isinstance(value, str):
                    self._extract_command_texts(str(value), file_path)

                # 告示牌文字: messages[].text
                elif key == 'text' and isinstance(value, str) and 'front_text' in current_path:
                    if self.is_translatable_text(str(value), allow_prefix=True):
                        self.add_result(str(value), 'sign_text', file_path)

                # 实体/物品自定义名称(可能包了 JSON 壳)
                elif key in ('CustomName', 'custom_name') and isinstance(value, str):
                    text = self._unwrap_json_text(str(value))
                    if text is not None and self.is_translatable_text(text, allow_prefix=True):
                        self.add_result(text, 'entity_name', file_path)

                # 成书内容
                elif 'written_book' in current_path and isinstance(value, str):
                    if self.is_translatable_text(str(value), allow_prefix=True):
                        self.add_result(str(value), 'book_text', file_path)

                # 其它 JSON text 字段(如物品 custom_name.text)
                elif key == 'text' and isinstance(value, str):
                    if self.is_translatable_text(str(value), allow_prefix=True):
                        self.add_result(str(value), 'text', file_path)

                # 递归
                self.scan_chunk_nbt(value, file_path, current_path)

        elif isinstance(data, NBTList):
            for i, item in enumerate(data):
                self.scan_chunk_nbt(item, file_path, f"{path}[{i}]")

    def _extract_command_texts(self, command: str, file_path: str):
        """从命令字符串中解析出所有 JSON 组件的 text 字段(对话文本)"""
        try:
            for _start, _end, obj in iter_json_components(command):
                texts = []
                self._collect_json_texts(obj, texts)
                for t in texts:
                    if self.is_translatable_text(t, allow_prefix=True):
                        self.add_result(t, 'command_json', file_path)
        except Exception as e:
            self.logger.debug(f"解析命令文本出错: {e}")

    def _collect_json_texts(self, data: Any, out: list):
        """递归收集 JSON 中的 text 字段值"""
        if isinstance(data, dict):
            if isinstance(data.get('text'), str):
                out.append(data['text'])
            for value in data.values():
                self._collect_json_texts(value, out)
        elif isinstance(data, list):
            for item in data:
                self._collect_json_texts(item, out)

    def _unwrap_json_text(self, value: str) -> Optional[str]:
        """如果字符串是 JSON({...} 或 [...]), 取出其中的 text 值; 否则原样返回"""
        s = value.strip()
        if s.startswith('{') or s.startswith('['):
            try:
                obj = json.loads(value)
                texts = []
                self._collect_json_texts(obj, texts)
                if texts:
                    return texts[0]
                return None   # JSON 但无 text 字段, 跳过
            except Exception:
                pass
        return value

    def scan_dat_file(self, file_path: str):
        """扫描DAT文件"""
        try:
            # 从配置中读取NBT加载选项
            ignore_data_version = self.config.get('nbt.ignore_data_version', False)

            # 使用nbtlib解析NBT文件，强制使用gzip=True
            nbt_file = File.load(file_path, gzipped=True)

            # 递归扫描NBT数据
            self.scan_nbt_data(nbt_file, file_path)

        except Exception as e:
            self.logger.debug(f"扫描DAT文件 {file_path} 时出错: {e}")
    
    def scan_nbt_data(self, data: Any, file_path: str, path: str = ""):
        """递归扫描NBT数据"""
        if isinstance(data, Compound):
            for key, value in data.items():
                current_path = f"{path}.{key}" if path else key
                
                # 检查特定字段
                if key in ['Command', 'CustomName', 'Name']:
                    if isinstance(value, str) and self.is_translatable_text(value):
                        self.add_result(value, f'nbt_{key.lower()}', file_path)
                
                # 递归处理
                self.scan_nbt_data(value, file_path, current_path)
        
        elif isinstance(data, NBTList):
            for i, item in enumerate(data):
                current_path = f"{path}[{i}]"
                self.scan_nbt_data(item, file_path, current_path)
        
        elif isinstance(data, str):
            # 检查字符串内容
            if self.is_translatable_text(data):
                # 尝试解析JSON文本
                if data.startswith('{') or data.startswith('['):
                    try:
                        json_data = json.loads(data)
                        self.scan_json_text(json_data, file_path)
                    except:
                        # 如果不是有效的JSON，直接作为文本处理
                        self.add_result(data, 'text', file_path)
                else:
                    self.add_result(data, 'text', file_path)
    
    def scan_json_text(self, data: Any, file_path: str):
        """扫描JSON文本内容"""
        if isinstance(data, dict):
            # 查找text字段
            if 'text' in data and isinstance(data['text'], str):
                if self.is_translatable_text(data['text']):
                    self.add_result(data['text'], 'json_text', file_path)
            
            # 查找extra字段
            if 'extra' in data and isinstance(data['extra'], list):
                for item in data['extra']:
                    self.scan_json_text(item, file_path)
            
            # 递归处理其他字段
            for key, value in data.items():
                if key != 'text' and key != 'extra':
                    self.scan_json_text(value, file_path)
        
        elif isinstance(data, list):
            for item in data:
                self.scan_json_text(item, file_path)
    
    def is_translatable_text(self, text: str, allow_prefix: bool = False) -> bool:
        """判断是否为可翻译文本（复用 utils.text_filter 的统一规则）
        allow_prefix=True 时跳过对 / @ # 开头内容的过滤(用于已从命令中提取出的纯文本对话)
        """
        return is_translatable_text(text, allow_prefix=allow_prefix)
    
    def add_result(self, text: str, text_type: str, location: str):
        """添加扫描结果"""
        if text and text.strip():
            self.results.append({
                'original': text.strip(),
                'type': text_type,
                'location': location,
                'file': os.path.basename(location)
            })
    
    def stop(self):
        """停止扫描"""
        self.stop_flag = True