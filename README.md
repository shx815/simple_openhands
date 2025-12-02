# Simple Linux Docker Runtime

[Windows 版本说明请点击这里 → README-Windows.md](README-Windows.md)

基于 OpenHands 的 runtime 代码创建的 Docker 容器，提供 FastAPI 接口来执行 Bash 命令与插件功能。

## 主要功能

### **核心功能**

#### **1. Bash 命令执行系统**
- 执行 bash 命令
- 支持交互式操作

#### **2. Python 代码执行引擎**
- Jupyter Kernel Gateway 集成（自动初始化）
- 基于 Jupyter Kernel 的代码执行环境，支持状态保持
- 支持文本和PNG图片输出

#### **3. 文件操作管理系统**
- 文件读取、写入、编辑
- 文件内容查看（支持 PDF、PNG、JPG、JPEG、GIF）

#### **4. 系统监控与诊断**
- 服务器状态监控
- 资源使用统计（CPU、内存、磁盘、I/O）
- 系统健康检查

#### **5. 插件管理系统**
- **Jupyter 插件**：自动初始化，提供 Python 执行环境
- **AgentSkills 插件**：立即可用，提供文件操作、搜索、PDF/DOCX/LaTeX/PPTX解析等技能
- **VSCode 插件**：手动初始化，提供VSCode开发环境（基于OpenVSCode服务器）
---

## oh-run CLI 工具（推荐）

**什么是 oh-run？**

`oh-run` 是一个命令行工具，让你可以用oh-run 'bash command' 命令与 simple_openhands 运行时交互，无需手动编写复杂的 curl 和 JSON。

**对比示例：**
```bash
# 不用 oh-run：需要写冗长的 curl 命令
curl -X POST "http://localhost:8000/execute_action" \
  -H "Content-Type: application/json" \
  -d '{"action":{"action":"run","args":{"command":"pwd"}}}'

# 使用 oh-run：简洁明了
oh-run 'pwd'
```

#### 安装方法（使用虚拟环境）

```bash
# 1. 以 micromamba 创建环境为例（推荐，或根据需要使用 conda）
micromamba create -n oh-run python=3.12 -y
micromamba activate oh-run

# 2. 安装 oh-run 工具（只需做一次）
cd simple_openhands
pip install '.[cli]'

# 3. 每次新开终端都需要激活环境后使用
micromamba activate oh-run
```

#### 配置运行时地址（必需）

安装后，配置 oh-run 要连接的运行时地址：

```bash
# 通过环境变量（推荐）
export OH_API_URL=http://127.0.0.1:8002
# 或者使用命令行参数 
oh-run --url http://127.0.0.1:8002 'pwd'
```

#### 使用示例

**基础用法：**
```bash
# 执行简单命令
oh-run 'pwd'
oh-run 'ls -la'
oh-run 'whoami'
```

**高级用法：**
```bash
# 添加思考注释（方便调试）
oh-run --thought '列出项目文件' 'ls -la'

# 设置超时时间（秒）
oh-run --timeout 120 'find / -name "*.log"'

# 阻塞命令
oh-run --blocking 'sleep 10'

# 输出原始 JSON（调试用）
oh-run --raw 'uname -a'

# 指定 API URL
oh-run --url http://127.0.0.1:8002 'pwd'

# 检查服务器上下文
oh-run --context

# 组合使用
oh-run --url http://127.0.0.1:8002 --timeout 300 --thought '安装依赖' 'pip install requests'
```

**Python 代码执行：**
```bash
# 执行 Python 代码（使用 --python 参数）
oh-run --python 'print("Hello, World!")' 

# 执行多行 Python 代码
oh-run --python 'import os; print(os.getcwd())'

# 带思考注释
oh-run --python --thought '测试Python环境' 'import sys; print(sys.version)'

# 或者使用标准库的示例（无需安装额外依赖）
oh-run --python 'import json; data = {"name": "test", "value": 123}; print(json.dumps(data, indent=2))'
```

**并行任务场景：**

