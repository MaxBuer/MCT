# -*- coding: utf-8 -*-
"""
JSON验证器 - JSON Validator
"""

import json
import re
from typing import Any, Dict, List, Union, Optional

from utils.logger import get_logger


def validate_json_text(data: Any) -> bool:
    """
    验证JSON文本数据的有效性
    
    Args:
        data: 要验证的数据
        
    Returns:
        是否有效
    """
    logger = get_logger()
    
    try:
        # 如果是字符串，尝试解析为JSON
        if isinstance(data, str):
            json.loads(data)
            return True
        
        # 如果是字典或列表，验证其内容
        elif isinstance(data, (dict, list)):
            json.dumps(data, ensure_ascii=False)
            return True
        
        else:
            return False
            
    except (json.JSONDecodeError, TypeError, ValueError) as e:
        logger.debug(f"JSON验证失败: {e}")
        return False


def validate_tellraw_json(data: Dict[str, Any]) -> bool:
    """
    验证tellraw JSON格式
    
    Args:
        data: JSON数据
        
    Returns:
        是否有效
    """
    required_fields = ['text']
    optional_fields = ['color', 'bold', 'italic', 'underlined', 'strikethrough', 'obfuscated', 'extra']
    
    # 检查必需字段
    for field in required_fields:
        if field not in data:
            return False
    
    # 检查字段类型
    if not isinstance(data.get('text'), str):
        return False
    
    # 检查颜色值
    if 'color' in data:
        valid_colors = [
            'black', 'dark_blue', 'dark_green', 'dark_aqua', 'dark_red', 'dark_purple',
            'gold', 'gray', 'dark_gray', 'blue', 'green', 'aqua', 'red', 'light_purple',
            'yellow', 'white', 'reset'
        ]
        if data['color'] not in valid_colors and not re.match(r'^#[0-9a-fA-F]{6}$', data['color']):
            return False
    
    # 检查布尔字段
    bool_fields = ['bold', 'italic', 'underlined', 'strikethrough', 'obfuscated']
    for field in bool_fields:
        if field in data and not isinstance(data[field], bool):
            return False
    
    # 检查extra字段
    if 'extra' in data:
        if not isinstance(data['extra'], list):
            return False
        for item in data['extra']:
            if not validate_tellraw_json(item):
                return False
    
    return True


def validate_bossbar_json(data: Dict[str, Any]) -> bool:
    """
    验证bossbar JSON格式
    
    Args:
        data: JSON数据
        
    Returns:
        是否有效
    """
    # Bossbar名称通常是一个字符串或tellraw JSON
    if isinstance(data, str):
        return True
    
    elif isinstance(data, dict):
        return validate_tellraw_json(data)
    
    else:
        return False


def validate_title_json(data: Dict[str, Any]) -> bool:
    """
    验证title JSON格式
    
    Args:
        data: JSON数据
        
    Returns:
        是否有效
    """
    # Title可以是字符串或tellraw JSON
    if isinstance(data, str):
        return True
    
    elif isinstance(data, dict):
        return validate_tellraw_json(data)
    
    else:
        return False


def sanitize_json_text(text: str) -> str:
    """
    清理JSON文本，确保其有效性
    
    Args:
        text: 原始文本
        
    Returns:
        清理后的文本
    """
    if not text:
        return text
    
    # 转义特殊字符
    text = text.replace('\\', '\\\\')
    text = text.replace('"', '\\"')
    text = text.replace('\n', '\\n')
    text = text.replace('\r', '\\r')
    text = text.replace('\t', '\\t')
    
    # 移除控制字符
    text = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', text)
    
    return text


def create_tellraw_json(text: str, **kwargs) -> Dict[str, Any]:
    """
    创建tellraw JSON对象
    
    Args:
        text: 文本内容
        **kwargs: 其他样式参数
        
    Returns:
        tellraw JSON对象
    """
    json_obj = {'text': text}
    
    # 添加样式参数
    valid_params = {
        'color': str,
        'bold': bool,
        'italic': bool,
        'underlined': bool,
        'strikethrough': bool,
        'obfuscated': bool
    }
    
    for param, param_type in valid_params.items():
        if param in kwargs and isinstance(kwargs[param], param_type):
            json_obj[param] = kwargs[param]
    
    return json_obj


