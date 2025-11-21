#!/usr/bin/env python3
"""
Simple Docker Runtime - FastAPI Server
使用完全移植的原始bash.py
"""

import os
import sys
import asyncio
import getpass
import subprocess
import traceback
import time
from contextlib import asynccontextmanager
from typing import Optional, Dict

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from simple_openhands.models import ServerInfo
from pydantic import BaseModel
# 根据平台选择合适的bash实现
if sys.platform == 'win32':
    try:
        from simple_openhands.windows_bash import WindowsPowershellSession
        BashSession = WindowsPowershellSession
    except Exception as e:
        print(f"Warning: Windows PowerShell not available: {e}")
        print("Service will start without command execution functionality")
        BashSession = None
else:
    from simple_openhands.bash import BashSession
from simple_openhands.events.action import CmdRunAction, FileReadAction, FileWriteAction, FileEditAction, IPythonRunCellAction
from simple_openhands.events.observation import CmdOutputObservation, FileReadObservation, FileWriteObservation, FileEditObservation, IPythonRunCellObservation
from simple_openhands.utils.system_stats import get_system_stats
from simple_openhands.utils.file.file_viewer import generate_file_viewer_html

from simple_openhands.plugins import ALL_PLUGINS, JupyterPlugin, VSCodePlugin
from simple_openhands.events.serialization import event_from_dict, event_to_dict

# 全局变量
bash_session: Optional[BashSession] = None
# 已初始化的插件实例注册表
PLUGIN_INSTANCES: Dict[str, object] = {}

async def _init_jupyter_async(username: str, timeout_seconds: float = 60.0) -> None:
    """Initialize Jupyter plugin in background with timeout, without blocking app start."""
    try:
        print(f"Starting Jupyter plugin async initialization (timeout {timeout_seconds}s)...")
        jupyter_plugin = JupyterPlugin()
        await asyncio.wait_for(jupyter_plugin.initialize(username), timeout=timeout_seconds)
        PLUGIN_INSTANCES["jupyter"] = jupyter_plugin
        print("Jupyter plugin auto-initialized successfully (async)")
    except asyncio.TimeoutError:
        print("Warning: Jupyter plugin initialization timed out; will initialize lazily on first use")
    except Exception as e:
        print(f"Warning: Jupyter plugin async initialization failed: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理 - 使用OpenHands的分散式平台检测模式"""
    global bash_session

    # 检查是否有可用的bash实现
    if BashSession is None:
        print("Warning: No suitable bash session class found for current platform")
        bash_session = None
        yield
        return

    # 根据平台设置工作目录
    if sys.platform == 'win32':
        work_dir = os.environ.get('WORK_DIR', 'C\\simple_openhands\\workspace')
    else:
        work_dir = os.environ.get('WORK_DIR', '/simple_openhands/workspace')
    
    username = os.environ.get('USERNAME', getpass.getuser())

    # 确保工作目录存在
    os.makedirs(work_dir, exist_ok=True)

    try:
        bash_session = BashSession(
            work_dir=work_dir, 
            username=username,
            no_change_timeout_seconds=120  # 增加到120秒，支持长时间运行的编译命令
        )
        # Windows PowerShell不需要initialize，Linux bash需要
        if hasattr(bash_session, 'initialize'):
            bash_session.initialize()
        print(f"Bash session initialized in {work_dir} as user {username}")
        # 强制将会话目录切换到工作目录，避免不一致
        try:
            bash_session.execute(CmdRunAction(command=f'cd {work_dir}', cwd=work_dir, is_static=True, hidden=True))
        except Exception:
            pass
        # 自动初始化Git仓库并设置safe.directory，避免“dubious ownership”问题
        try:
            current_cwd = getattr(bash_session, 'cwd', work_dir)
            # 配置基础git用户信息（幂等）
            bash_session.execute(CmdRunAction(command='git config --global user.name "simple_openhands"', cwd=current_cwd, is_static=True, hidden=True))
            bash_session.execute(CmdRunAction(command='git config --global user.email "simple_openhands@example.com"', cwd=current_cwd, is_static=True, hidden=True))
            # 若非git仓库则初始化（幂等）
            bash_session.execute(CmdRunAction(command='git rev-parse --is-inside-work-tree || git init', cwd=current_cwd, is_static=True, hidden=True))
            # 设置safe.directory，避免挂载目录所有权不一致导致的报错（幂等，可重复添加）
            bash_session.execute(CmdRunAction(command=f'git config --global --add safe.directory "{current_cwd}"', cwd=current_cwd, is_static=True, hidden=True))
        except Exception as e:
            print(f"Git auto-setup skipped: {e}")
    except Exception as e:
        print(f"Failed to initialize bash session: {e}")
        bash_session = None

    # 自动初始化核心插件（非阻塞地启动 Jupyter 初始化，避免阻塞应用启动）
    if bash_session:
        try:
            # kick off async Jupyter init with timeout; server can serve /alive before it completes
            asyncio.create_task(_init_jupyter_async(username))
        except Exception as e:
            print(f"Failed to schedule Jupyter initialization: {e}")

        # AgentSkills插件无需初始化，函数立即可用
        print("AgentSkills plugin functions are always available (no initialization needed)")

    yield

    # 关闭时清理
    if bash_session:
        bash_session.close()

# 创建FastAPI应用
app = FastAPI(
    title="Simple Docker Runtime",
    description="基于OpenHands的完整bash.py实现的Docker运行时",
    version="1.0.0",
    lifespan=lifespan
)

# 添加CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """全局异常处理器"""
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "detail": str(exc),
            "type": type(exc).__name__
        }
    )