如果你有多个运行时实例（如多个容器），可以为每个终端/会话设置不同的环境变量：

```bash
# 终端 1 - 连接到运行时 A
export OH_API_URL=http://127.0.0.1:8002
oh-run 'pwd'

# 终端 2 - 连接到运行时 B
export OH_API_URL=http://127.0.0.1:9002
oh-run 'pwd'
```

## 用户使用指南

### 1. 环境部署

#### 方式一：一键部署脚本（推荐）
```bash
# 进入项目目录
cd simple_openhands

# 给脚本执行权限
chmod +x deploy.sh

# 运行部署脚本,启动容器时默认使用8000、3000、8001三个端口
./deploy.sh 
```

#### 方式二：手动部署
```bash
# 进入项目目录
cd simple_openhands

# 构建 Docker 镜像
docker build -t simple-openhands .

# 启动容器
docker run -d --name simple-openhands \
  -p 8002:8000 -p 3001:3000 -p 8001:8001 \
  -v "$(pwd)/workspace:/simple_openhands/workspace" \
  -e WORK_DIR=/simple_openhands/workspace \
  simple-openhands

# 挂载目录可自定义
# 启用文件日志（可选）
# 添加 -e LOG_TO_FILE=true 环境变量，日志会写入到 /simple_openhands/code/logs/simple_openhands_YYYY-MM-DD.log
docker run -d --name simple-openhands \
  -p 8002:8000 -p 3001:3000 -p 8001:8001 \
  -v "$(pwd)/workspace:/simple_openhands/workspace" \
  -e WORK_DIR=/simple_openhands/workspace \
  -e LOG_TO_FILE=true \
  simple-openhands

# 端口说明：
# -p 8002:8000          # 主API服务端口，提供所有API接口
# -p 3001:3000          # VSCode服务器端口，用于Web版VSCode访问
# -p 8001:8001          # Jupyter端口，用于Python代码执行

# 查看启动日志
docker logs -f simple-openhands
```

### 2. API 接口使用

#### 基础服务 API

**健康检查**
```bash
# 检查服务是否存活
curl http://localhost:8002/alive

# 获取服务器详细信息
curl http://localhost:8002/server_info
# 或者使用oh-run
oh-run --context

# 访问根路径
curl http://localhost:8002/
```

**系统监控**
```bash
# 获取系统资源统计
curl http://localhost:8002/system/stats

# 重置 bash session
curl -X POST "http://localhost:8002/reset"
```

#### execute_action 统一接口

**标准命令格式**

所有操作都通过 `/execute_action` 端点执行，使用统一的JSON格式。以下是完整的命令结构说明：

```json
{
  "action": {
    "action": "action_type",          // 动作类型：run(命令执行)、run_ipython(Python代码)、read(文件读取)、write(文件写入)、edit(文件编辑)
    "args": {                         // 动作参数，根据动作类型不同而不同
      "command": "pwd",               // 命令执行：要执行的bash命令
      "code": "print('Hello')",       // Python执行：要执行的Python代码
      "path": "/path/to/file",        // 文件操作：文件路径
      "content": "file content",      // 文件写入/编辑：文件内容
      "thought": "执行原因说明",       // 可选：执行此动作的思考过程
      "start": 1,                     // 文件编辑：起始行号(1-indexed)
      "end": -1,                      // 文件编辑：结束行号(-1表示文件末尾)
      "command": "str_replace",       // 文件编辑：编辑命令(str_replace, insert等)
      "old_str": "old text",          // 文件编辑：要替换的旧字符串
      "new_str": "new text"           // 文件编辑：新的字符串
    }
  }
}
```

**标准响应格式 (Observation)：**

系统支持多种响应类型，所有响应都使用统一的JSON结构，与action格式保持一致：

