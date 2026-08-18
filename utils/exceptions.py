# -*- coding: utf-8 -*-
"""
异常定义 - Exception Definitions
"""

class MCTError(Exception):
    """Minecraft汉化工具基础异常类"""
    
    def __init__(self, message: str = "", error_code: str = "UNKNOWN"):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
    
    def __str__(self):
        return f"[{self.error_code}] {self.message}"


class WorldValidationError(MCTError):
    """世界验证异常"""
    
    def __init__(self, message: str = "世界验证失败"):
        super().__init__(message, "WORLD_VALIDATION_ERROR")


class NBTReadError(MCTError):
    """NBT文件读取异常"""
    
    def __init__(self, message: str = "NBT文件读取失败"):
        super().__init__(message, "NBT_READ_ERROR")


class NBTWriteError(MCTError):
    """NBT文件写入异常"""
    
    def __init__(self, message: str = "NBT文件写入失败"):
        super().__init__(message, "NBT_WRITE_ERROR")


class ScanError(MCTError):
    """扫描异常"""
    
    def __init__(self, message: str = "文本扫描失败"):
        super().__init__(message, "SCAN_ERROR")


class TranslationError(MCTError):
    """翻译异常"""
    
    def __init__(self, message: str = "翻译失败"):
        super().__init__(message, "TRANSLATION_ERROR")


class ExportError(MCTError):
    """导出异常"""
    
    def __init__(self, message: str = "导出失败"):
        super().__init__(message, "EXPORT_ERROR")


class BackupError(MCTError):
    """备份异常"""
    
    def __init__(self, message: str = "备份失败"):
        super().__init__(message, "BACKUP_ERROR")


class ConfigError(MCTError):
    """配置异常"""
    
    def __init__(self, message: str = "配置错误"):
        super().__init__(message, "CONFIG_ERROR")


class FileNotFoundError(MCTError):
    """文件未找到异常"""
    
    def __init__(self, message: str = "文件未找到"):
        super().__init__(message, "FILE_NOT_FOUND")


class PermissionError(MCTError):
    """权限异常"""
    
    def __init__(self, message: str = "权限不足"):
        super().__init__(message, "PERMISSION_ERROR")


class ValidationError(MCTError):
    """验证异常"""
    
    def __init__(self, message: str = "验证失败"):
        super().__init__(message, "VALIDATION_ERROR")


class JSONValidationError(MCTError):
    """JSON验证异常"""
    
    def __init__(self, message: str = "JSON验证失败"):
        super().__init__(message, "JSON_VALIDATION_ERROR")


class NetworkError(MCTError):
    """网络异常"""
    
    def __init__(self, message: str = "网络错误"):
        super().__init__(message, "NETWORK_ERROR")


class ServiceUnavailableError(MCTError):
    """服务不可用异常"""
    
    def __init__(self, message: str = "服务不可用"):
        super().__init__(message, "SERVICE_UNAVAILABLE")


def handle_exception(func):
    """异常处理装饰器"""
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except MCTError:
            raise
        except FileNotFoundError as e:
            raise FileNotFoundError(str(e))
        except PermissionError as e:
            raise PermissionError(str(e))
        except Exception as e:
            from utils.logger import get_logger
            logger = get_logger()
            logger.error(f"未处理的异常: {e}", exc_info=True)
            raise MCTError(f"发生未知错误: {e}")
    
    return wrapper