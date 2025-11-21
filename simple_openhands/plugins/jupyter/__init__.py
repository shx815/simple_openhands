import asyncio
import os
import subprocess
import sys
import time
from dataclasses import dataclass

from simple_openhands.core import logger
from simple_openhands.events.action import Action, IPythonRunCellAction
from simple_openhands.events.observation import Observation, IPythonRunCellObservation
from .execute_server import JupyterKernel
from ..requirement import Plugin, PluginRequirement


def should_continue() -> bool:
    """Simple helper function to check if execution should continue."""
    return True


@dataclass
class JupyterRequirement(PluginRequirement):
    name: str = 'jupyter'


class JupyterPlugin(Plugin):
    name: str = 'jupyter'
    kernel_gateway_port: int
    kernel_id: str
    gateway_process: asyncio.subprocess.Process | subprocess.Popen
    python_interpreter_path: str

    async def initialize(
        self, username: str, kernel_id: str = 'simple_openhands-default'
    ) -> None:
        # 使用固定端口，避免防火墙问题
        self.kernel_gateway_port = int(os.environ.get('JUPYTER_PORT', '8001'))
        
        # 验证端口是否在合理范围内
        if not (1024 <= self.kernel_gateway_port <= 65535):
            raise ValueError(f"Invalid JUPYTER_PORT: {self.kernel_gateway_port}. Port must be between 1024 and 65535.")
        
        self.kernel_id = kernel_id
        is_local_runtime = os.environ.get('LOCAL_RUNTIME_MODE') == '1'
        is_windows = sys.platform == 'win32'

        if not is_local_runtime:
            # Non-LocalRuntime: 直接以当前用户运行，在 micromamba env + poetry venv 中启动
            if is_windows:
                code_repo_path = 'C:\\simple_openhands\\code'  # Windows container path
            else:
                code_repo_path = '/simple_openhands/code'  # Unix container path
            poetry_prefix = (
                        'cd /simple_openhands/code\n'
        'export POETRY_VIRTUALENVS_PATH=/simple_openhands/poetry;\n'
        'export PYTHONPATH=/simple_openhands/code:/simple_openhands/code/simple_openhands:$PYTHONPATH;\n'
        'export MAMBA_ROOT_PREFIX=/simple_openhands/micromamba;\n'
        '/simple_openhands/micromamba/bin/micromamba run -n simple_openhands poetry run '
            )
        else:
            # LocalRuntime
            prefix = ''
            code_repo_path = os.environ.get('SIMPLE_OPENHANDS_REPO_PATH')
            if not code_repo_path:
                raise ValueError(
                    'SIMPLE_OPENHANDS_REPO_PATH environment variable is not set. '
                    'This is required for the jupyter plugin to work with LocalRuntime.'
                )
            # The correct environment is ensured by the PATH in LocalRuntime.
            poetry_prefix = f'cd {code_repo_path}\n'

        if is_windows:
            # Windows-specific command format
            if not is_local_runtime:
                # For non-local runtime, use the same approach as OpenHands official implementation
                jupyter_launch_command = (
                    f'cd /d "{code_repo_path}" && '
                    f'"{sys.executable}" -m jupyter kernelgateway '
                    '--KernelGatewayApp.ip=0.0.0.0 '
                    f'--KernelGatewayApp.port={self.kernel_gateway_port}'
                )
            else:
                # For local runtime, use the same approach as OpenHands official implementation
                jupyter_launch_command = (
                    f'cd /d "{code_repo_path}" && '
                    f'"{sys.executable}" -m jupyter kernelgateway '
                    '--KernelGatewayApp.ip=0.0.0.0 '
                    f'--KernelGatewayApp.port={self.kernel_gateway_port}'
                )
            logger.debug(f'Jupyter launch command (Windows): {jupyter_launch_command}')

            # Using synchronous subprocess.Popen for Windows as asyncio.create_subprocess_shell
            # has limitations on Windows platforms
            self.gateway_process = subprocess.Popen(  # type: ignore[ASYNC101] # noqa: ASYNC101
                jupyter_launch_command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                shell=True,
                text=True,
                bufsize=0,  # 无缓冲
                universal_newlines=True,
            )

            # Windows-specific stdout handling with timeout and proper detection
            output = ''
            max_wait_time = 60  # 最多等待60秒
            start_time = time.time()
            
            while should_continue() and (time.time() - start_time) < max_wait_time:
                if self.gateway_process.stdout is None:
                    time.sleep(0.5)
                    continue

                line = self.gateway_process.stdout.readline()
                if not line:
                    time.sleep(0.5)
                    continue

                output += line
                logger.debug(f'Jupyter output: {line.strip()}')
                
                # Use OpenHands' simple detection approach
                if 'at' in line:
                    logger.info(f'Jupyter kernel gateway started successfully, detected: {line.strip()}')
                    break

                # 减少sleep时间，加快检测速度
                time.sleep(0.1)
            
            # 检查是否超时
            if (time.time() - start_time) >= max_wait_time:
                logger.warning(f'Jupyter server startup timed out after {max_wait_time} seconds')
                logger.warning(f'Captured output so far: {output}')
                # 尝试直接连接端口验证服务是否真的启动了
                import socket
                try:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    result = sock.connect_ex(('127.0.0.1', self.kernel_gateway_port))
                    sock.close()
                    if result == 0:
                        logger.info(f'Jupyter server is actually running on port {self.kernel_gateway_port}, output detection failed but port is accessible')
                    else:
                        logger.error(f'Jupyter server is not running on port {self.kernel_gateway_port}')
                except Exception as e:
                    logger.error(f'Failed to check port {self.kernel_gateway_port}: {e}')
                # 继续执行，不要因为超时而失败

            logger.debug(
                f'Jupyter kernel gateway started at port {self.kernel_gateway_port}. Output: {output}'
            )
        else:
            # Unix systems (Linux/macOS)
            # 使用 jupyter kernelgateway（更轻量、更稳定），参考 OpenHands 官方实现
            jupyter_launch_command = (
                "/bin/bash << 'EOF'\n"
                f"{poetry_prefix}"
                f'"{sys.executable}" -m jupyter kernelgateway '
                '--KernelGatewayApp.ip=0.0.0.0 '
                f'--KernelGatewayApp.port={self.kernel_gateway_port}\n'
                'EOF'
            )
            logger.debug(f'Jupyter launch command: {jupyter_launch_command}')

            # Using asyncio.create_subprocess_shell instead of subprocess.Popen
            # to avoid ASYNC101 linting error
            self.gateway_process = await asyncio.create_subprocess_shell(
                jupyter_launch_command,
                stderr=asyncio.subprocess.STDOUT,
                stdout=asyncio.subprocess.PIPE,
            )
            # read stdout until the kernel gateway is ready
            output = ''
            while should_continue() and self.gateway_process.stdout is not None:
                line_bytes = await self.gateway_process.stdout.readline()
                line = line_bytes.decode('utf-8')
                output += line
                if 'at' in line:
                    break
                await asyncio.sleep(1)
                logger.debug('Waiting for jupyter kernel gateway to start...')

            logger.debug(
                f'Jupyter kernel gateway started at port {self.kernel_gateway_port}. Output: {output}'
            )

        # 测试Jupyter服务器是否正常工作
        try:
            _obs = await self._run(
                IPythonRunCellAction(code='import sys; print(sys.executable)')
            )
            self.python_interpreter_path = _obs.content.strip()
            logger.info(f"Jupyter plugin initialized successfully. Python path: {self.python_interpreter_path}")
        except Exception as e:
            logger.error(f"Failed to test Jupyter plugin: {e}")
            raise

    async def _run(self, action: Action) -> IPythonRunCellObservation:
        """Internal method to run a code cell in the jupyter kernel."""
        if not isinstance(action, IPythonRunCellAction):
            raise ValueError(
                f'Jupyter plugin only supports IPythonRunCellAction, but got {action}'
            )

        if not hasattr(self, 'kernel'):
            self.kernel = JupyterKernel(
                f'localhost:{self.kernel_gateway_port}', self.kernel_id
            )

        if not self.kernel.initialized:
            await self.kernel.initialize()

        # Execute the code and get structured output
        output = await self.kernel.execute(action.code, timeout=action.timeout)

        # Extract text content and image URLs from the structured output
        text_content = output.get('text', '')
        image_urls = output.get('images', [])

        return IPythonRunCellObservation(
            content=text_content,
            code=action.code,
            image_urls=image_urls if image_urls else None,
        )

    async def run(self, action: Action) -> IPythonRunCellObservation:
        """Execute Python code in Jupyter kernel"""
        try:
            obs = await self._run(action)
            return obs
        except Exception as e:
            logger.error(f"Error executing Python code: {e}")
            # 返回错误观察结果而不是抛出异常
            return IPythonRunCellObservation(
                content=f"Error executing code: {str(e)}",
                code=action.code if hasattr(action, 'code') else "unknown",
                image_urls=None,
            )