```json
{
  "observation": "observation_type",  // 响应类型：run(命令执行)、run_ipython(Python代码)、read(文件读取)、write(文件写入)、edit(文件编辑)
  "args": {                           // 统一参数结构，包含所有相关字段
    "content": "响应内容",             // 响应的主要内容（命令输出、文件内容、操作结果等）
    "command": "执行的命令",           // 命令执行：实际执行的bash命令
    "hidden": false,                  // 命令执行：是否隐藏输出
    "metadata": {                     // 命令执行：命令执行元数据
      "exit_code": 0,                 // 命令退出码（0表示成功）
      "pid": -1,                      // 进程ID
      "username": "用户名",            // 执行命令的用户名
      "hostname": "主机名",            // 主机名
      "working_dir": "工作目录",       // 命令执行时的工作目录
      "py_interpreter_path": "Python解释器路径", // Python解释器路径
      "prefix": "",                   // 输出前缀
      "suffix": "\n[Command completed with exit code 0.]" // 输出后缀
    },
    "code": "执行的Python代码",       // Python执行：要执行的Python代码
    "image_urls": ["图片URL1", "图片URL2"], // Python执行：生成的图片URL列表（如matplotlib图表）
    "path": "文件路径",                // 文件操作：文件路径
    "old_content": "旧内容",           // 文件编辑：编辑前的旧内容
    "new_content": "新内容",           // 文件编辑：编辑后的新内容
    "prev_exist": false,              // 文件编辑：文件之前是否存在
    "impl_source": "DEFAULT",         // 文件操作：实现来源
    "diff": "diff内容",               // 文件编辑：差异内容
    "error_id": "错误ID"              // 错误响应：错误标识符
  }
}
```

**说明：**
- 所有observation响应都使用统一的`args`结构
- 根据不同的observation类型，`args`中会包含相应的字段
- 字段含义与具体操作类型相关，未使用的字段不会出现在响应中
- 这种统一格式便于客户端处理，与action的格式保持一致

**1. Bash 命令执行**
```bash
# 输出Hello World
curl -X POST "http://localhost:8002/execute_action" \
  -H "Content-Type: application/json" \
  -d '{
    "action": {
      "action": "run",
      "args": {
        "command": "echo \"Hello World\"",
        "thought": "输出Hello World消息"
      }
    }
  }'
  
# 列出当前目录下的内容
curl -X POST "http://localhost:8002/execute_action" \
  -H "Content-Type: application/json" \
  -d '{
    "action": {
      "action": "run",
      "args": {
        "command": "ls -la",
        "thought": "列出当前目录内容"
      }
    }
  }'

# 显示当前工作目录路径
curl -X POST "http://localhost:8002/execute_action" \
  -H "Content-Type: application/json" \
  -d '{
    "action": {
      "action": "run",
      "args": {
        "command": "pwd",
        "thought": "显示当前工作目录"
      }
    }
  }'

# 切换到指定目录
curl -X POST "http://localhost:8002/execute_action" \
  -H "Content-Type: application/json" \
  -d '{
    "action": {
      "action": "run",
      "args": {
        "command": "cd /simple_openhands/workspace",
        "thought": "切换到工作目录"
      }
    }
  }'

# 显示当前登录的用户名
curl -X POST "http://localhost:8002/execute_action" \
  -H "Content-Type: application/json" \
  -d '{
    "action": {
      "action": "run",
      "args": {
        "command": "whoami",
        "thought": "显示当前用户名"
      }
    }
  }'

# 查找指定类型的文件
curl -X POST "http://localhost:8002/execute_action" \
  -H "Content-Type: application/json" \
  -d '{
    "action": {
      "action": "run",
      "args": {
        "command": "find . -name \"*.py\" | head -5",
        "thought": "查找Python文件"
      }
    }
  }'
```

