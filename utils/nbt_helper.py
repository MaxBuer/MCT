# -*- coding: utf-8 -*-
"""
NBT文件助手 - NBT File Helper
"""

import os
import re
from typing import Tuple, Optional
from pathlib import Path

import nbtlib
from nbtlib import File

from utils.logger import get_logger
from utils.config import Config


def validate_world(world_path: str) -> Tuple[bool, str]:
    """
    验证Minecraft世界文件夹的有效性
    
    Args:
        world_path: 世界文件夹路径
        
    Returns:
        (is_valid, message): 是否有效和消息
    """
    logger = get_logger()
    config = Config()
    
    try:
        path = Path(world_path)
        
        # 检查路径是否存在
        if not path.exists():
            return False, "路径不存在"
        
        # 检查是否为目录
        if not path.is_dir():
            return False, "路径不是文件夹"
        
        # 检查level.dat文件
        level_dat = path / "level.dat"
        if not level_dat.exists():
            return False, "缺少level.dat文件"
        
        # 验证level.dat文件
        try:
            # 从配置中读取NBT加载选项
            ignore_data_version = config.get('nbt.ignore_data_version', False)
            
            # 使用gzip=True参数加载NBT文件
            nbt_file = File.load(str(level_dat), gzipped=True)
            
            # 检查Data标签是否存在
            if 'Data' not in nbt_file:
                return False, "level.dat缺少Data标签"
            
            # 检查Data标签下的必要字段
            data = nbt_file['Data']
            if not isinstance(data, nbtlib.Compound):
                return False, "level.dat格式不正确"
            
            # DataVersion 位于 Data 标签内部（现代 Minecraft 标准结构），
            # 而非 level.dat 根节点；仅对极早期版本回退检查根节点
            if not ignore_data_version:
                has_version = ('DataVersion' in data) or ('DataVersion' in nbt_file)
                if not has_version:
                    return False, "level.dat缺少DataVersion标签"
            
            # 检查版本信息
            if 'Version' in data and not ignore_data_version:
                version = data['Version']
                if isinstance(version, nbtlib.Compound):
                    if 'Name' in version:
                        logger.info(f"检测到Minecraft版本: {version['Name']}")
            
        except Exception as e:
            if "NBT file is not gzipped" in str(e):
                return False, "level.dat文件格式不正确（需要gzip压缩）"
            return False, f"level.dat文件损坏: {e}"
        
        # 检查region文件夹
        region_path = path / "region"
        if not region_path.exists():
            logger.warning("缺少region文件夹")
        
        # 检查data文件夹
        data_path = path / "data"
        if not data_path.exists():
            logger.info("缺少data文件夹（可选）")
        
        return True, "有效的Minecraft世界"
        
    except Exception as e:
        logger.error(f"验证世界失败: {e}")
        return False, f"验证失败: {e}"