@app.get("/")
async def root():
    """根路径"""
    return {"message": "Simple Docker Runtime API", "version": "1.0.0"}

@app.get("/alive")
async def alive_check():
    """健康检查端点"""
    bash_active = False
    if bash_session is not None:
        # Windows PowerShell和Linux bash的初始化状态检查方式不同
        if hasattr(bash_session, '_initialized'):
            bash_active = bash_session._initialized
        elif hasattr(bash_session, '_closed'):
            bash_active = not bash_session._closed
    
    return {"status": "alive", "bash_session_active": bash_active}

@app.get("/server_info", response_model=ServerInfo)
async def get_server_info():
    """获取服务器信息"""
    # 根据平台设置默认工作目录
    if sys.platform == 'win32':
        work_dir = os.environ.get('WORK_DIR', 'C\\simple_openhands\\workspace')
    else:
        work_dir = os.environ.get('WORK_DIR', '/simple_openhands/workspace')
    
    username = os.environ.get('USERNAME', getpass.getuser())

    cwd = work_dir
    if bash_session and hasattr(bash_session, '_initialized') and bash_session._initialized:
        try:
            cwd = bash_session.cwd
        except Exception:
            pass

    # 获取系统统计信息
    try:
        resources = get_system_stats()
    except Exception as e:
        resources = {"error": f"Failed to get system stats: {str(e)}"}

    return ServerInfo(
        status="running",
        version="1.0.0",
        cwd=cwd,
        username=username,
        resources=resources
    )


@app.get("/system/stats")
async def get_system_stats_api():
    """获取系统统计信息
    
    基于你已有的get_system_stats函数，提供专业的系统统计API
    """
    try:
        stats = get_system_stats()
        return {
            "status": "success",
            "system_stats": stats,
            "timestamp": time.time()
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get system stats: {str(e)}"
        )



@app.post("/reset")
async def reset_session():
    """重置bash session"""
    global bash_session

    if bash_session:
        bash_session.close()

    # 根据平台设置工作目录
    if sys.platform == 'win32':
        work_dir = os.environ.get('WORK_DIR', 'C\\simple_openhands\\workspace')
    else:
        work_dir = os.environ.get('WORK_DIR', '/simple_openhands/workspace')
    
    username = os.environ.get('USERNAME', getpass.getuser())

    try:
        bash_session = BashSession(
            work_dir=work_dir, 
            username=username,
            no_change_timeout_seconds=120  # 增加到120秒，支持长时间运行的编译命令
        )
        # Windows PowerShell不需要initialize，Linux bash需要
        if hasattr(bash_session, 'initialize'):
            bash_session.initialize()
        return {"message": "Bash session reset successfully"}
    except Exception as e:
        bash_session = None
        raise HTTPException(
            status_code=500,
            detail=f"Failed to reset bash session: {str(e)}"
        )