**2. Python 代码执行**
```bash
# 执行简单Python代码
curl -X POST "http://localhost:8002/execute_action" \
  -H "Content-Type: application/json" \
  -d '{
    "action": {
      "action": "run_ipython",
      "args": {
        "code": "print(\"Hello, World!\")"
      }
    }
  }'

# 查看系统信息
curl -X POST "http://localhost:8002/execute_action" \
  -H "Content-Type: application/json" \
  -d '{
    "action": {
      "action": "run_ipython",
      "args": {
        "code": "import os\nprint(f\"Current directory: {os.getcwd()}\")\nprint(f\"Files: {os.listdir(\".\")}\")"
      }
    }
  }'

# 数据处理示例
curl -X POST "http://localhost:8002/execute_action" \
  -H "Content-Type: application/json" \
  -d '{
    "action": {
      "action": "run_ipython",
      "args": {
        "code": "numbers = [1, 2, 3, 4, 5]\nsquared = [x**2 for x in numbers]\nprint(f\"Numbers: {numbers}\")\nprint(f\"Squared: {squared}\")\nprint(f\"Sum: {sum(squared)}\")"
      }
    }
  }'

# 网络请求示例
curl -X POST "http://localhost:8002/execute_action" \
  -H "Content-Type: application/json" \
  -d '{
    "action": {
      "action": "run_ipython",
      "args": {
        "code": "import requests\ntry:\n    response = requests.get(\"https://httpbin.org/get\")\n    print(f\"Status: {response.status_code}\")\n    print(f\"Response: {response.json()}\")\nexcept Exception as e:\n    print(f\"Error: {e}\")"
      }
    }
  }'

# 生成图表示例
curl -X POST "http://localhost:8002/execute_action" \
  -H "Content-Type: application/json" \
  -d '{
    "action": {
      "action": "run_ipython",
      "args": {
        "code": "import matplotlib.pyplot as plt\nimport numpy as np\nx = np.linspace(0, 10, 100)\ny = np.sin(x)\nplt.plot(x, y)\nplt.title(\"Sine Wave\")\nplt.show()"
      }
    }
  }'
```

**3. 文件操作（read/write/edit）**
```bash
# 写入文件（write）
curl -X POST "http://localhost:8002/execute_action" \
  -H "Content-Type: application/json" \
  -d '{
    "action": {
      "action": "write",
      "args": {
        "path": "/simple_openhands/workspace/test.txt",
        "content": "这是一个测试文件",
        "thought": "创建测试文件"
      }
    }
  }'

# 编辑文件（edit）
curl -X POST "http://localhost:8002/execute_action" \
  -H "Content-Type: application/json" \
  -d '{
    "action": {
      "action": "edit",
      "args": {
        "path": "/simple_openhands/workspace/test.txt",
        "command": "str_replace",
        "old_str": "测试",
        "new_str": "示例",
        "thought": "修改文件内容"
      }
    }
  }'

# 读取文件（read）
curl -X POST "http://localhost:8002/execute_action" \
  -H "Content-Type: application/json" \
  -d '{
    "action": {
      "action": "read",
      "args": {
        "path": "/simple_openhands/workspace/test.txt",
        "thought": "查看文件内容"
      }
    }
  }'

# 删除文件
curl -X POST "http://localhost:8002/execute_action" \
  -H "Content-Type: application/json" \
  -d '{
    "action": {
      "action": "run",
      "args": {
        "command": "rm /simple_openhands/workspace/test.txt",
        "thought": "清理测试文件"
      }
    }
  }'
```

#### 文件查看端点

**view-file 特殊端点**

除了execute_action统一接口外，还提供专门的文件查看端点：
```bash
# 查看图片文件（PNG、JPG、GIF）
curl "http://localhost:8002/view-file?path=/path/to/your/image.png"

# 查看PDF文件
curl "http://localhost:8002/view-file?path=/path/to/your/document.pdf"

# 注意：/view-file 只支持图片和PDF文件，不支持文本文件
# 文本文件请使用上面的 execute_action——read 文件操作
```

#### 插件管理 API

**插件状态**
```bash
# 获取所有插件状态
curl http://localhost:8002/plugins
```