def get_world_info(world_path: str) -> dict:
    """
    获取世界信息
    
    Args:
        world_path: 世界文件夹路径
        
    Returns:
        世界信息字典
    """
    logger = get_logger()
    config = Config()
    info = {
        'name': os.path.basename(world_path),
        'path': world_path,
        'valid': False,
        'version': 'Unknown',
        'game_type': 'Unknown',
        'difficulty': 'Unknown',
        'spawn_x': 0,
        'spawn_y': 0,
        'spawn_z': 0,
        'time': 0,
        'day_time': 0,
        'game_rules': {},
        'data_version': 0,
        'ignore_data_version': config.get('nbt.ignore_data_version', False)
    }
    
    try:
        level_dat = os.path.join(world_path, 'level.dat')
        if not os.path.exists(level_dat):
            return info
        
        # 从配置中读取NBT加载选项
        ignore_data_version = config.get('nbt.ignore_data_version', False)
        
        nbt_file = File.load(level_dat, gzipped=True)
        data = nbt_file.get('Data', {})
        
        # 基本信息
        info['valid'] = True
        if not ignore_data_version:
            info['data_version'] = data.get('DataVersion', 0)
        
        # 世界名称
        if 'LevelName' in data:
            info['name'] = data['LevelName']
        
        # 游戏版本
        if 'Version' in data and not ignore_data_version:
            version = data['Version']
            if isinstance(version, dict) and 'Name' in version:
                info['version'] = version['Name']
        
        # 游戏类型
        if 'GameType' in data:
            game_types = {0: 'Survival', 1: 'Creative', 2: 'Adventure', 3: 'Spectator'}
            info['game_type'] = game_types.get(data['GameType'], 'Unknown')
        
        # 难度
        if 'Difficulty' in data:
            difficulties = {0: 'Peaceful', 1: 'Easy', 2: 'Normal', 3: 'Hard'}
            info['difficulty'] = difficulties.get(data['Difficulty'], 'Unknown')
        
        # 出生点
        if 'SpawnX' in data:
            info['spawn_x'] = data['SpawnX']
        if 'SpawnY' in data:
            info['spawn_y'] = data['SpawnY']
        if 'SpawnZ' in data:
            info['spawn_z'] = data['SpawnZ']
        
        # 时间
        if 'Time' in data:
            info['time'] = data['Time']
        if 'DayTime' in data:
            info['day_time'] = data['DayTime']
        
        # 游戏规则
        if 'GameRules' in data:
            game_rules = data['GameRules']
            if isinstance(game_rules, dict):
                info['game_rules'] = dict(game_rules)
        
        logger.info(f"获取世界信息完成: {info['name']}")
        
    except Exception as e:
        logger.error(f"获取世界信息失败: {e}")
        info['valid'] = False
    
    return info


def load_nbt_file(file_path: str, ignore_data_version: bool = False) -> Optional[File]:
    """
    加载NBT文件
    
    Args:
        file_path: NBT文件路径
        ignore_data_version: 是否忽略DataVersion检查
        
    Returns:
        NBT文件对象或None
    """
    logger = get_logger()
    
    try:
        if not os.path.exists(file_path):
            logger.error(f"NBT文件不存在: {file_path}")
            return None
        
        # 使用gzipped=True参数加载NBT文件
        nbt_file = File.load(file_path, gzipped=True)
        
        # 如果忽略DataVersion，移除相关检查
        if ignore_data_version and 'DataVersion' in nbt_file:
            logger.info(f"忽略DataVersion检查: {file_path}")
        
        return nbt_file
        
    except Exception as e:
        logger.error(f"加载NBT文件失败 {file_path}: {e}")
        return None


def save_nbt_file(nbt_file: File, file_path: str) -> bool:
    """
    保存NBT文件
    
    Args:
        nbt_file: NBT文件对象
        file_path: 保存路径
        
    Returns:
        是否成功
    """
    logger = get_logger()
    
    try:
        # 使用gzipped=True参数保存NBT文件
        nbt_file.save(file_path, gzipped=True)
        logger.info(f"保存NBT文件成功: {file_path}")
        return True
        
    except Exception as e:
        logger.error(f"保存NBT文件失败 {file_path}: {e}")
        return False


def list_world_files(world_path: str) -> dict:
    """
    列出世界中的文件
    
    Args:
        world_path: 世界文件夹路径
        
    Returns:
        文件分类字典
    """
    files = {
        'root': [],
        'region': [],
        'entities': [],
        'data': [],
        'playerdata': [],
        'stats': []
    }
    
    try:
        path = Path(world_path)
        
        # 根目录文件
        for file in path.iterdir():
            if file.is_file():
                files['root'].append(file.name)
        
        # 子目录文件
        for subdir in ['region', 'entities', 'data', 'playerdata', 'stats']:
            subdir_path = path / subdir
            if subdir_path.exists() and subdir_path.is_dir():
                for file in subdir_path.iterdir():
                    if file.is_file():
                        files[subdir].append(file.name)
        
    except Exception as e:
        logger = get_logger()
        logger.error(f"列出世界文件失败: {e}")
    
    return files