# 移除独立的文件操作API端点，统一通过 /execute_action 处理
# 参考 OpenHands 的架构设计

@app.get("/view-file")
async def view_file(path: str):
    """查看文件内容"""
    try:
        if not os.path.isabs(path):
            raise HTTPException(status_code=400, detail="Path must be absolute")
        
        if not os.path.exists(path):
            raise HTTPException(status_code=404, detail="File not found")
        
        if os.path.isdir(path):
            raise HTTPException(status_code=400, detail="Path is a directory")
        
        html_content = generate_file_viewer_html(path)
        return HTMLResponse(content=html_content)
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error viewing file: {str(e)}")


@app.get("/vscode/connection_token")
async def get_vscode_connection_token():
    """获取VSCode连接令牌
    
    基于OpenHands的VSCode插件API，提供连接令牌
    """
    plugin = PLUGIN_INSTANCES.get("vscode")
    if plugin is None or not isinstance(plugin, VSCodePlugin):
        raise HTTPException(
            status_code=400, 
            detail="VSCode plugin is not initialized. Call /plugins/vscode/initialize first."
        )
    
    try:
        # 直接访问插件的属性，就像OpenHands做的那样
        token = plugin.vscode_connection_token
        if not token:
            raise HTTPException(
                status_code=400,
                detail="VSCode plugin not properly initialized or token not available"
            )
        return {
            "status": "success",
            "connection_token": token,
            "note": "Use this token to connect VSCode to the runtime"
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get VSCode connection token: {str(e)}"
        )

@app.get("/vscode-url")
async def get_vscode_url():
    """获取VSCode连接URL
    
    基于OpenHands的VSCode插件API，提供连接URL
    """
    plugin = PLUGIN_INSTANCES.get("vscode")
    if plugin is None or not isinstance(plugin, VSCodePlugin):
        raise HTTPException(
            status_code=400, 
            detail="VSCode plugin is not initialized. Call /plugins/vscode/initialize first."
        )
    
    try:
        # 直接构建URL，就像OpenHands做的那样
        token = plugin.vscode_connection_token
        port = plugin.vscode_port
        if not token or not port:
            raise HTTPException(
                status_code=400,
                detail="VSCode plugin not properly initialized or token/port not available"
            )
        
        # 构建VSCode URL，使用localhost（容器内访问）
        vscode_url = f"http://localhost:{port}/?tkn={token}&folder={_default_work_dir()}"
        
        return {
            "status": "success",
            "vscode_url": vscode_url,
            "note": "Use this URL to open VSCode in browser or connect desktop VSCode"
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get VSCode URL: {str(e)}"
        )

@app.get("/plugins")
async def get_plugins():
    """获取可用插件列表和状态"""
    plugin_status = {}
    
    for name, plugin_class in ALL_PLUGINS.items():
        if name == "jupyter":
            # Jupyter自动初始化
            status = "auto_initialized" if name in PLUGIN_INSTANCES else "auto_initializing"
            note = "Auto-initializes on startup"
        elif name == "agent_skills":
            # AgentSkills无需初始化
            status = "always_available"
            note = "Function collection, no initialization needed"
        else:
            # 其他插件需要手动初始化
            status = "initialized" if name in PLUGIN_INSTANCES else "not_initialized"
            note = "Requires manual initialization"
        
        plugin_status[name] = {
            "name": plugin_class.name,
            "type": plugin_class.__name__,
            "status": status,
            "note": note
        }
    
    return {
        "available_plugins": list(ALL_PLUGINS.keys()),
        "plugin_count": len(ALL_PLUGINS),
        "plugins": plugin_status,
        "summary": {
            "auto_initialized": len([p for p in plugin_status.values() if p["status"] == "auto_initialized"]),
            "always_available": len([p for p in plugin_status.values() if p["status"] == "always_available"]),
            "manual_required": len([p for p in plugin_status.values() if p["status"] in ["initialized", "not_initialized"]])
        }
    }