**VSCode 插件**
```bash
# 给挂载目录权限
chmod 777 workspace

# 初始化 VSCode 插件
curl -X POST "http://localhost:8002/plugins/vscode/initialize" \
  -H "Content-Type: application/json" \
  -d '{"username": "simple_openhands"}'

# 获取 VSCode 连接URL
curl http://localhost:8002/vscode-url

# 获取 VSCode 连接令牌
curl http://localhost:8002/vscode/connection_token

# 使用ip访问示例：（实际请更换ip,port,token）
http://10.1.2.2:3001/?tkn=9abae0ba-2de0-4c9d-8dcb-11fdf98f74ff&folder=/simple_openhands/workspace"
```

**注意**：
- Jupyter 插件：服务启动时自动初始化，无需手动操作
- AgentSkills 插件：函数集合，立即可用，无需初始化

---

## 快速接入指南

如果你想让其他项目快速接入使用 simple_openhands，可以通过程序化调用 `oh-run` CLI 工具来执行命令。这种方式可以绕过本地 shell，避免命令中的特殊字符被本地 shell 解析。

### 为什么使用程序化调用而不是本地 shell？

- **避免 shell 展开**：命令中的 `$变量`、`$(命令)`、反引号等不会被本地 shell 解析，原样传递给 `oh-run`
- **简化参数传递**：命令字符串作为参数直接传递，无需处理 shell 引号转义的复杂性
- **可预测性**：不依赖 shell 的配置差异，行为一致
- **跨平台兼容**：Windows 和 Linux 上行为一致

### Go 语言集成示例

使用 `exec.Command` 直接调用 `oh-run`，避免通过 shell：

```go
package main

import (
    "context"
    "fmt"
    "os"
    "os/exec"
    "strings"
    "time"
)

func executeCommand(ctx context.Context, command string, apiURL string, timeoutSeconds float64) (string, error) {
    ctxWithTimeout, cancel := context.WithTimeout(ctx, time.Duration(timeoutSeconds*float64(time.Second)))
    defer cancel()

    // 检查 oh-run 是否在 PATH 中
    if _, err := exec.LookPath("oh-run"); err != nil {
        return "", fmt.Errorf("oh-run not found in PATH: %w", err)
    }

    trimmed := strings.TrimSpace(command)
    if trimmed == "" {
        return "", fmt.Errorf("empty command")
    }

    // 设置环境变量
    env := os.Environ()
    env = append(env, fmt.Sprintf("OH_API_URL=%s", apiURL))

    // 使用 exec.Command 直接调用，不通过 shell
    cmd := exec.CommandContext(ctxWithTimeout, "oh-run", trimmed)
    cmd.Env = env

    output, err := cmd.CombinedOutput()
    if err != nil {
        return "", fmt.Errorf("command failed: %w\nOutput: %s", err, output)
    }

    return string(output), nil
}

// 使用示例
func main() {
    ctx := context.Background()
    apiURL := "http://127.0.0.1:8000"
    
    output, err := executeCommand(ctx, "pwd", apiURL, 30.0)
    if err != nil {
        fmt.Printf("Error: %v\n", err)
        return
    }
    fmt.Printf("Output: %s\n", output)
}
```

### Python 语言集成示例

使用 `subprocess.run()` 直接调用 `oh-run`，避免通过 shell：

```python
import subprocess
import os
from typing import Optional, Tuple

def execute_command(
    command: str,
    api_url: str,
    timeout: Optional[float] = None
) -> Tuple[str, int]:
    """
    执行命令并返回输出和退出码
    
    Args:
        command: 要执行的 bash 命令
        api_url: simple_openhands API 地址（如 http://127.0.0.1:8000）
        timeout: 超时时间（秒），None 表示使用默认超时
    
    Returns:
        (输出内容, 退出码)
    """
    # 检查 oh-run 是否在 PATH 中
    import shutil
    if not shutil.which("oh-run"):
        raise RuntimeError("oh-run not found in PATH")
    
    trimmed = command.strip()
    if not trimmed:
        raise ValueError("empty command")
    
    # 设置环境变量
    env = os.environ.copy()
    env["OH_API_URL"] = api_url
    
    # 使用 subprocess.run 直接调用，不通过 shell
    # shell=False 确保命令字符串作为参数传递，不会被 shell 解析
    try:
        result = subprocess.run(
            ["oh-run", trimmed],
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False  # 不自动抛出异常，手动处理退出码
        )
        return result.stdout, result.returncode
    except subprocess.TimeoutExpired as e:
        return f"Command timed out after {timeout} seconds", -1
    except FileNotFoundError:
        raise RuntimeError("oh-run not found in PATH")

# 使用示例
if __name__ == "__main__":
    api_url = "http://127.0.0.1:8000"
    
    # 执行简单命令
    output, exit_code = execute_command("pwd", api_url)
    print(f"Exit code: {exit_code}")
    print(f"Output: {output}")
    
    # 执行带超时的命令
    output, exit_code = execute_command("sleep 5", api_url, timeout=10.0)
    print(f"Exit code: {exit_code}")
    print(f"Output: {output}")
```

