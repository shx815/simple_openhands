"""Platform detection and compatibility management for simple_openhands."""

import sys
import os
from typing import Union, List, Optional

def get_platform() -> str:
    """获取当前平台 - 使用OpenHands的标准方式"""
    if sys.platform == 'win32':
        return "windows"
    elif sys.platform.startswith("linux"):
        return "linux"
    else:
        return "unknown"

def is_windows() -> bool:
    """检查是否为Windows平台 - 与OpenHands保持一致"""
    return sys.platform == 'win32'

def is_linux() -> bool:
    """检查是否为Linux平台"""
    return sys.platform.startswith("linux")

def get_bash_session_class():
    """根据平台获取合适的bash会话类 - 参考OpenHands的实现"""
    if is_windows():
        try:
            from ..windows_bash import WindowsPowershellSession
            return WindowsPowershellSession
        except ImportError as e:
            print(f"Warning: Windows PowerShell not available: {e}")
            return None
    else:
        from ..bash import BashSession
        return BashSession

def get_platform_specific_config():
    """获取平台特定的配置 - 参考OpenHands的环境变量处理"""
    if is_windows():
        return {
            "env_var_prefix": "$env:",
            "path_separator": "\\",
            "shell_type": "powershell",
            "work_dir": "C:\\workspace",
            "test_dir": "C:\\simple_openhands\\code\\tests",
            "micromamba_path": "C:\\simple_openhands\\micromamba\\bin\\micromamba.exe",
            "poetry_path": "C:\\simple_openhands\\micromamba\\envs\\simple_openhands\\Scripts\\poetry.exe"
        }
    else:
        return {
            "env_var_prefix": "export ",
            "path_separator": "/",
            "shell_type": "bash",
            "work_dir": "/workspace",
            "test_dir": "/simple_openhands/code/tests",
            "micromamba_path": "/simple_openhands/micromamba/bin/micromamba",
            "poetry_path": "/simple_openhands/micromamba/envs/simple_openhands/bin/poetry"
        }

def check_platform_compatibility() -> bool:
    """检查平台兼容性"""
    platform_type = get_platform()
    
    if platform_type == "windows":
        try:
            import pythonnet
            return True
        except ImportError:
            print("Warning: pythonnet not available on Windows")
            return False
    elif platform_type == "linux":
        try:
            import libtmux
            return True
        except ImportError:
            print("Warning: libtmux not available on Linux")
            return False
    else:
        print(f"Warning: Unknown platform: {platform_type}")
        return False

def get_platform_paths():
    """获取平台特定的路径配置"""
    return get_platform_specific_config()