def extract_text_from_json(data: Any) -> List[str]:
    """
    从JSON数据中提取所有文本内容
    
    Args:
        data: JSON数据
        
    Returns:
        文本内容列表
    """
    texts = []
    
    if isinstance(data, dict):
        if 'text' in data and isinstance(data['text'], str):
            texts.append(data['text'])
        
        if 'extra' in data and isinstance(data['extra'], list):
            for item in data['extra']:
                texts.extend(extract_text_from_json(item))
        
        # 递归处理其他值
        for value in data.values():
            if isinstance(value, (dict, list)):
                texts.extend(extract_text_from_json(value))
    
    elif isinstance(data, list):
        for item in data:
            texts.extend(extract_text_from_json(item))
    
    elif isinstance(data, str):
        texts.append(data)
    
    return texts


def merge_json_texts(data: Any, translations: Dict[str, str]) -> bool:
    """
    合并翻译到JSON数据中
    
    Args:
        data: JSON数据
        translations: 翻译字典
        
    Returns:
        是否进行了修改
    """
    modified = False
    
    if isinstance(data, dict):
        if 'text' in data and isinstance(data['text'], str):
            original = data['text']
            if original in translations:
                data['text'] = translations[original]
                modified = True
        
        if 'extra' in data and isinstance(data['extra'], list):
            for item in data['extra']:
                if merge_json_texts(item, translations):
                    modified = True
        
        # 递归处理其他值
        for value in data.values():
            if isinstance(value, (dict, list)):
                if merge_json_texts(value, translations):
                    modified = True
    
    elif isinstance(data, list):
        for item in data:
            if merge_json_texts(item, translations):
                modified = True
    
    return modified


class JSONTextProcessor:
    """JSON文本处理器"""
    
    def __init__(self):
        self.logger = get_logger()
    
    def process_tellraw_command(self, command: str) -> Optional[str]:
        """
        处理tellraw命令，提取和验证JSON部分
        
        Args:
            command: 原始命令
            
        Returns:
            处理后的命令或None
        """
        # 匹配tellraw命令
        match = re.search(r'/tellraw\s+\S+\s+(.+)', command)
        if not match:
            return None
        
        json_part = match.group(1).strip()
        
        try:
            # 尝试解析JSON
            json_data = json.loads(json_part)
            
            # 验证格式
            if isinstance(json_data, (dict, list)):
                # 重新序列化以确保格式正确
                return command.replace(json_part, json.dumps(json_data, ensure_ascii=False))
            
        except json.JSONDecodeError:
            self.logger.warning(f"无效的tellraw JSON: {json_part[:100]}...")
        
        return None
    
    def process_title_command(self, command: str) -> Optional[str]:
        """
        处理title命令，提取和验证JSON部分
        
        Args:
            command: 原始命令
            
        Returns:
            处理后的命令或None
        """
        # 匹配title命令
        match = re.search(r'/title\s+\S+\s+(title|subtitle|actionbar)\s+(.+)', command)
        if not match:
            return None
        
        json_part = match.group(2).strip()
        
        try:
            # 尝试解析JSON
            json_data = json.loads(json_part)
            
            # 验证格式
            if isinstance(json_data, (dict, list)):
                # 重新序列化以确保格式正确
                return command.replace(json_part, json.dumps(json_data, ensure_ascii=False))
            
        except json.JSONDecodeError:
            self.logger.warning(f"无效的title JSON: {json_part[:100]}...")
        
        return None
    
    def process_bossbar_command(self, command: str) -> Optional[str]:
        """
        处理bossbar命令，提取和验证JSON部分
        
        Args:
            command: 原始命令
            
        Returns:
            处理后的命令或None
        """
        # 匹配bossbar set name命令
        match = re.search(r'/bossbar\s+\S+\s+set\s+name\s+(.+)', command)
        if not match:
            return None
        
        json_part = match.group(1).strip()
        
        try:
            # 尝试解析JSON
            json_data = json.loads(json_part)
            
            # 验证格式
            if isinstance(json_data, (dict, list)):
                # 重新序列化以确保格式正确
                return command.replace(json_part, json.dumps(json_data, ensure_ascii=False))
            
        except json.JSONDecodeError:
            self.logger.warning(f"无效的bossbar JSON: {json_part[:100]}...")
        
        return None