### 集成要点总结

1. **环境变量设置**：
   - `OH_API_URL`: 必需，指向 simple_openhands API 地址

2. **命令执行**：
   - 直接调用 `oh-run` 命令，将命令字符串作为参数传递
   - 不要通过 shell（如 `bash -c`）执行，避免 shell 解析命令

3. **错误处理**：
   - 检查 `oh-run` 是否在 PATH 中
   - 处理超时情况
   - 检查退出码（0 表示成功）

4. **输出格式**：
   - `oh-run` 的输出格式为：`Command ran and generated the following output:\n```\n{content}\n````
   - 空输出会显示为 `[empty output]`


### Bash Tool Description 建议

如果你需要为 bash 命令执行工具（如 `execute_bash` 或 `run_terminal_cmd`）编写 Tool Description，以下提供了两个版本：详细版（Detailed）和简短版（Short），结合了 OpenHands 和 simple_openhands in CompileBench 的最佳实践。

#### Detailed Version（详细版）

适合需要详细指导的场景：

```text
Execute a bash command in the terminal within a persistent shell session.

### Command Execution
* One command at a time: You can only execute one bash command at a time. If you need to run multiple commands sequentially, use `&&` or `;` to chain them together.
* Persistent session: Commands execute in a persistent shell session where environment variables, virtual environments, and working directory persist between commands.
* Soft timeout: Commands have a soft timeout of 10 seconds, once that's reached, you have the option to continue or interrupt the command (see section below for details)
* Shell options: Do NOT use `set -e`, `set -eu`, or `set -euo pipefail` in shell scripts or commands in this environment. The runtime may not support them and can cause unusable shell sessions. If you want to run multi-line bash commands, write the commands to a file and then run it, instead.

### Long-running Commands
* For commands that may run indefinitely, run them in the background and redirect output to a file, e.g. `python3 app.py > server.log 2>&1 &`.
* For commands that may run for a long time (e.g. installation or testing commands), or commands that run for a fixed amount of time (e.g. sleep), you should set the "timeout" parameter of your function call to an appropriate value.
* If a bash command returns exit code `-1`, this means the process hit the soft timeout and is not yet finished. By setting `is_input` to `true`, you can:
  - Send empty `command` to retrieve additional logs
  - Send text (set `command` to the text) to STDIN of the running process
  - Send control commands like `C-c` (Ctrl+C), `C-d` (Ctrl+D), or `C-z` (Ctrl+Z) to interrupt the process
  - If you do C-c, you can re-start the process with a longer "timeout" parameter to let it run to completion

### Best Practices
* Directory verification: Before creating new directories or files, first verify the parent directory exists and is the correct location.
* Directory management: Try to maintain working directory by using absolute paths and avoiding excessive use of `cd`.

### Output Handling
* Output truncation: If the output exceeds a maximum length, it will be truncated before being returned.
```

#### Short Version（简短版）

适合需要简洁提示的场景：