@app.post("/plugins/{plugin_name}/initialize")
async def initialize_plugin(plugin_name: str, username: str = "simple_openhands"):
    """初始化指定插件
    
    注意：
    - Jupyter插件会在服务启动时自动初始化，无需手动初始化
    - AgentSkills插件是函数集合，无需初始化，可直接使用
    - 只有VSCode等需要运行时状态的插件需要手动初始化
    """
    if plugin_name not in ALL_PLUGINS:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_name}' not found")
    
    # 检查插件类型
    if plugin_name == "jupyter":
        raise HTTPException(
            status_code=400, 
            detail="Jupyter plugin auto-initializes on startup, no manual initialization needed"
        )
    
    if plugin_name == "agent_skills":
        raise HTTPException(
            status_code=400, 
            detail="AgentSkills plugin is a function collection, no initialization needed. Functions can be called directly in Python code."
        )
    
    try:
        plugin_class = ALL_PLUGINS[plugin_name]
        plugin_instance = plugin_class()
        await plugin_instance.initialize(username)
        # 保存实例，供后续调用
        PLUGIN_INSTANCES[plugin_name] = plugin_instance
        return {
            "status": "success",
            "plugin": plugin_name,
            "message": f"Plugin '{plugin_name}' initialized successfully",
            "note": "This plugin requires manual initialization"
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to initialize plugin '{plugin_name}': {str(e)}"
        )


class ActionRequest(BaseModel):
    action: dict




@app.post("/execute_action")
async def execute_action(action_request: ActionRequest):
    """执行 OpenHands Action - 支持所有 Action 类型"""
    if not bash_session:
        raise HTTPException(
            status_code=503,
            detail="Bash session not available. Please check server status."
        )

    # 兼容Windows PowerShell和Linux bash的初始化状态检查
    bash_ready = False
    if hasattr(bash_session, '_initialized'):
        bash_ready = bash_session._initialized
    elif hasattr(bash_session, '_closed'):
        bash_ready = not bash_session._closed
    else:
        # 如果没有这些属性，假设bash session是可用的
        bash_ready = True

    if not bash_ready:
        raise HTTPException(
            status_code=503,
            detail="Bash session not ready. Please check server status."
        )

    try:
        # 从字典创建 Action 对象 - 直接传递 action_request.action
        action = event_from_dict(action_request.action)
        
        # 根据 Action 类型执行相应的操作
        if isinstance(action, CmdRunAction):
            # 执行 bash 命令
            observation = bash_session.execute(action)
            return event_to_dict(observation)
            
        elif isinstance(action, IPythonRunCellAction):
            # 执行 Python 代码 - Jupyter自动可用
            plugin = PLUGIN_INSTANCES.get("jupyter")
            if plugin is None or not isinstance(plugin, JupyterPlugin):
                # 如果Jupyter未初始化，自动初始化
                try:
                    print("Auto-initializing Jupyter plugin...")
                    jupyter_plugin = JupyterPlugin()
                    await jupyter_plugin.initialize("simple_openhands")
                    PLUGIN_INSTANCES["jupyter"] = jupyter_plugin
                    plugin = jupyter_plugin
                    print("Jupyter plugin auto-initialized successfully")
                except Exception as e:
                    print(f"Failed to auto-initialize Jupyter plugin: {e}")
                    raise HTTPException(status_code=500, detail=f"Failed to auto-initialize Jupyter: {str(e)}")
            
            try:
                observation = await plugin.run(action)
                return event_to_dict(observation)
            except Exception as e:
                print(f"Error executing Python code: {e}")
                # 返回错误观察结果
                error_obs = IPythonRunCellObservation(
                    content=f"Error executing Python code: {str(e)}",
                    code=action.code,
                    image_urls=None,
                )
                return event_to_dict(error_obs)
            
        elif isinstance(action, FileReadAction):
            # 读取文件
            observation = await read_file_action(action)
            return event_to_dict(observation)
            
        elif isinstance(action, FileWriteAction):
            # 写入文件
            observation = await write_file_action(action)
            return event_to_dict(observation)
            
        elif isinstance(action, FileEditAction):
            # 编辑文件
            observation = await edit_file_action(action)
            return event_to_dict(observation)
            
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported action type: {type(action).__name__}")
            
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "error": str(e),
                "traceback": traceback.format_exc()
            }
        )