def create_world_backup(world_path: str, backup_dir: Optional[str] = None) -> str:
    """
    创建世界备份
    
    Args:
        world_path: 世界文件夹路径
        backup_dir: 备份目录（可选）
        
    Returns:
        备份文件路径
    """
    import shutil
    import zipfile
    from datetime import datetime
    
    logger = get_logger()
    
    try:
        world_name = os.path.basename(world_path)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        if backup_dir is None:
            backup_dir = os.path.dirname(world_path)
        
        backup_name = f"{world_name}_{timestamp}_backup.zip"
        backup_path = os.path.join(backup_dir, backup_name)
        
        # 创建ZIP备份
        with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(world_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, world_path)
                    zipf.write(file_path, arcname)
        
        logger.info(f"备份创建完成: {backup_path}")
        return backup_path
        
    except Exception as e:
        logger.error(f"创建备份失败: {e}")
        raise Exception(f"备份创建失败: {e}")


def validate_nbt_file(file_path: str, ignore_data_version: bool = False) -> bool:
    """
    验证NBT文件的有效性
    
    Args:
        file_path: NBT文件路径
        ignore_data_version: 是否忽略DataVersion检查
        
    Returns:
        是否有效
    """
    logger = get_logger()
    
    try:
        if not os.path.exists(file_path):
            return False
        
        # 尝试加载NBT文件
        nbt_file = load_nbt_file(file_path, ignore_data_version)
        if nbt_file is None:
            return False
        
        # 检查基本结构
        if not isinstance(nbt_file, nbtlib.Compound):
            return False
        
        return True
        
    except Exception as e:
        logger.debug(f"验证NBT文件失败: {e}")
        return False


# DataVersion -> MC 版本（常用版本号，用于世界详情展示；优先使用 level.dat 中精确的 Version.Name）
WORLD_DATA_VERSION_MAP = [
    (2586, "1.16.5"), (2724, "1.17.1"), (2865, "1.18.2"), (2975, "1.19"),
    (3105, "1.19.3"), (3120, "1.19.4"), (3463, "1.20"), (3465, "1.20.1"),
    (3578, "1.20.2"), (3700, "1.20.4"), (3839, "1.20.6"), (3953, "1.21"),
    (3955, "1.21.1"), (4080, "1.21.3"), (4189, "1.21.4"), (4309, "1.21.5"),
    (4327, "1.21.6"), (4373, "1.21.7"), (4455, "1.21.8"), (4492, "1.21.9"),
    (4671, "1.21.11"),
]


def data_version_to_mc(data_version: int) -> str:
    """把 level.dat 的 DataVersion 映射为 MC 版本字符串"""
    exact = {v: n for v, n in WORLD_DATA_VERSION_MAP}
    if data_version in exact:
        return exact[data_version]
    nearest = None
    for v, name in WORLD_DATA_VERSION_MAP:
        if data_version >= v:
            nearest = name
    if nearest:
        return f"≈{nearest}（DataVersion {data_version}）"
    return f"DataVersion {data_version}"


def get_world_meta(world_path: str) -> dict:
    """提取世界存档展示信息：{name, version, description, icon_bytes, icon_fmt}
    版本优先取 level.dat 中精确的 Version.Name（如 1.21.11），
    其次用 Version.Id / DataVersion 映射到 MC 版本。"""
    meta = {"name": os.path.basename(os.path.normpath(world_path)),
            "version": "", "description": "", "icon_bytes": None, "icon_fmt": ""}
    try:
        nbt_file = File.load(os.path.join(world_path, "level.dat"), gzipped=True)
        data = nbt_file.get("Data", {})
        if isinstance(data, nbtlib.Compound):
            if "LevelName" in data:
                meta["name"] = str(data["LevelName"])
            ver = data.get("Version", {})
            if isinstance(ver, nbtlib.Compound) and "Name" in ver:
                meta["version"] = str(ver["Name"])            # 精确版本号
            elif isinstance(ver, nbtlib.Compound) and "Id" in ver:
                meta["version"] = data_version_to_mc(int(ver["Id"]))
            elif "DataVersion" in data:
                meta["version"] = data_version_to_mc(int(data["DataVersion"]))
    except Exception as e:
        get_logger().debug(f"读取世界元数据失败: {e}")
    # 世界图标 icon.png（游戏单人游戏列表显示的图标）
    icon = os.path.join(world_path, "icon.png")
    if os.path.exists(icon):
        try:
            with open(icon, "rb") as f:
                meta["icon_bytes"] = f.read()
                meta["icon_fmt"] = "png"
        except Exception as e:
            get_logger().debug(f"读取世界图标失败: {e}")
    return meta