```text
Execute a bash command in the terminal within a persistent shell session.

Execution rules:
- Interact with running process: If a bash command returns exit code `-1`, this means the process is not yet finished. You can interact with the running process and send empty `command` to retrieve any additional logs, or send additional text to STDIN of the running process, or send command like `C-c` (Ctrl+C), `C-d` (Ctrl+D), `C-z` (Ctrl+Z) to interrupt the process.
- Don't include any newlines in the command.
- Do NOT use `set -e`, `set -eu`, or `set -euo pipefail`. These can cause unusable shell sessions.
- Try to maintain working directory by using absolute paths and avoiding excessive use of `cd`.
```

## 开发者使用指南

### 环境配置

**容器内环境说明：**
- 使用 **Poetry** 管理依赖，**micromamba** 管理Python环境
- 容器内Python命令需要：`/simple_openhands/micromamba/bin/micromamba run -n simple_openhands poetry run python -c "your_code_here"`

**容器内目录结构：**
```
/simple_openhands/
├── code/                   # 应用代码
│   ├── simple_openhands/   # 源代码
│   ├── tests/              # 测试代码
│   ├── pyproject.toml      # Poetry配置
│   └── poetry.lock         # Poetry锁定文件
├── workspace/              # 工作目录（挂载点）
├── poetry/                 # Poetry虚拟环境
├── micromamba/             # micromamba环境
├── bin/                    # uv工具（env, uv, uvx）
└── .openvscode-server/     # VSCode服务器

注意：日志文件（当 LOG_TO_FILE=true 时）会写入到 /simple_openhands/code/logs/ 目录

/home/peter/                # 用户peter的家目录
├── .bashrc                 # Bash配置文件（最小化配置）
├── .profile                # Profile配置
└── .openvscode-server/     # VSCode用户配置（运行时创建）
```

### 项目架构

本项目按照 OpenHands 标准组织类定义，结构清晰：

#### 基础类层次结构

```
Event (基础事件类)
├── Action (动作基类)
│   ├── CmdRunAction (命令执行)
│   ├── IPythonRunCellAction (Python代码执行)
│   ├── FileReadAction (文件读取)
│   ├── FileWriteAction (文件写入)
│   └── FileEditAction (文件编辑)
└── Observation (观察基类)
    ├── CmdOutputObservation (命令输出)
    ├── IPythonRunCellObservation (Python执行输出)
    ├── FileReadObservation (文件读取结果)
    ├── FileWriteObservation (文件写入结果)
    └── FileEditObservation (文件编辑结果)
```

### 功能实现细节

#### **1. Bash 命令执行系统**

**命令执行与解析**
- 支持执行单个 bash 命令，包括管道、重定向、条件语句等
- 通过 bashlex 库进行智能语法解析
- 支持命令链（&&、;）、here document 等复杂语法结构
- 不支持同时执行多条命令

**会话环境管理**
- 基于 tmux 的持久化 shell 环境
- 支持多会话管理，每个会话有唯一标识
- 支持命令历史记录（限制为10,000条）
- 支持切换工作目录并通过 PS1 提示符自动检测工作目录变化

**执行控制与监控**
- 通过 tmux 会话实时获取命令的标准输出和错误输出
- 支持阻塞和非阻塞模式
- 提供两种超时机制（无变化超时默认30秒和硬超时可配置）
- 非阻塞模式下自动触发超时防止命令长时间阻塞

**交互与状态管理**
- 支持与运行中的进程交互，可发送输入数据或特殊控制键（如 Ctrl+C、Ctrl+Z、Ctrl+D 等）
- 实时跟踪命令执行状态（运行中、完成、超时等）
- 自动清理命令输出并处理输出截断

**错误处理与容错**
- 完善的错误处理机制，包括命令解析错误、执行错误、超时错误等异常情况
- 提供详细的错误信息和状态反馈

#### **2. Python 代码执行引擎**

**Jupyter Kernel Gateway 集成**
- 通过 Jupyter Kernel Gateway 执行 Python 代码，基于 Jupyter Kernel 的代码执行环境，支持状态保持
- 自动启动并使用固定端口（8001）

**智能内核管理**
- 自动初始化、内核生命周期管理、心跳检测、连接重连
- 支持 Docker 容器运行模式