async def read_file_action(action: FileReadAction) -> FileReadObservation:
    """读取文件内容"""
    if not bash_session:
        raise HTTPException(status_code=503, detail="Bash session not available")
    
    working_dir = bash_session.cwd
    filepath = action.path if os.path.isabs(action.path) else os.path.join(working_dir, action.path)
    
    try:
        if not os.path.exists(filepath):
            return FileReadObservation(
                content=f"File not found: {filepath}. Your current working directory is {working_dir}.",
                path=filepath
            )
        
        if os.path.isdir(filepath):
            return FileReadObservation(
                content=f"Path is a directory: {filepath}. You can only read files",
                path=filepath
            )
        
        # 读取文件内容
        with open(filepath, 'r', encoding='utf-8') as file:
            content = file.read()
            
        return FileReadObservation(
            content=content,
            path=filepath
        )
        
    except Exception as e:
        return FileReadObservation(
            content=f"Error reading file {filepath}: {str(e)}",
            path=filepath
        )

async def write_file_action(action: FileWriteAction) -> FileWriteObservation:
    """写入文件内容"""
    if not bash_session:
        raise HTTPException(status_code=503, detail="Bash session not available")
    
    working_dir = bash_session.cwd
    filepath = action.path if os.path.isabs(action.path) else os.path.join(working_dir, action.path)
    
    try:
        # 确保目录存在
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        
        # 写入文件
        with open(filepath, 'w', encoding='utf-8') as file:
            file.write(action.content)
            
        return FileWriteObservation(
            content="File written successfully",
            path=filepath
        )
        
    except Exception as e:
        return FileWriteObservation(
            content=f"Error writing file {filepath}: {str(e)}",
            path=filepath
        )

async def edit_file_action(action: FileEditAction) -> FileEditObservation:
    """编辑文件内容"""
    if not bash_session:
        raise HTTPException(status_code=503, detail="Bash session not available")
    
    working_dir = bash_session.cwd
    filepath = action.path if os.path.isabs(action.path) else os.path.join(working_dir, action.path)
    
    try:
        if not os.path.exists(filepath):
            return FileEditObservation(
                content=f"File not found: {filepath}",
                path=filepath
            )
        
        # 读取原文件内容
        with open(filepath, 'r', encoding='utf-8') as file:
            old_content = file.read()
        
        # 执行编辑操作
        if action.command == "str_replace" and action.old_str and action.new_str:
            new_content = old_content.replace(action.old_str, action.new_str)
        else:
            new_content = old_content
        
        # 写入新内容
        with open(filepath, 'w', encoding='utf-8') as file:
            file.write(new_content)
            
        return FileEditObservation(
            content="File edited successfully",
            path=filepath,
            old_content=action.old_str,
            new_content=action.new_str
        )
        
    except Exception as e:
        return FileEditObservation(
            content=f"Error editing file {filepath}: {str(e)}",
            path=filepath
        )

def main():
    """主函数"""
    # 从环境变量获取配置
    host = os.environ.get('HOST', '0.0.0.0')
    port = int(os.environ.get('PORT', '8000'))

    # 根据平台设置默认工作目录
    if sys.platform == 'win32':
        default_work_dir = 'C\\simple_openhands\\workspace'
    else:
        default_work_dir = '/simple_openhands/workspace'

    print(f"Starting Simple Docker Runtime on {host}:{port}")
    print(f"Platform: {'Windows' if sys.platform == 'win32' else 'Linux/Unix'}")
    print(f"Work directory: {os.environ.get('WORK_DIR', default_work_dir)}")
    print(f"Username: {os.environ.get('USERNAME', getpass.getuser())}")

    # 运行服务器
    uvicorn.run(
        "simple_openhands.main:app",
        host=host,
        port=port,
        reload=False,
        log_level="info"
    )

if __name__ == "__main__":
    main()