**代码执行与输出**
- 通过 IPythonRunCellAction 执行代码，支持超时设置
- 多种输出类型处理（文本、图片PNG、ANSI转义序列清理）

**环境集成与错误处理**
- 与 Poetry 虚拟环境和 micromamba 环境集成
- 完善的异常捕获和错误信息展示，支持 Linux 系统完整运行

#### **3. 文件操作管理系统**

**文件读取**
- 通过FileReadAction执行，支持相对路径和绝对路径
- 自动基于当前工作目录解析，支持UTF-8编码

**文件写入**
- 通过FileWriteAction执行，支持创建和覆盖文件内容
- 自动创建必要的目录结构

**文件编辑**
- 通过FileEditAction执行，支持字符串替换编辑操作（str_replace命令）

**文件查看**
- 提供/view-file端点，支持查看文件内容
- 生成HTML格式的文件查看器

**统一接口**
- 核心文件操作（读取、写入、编辑）通过/execute_action端点统一处理
- 遵循OpenHands的Action架构

**错误处理**
- 完善的异常处理，包括文件不存在、路径是目录、权限错误、编码错误等情况的处理
- 通过返回相应的Observation对象或HTTP异常提供详细错误信息

#### **4. 系统监控与诊断**

**服务器信息**
- 通过 /server_info 端点提供服务器状态、工作目录、用户名和资源信息

**系统资源监控**
- 通过 /system/stats 端点监控进程 CPU、内存（RSS、VMS、使用百分比）、磁盘使用情况和 I/O 统计

**端口管理**
- 提供端口可用性检查和可用端口查找功能，支持端口范围搜索

#### **5. VSCode 插件**

**OpenVSCode 服务器**
- 集成 OpenVSCode 服务器，提供基于浏览器的代码编辑环境
- 支持端口配置（默认3000）和自动端口检测

**连接管理**
- 生成唯一连接令牌，提供 /vscode-url 和 /vscode/connection_token 端点获取连接信息

**工作区配置**
- 自动创建 .vscode/settings.json 配置文件
- Windows 容器内自动禁用，Linux 容器正常支持

### 开发指南

#### 添加新的 Action 类型

1. 在相应的模块文件中定义新的 Action 类
2. 继承自 `Action` 基类
3. 设置 `action` 属性为唯一的字符串标识
4. 在 `serialization.py` 的 `actions` 元组中添加新类
5. 更新 `__init__.py` 的导出

#### 添加新的 Observation 类型

1. 在相应的模块文件中定义新的 Observation 类
2. 继承自 `Observation` 基类
3. 设置 `observation` 属性为唯一的字符串标识
4. 在 `serialization.py` 的 `observations` 元组中添加新类
5. 更新 `__init__.py` 的导出

### 测试运行

#### 在容器内运行
```bash
# 进入容器
docker exec -it simple-openhands bash

# 切换到代码目录
cd /simple_openhands/code

# 运行所有测试
/simple_openhands/micromamba/bin/micromamba run -n simple_openhands poetry run pytest tests -v

# 或者运行特定测试文件
/simple_openhands/micromamba/bin/micromamba run -n simple_openhands poetry run pytest tests/test_bash_session.py -v

# 或者运行特定测试函数
/simple_openhands/micromamba/bin/micromamba run -n simple_openhands poetry run pytest tests/test_bash_session.py::test_bash_session_creation -v
```

### 开发流程
1. **修改代码**
2. **停止旧容器**: `docker stop simple-openhands && docker rm simple-openhands`
3. **构建镜像**: `docker build -t simple-openhands .`
4. **启动新容器**: `docker run -d --name simple-openhands -p 8000:8000 -p 3000:3000 -p 8001:8001 -v "$(pwd)/workspace:/simple_openhands/workspace" -e WORK_DIR=/simple_openhands/workspace simple-openhands`
5. **验证修改**: 测试新功能是否正常工作

### 开发提示
- 大部分操作与用户指南相同
- 主要区别在于依赖安装和测试运行方式
- 代码修改后需要重新构建镜像才能生效