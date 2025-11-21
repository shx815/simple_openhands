# Simple Windows Docker Runtime

基于 OpenHands 的 runtime 代码创建的 Docker 容器，提供 FastAPI 接口来执行 PowerShell 命令与插件功能。

## 主要功能

### **核心功能**

#### **1. PowerShell 命令执行系统**
- 执行 PowerShell 命令
- 支持交互式操作

#### **2. Python 代码执行引擎**
- Jupyter 服务器集成（自动初始化）
- 交互式编程环境
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
- **VSCode 插件**：❌ **不支持Windows** - VSCode插件在Windows容器中不可用
 
#### **6. Git 版本控制与代码差异**
- 获取当前分支（/git/branch）
- 获取变更文件列表（/git/changes）
- 获取单文件原始/修改内容（/git/diff）
---

## 用户使用指南

### 1. 环境部署

#### 方式一：一键部署脚本（推荐）
```powershell
# 进入项目目录
Set-Location simple_openhands

# 执行PowerShell部署脚本
.\deploy-windows.ps1

# 注意：如果遇到执行策略限制，运行：
# Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

#### 方式二：手动部署
```powershell
# 进入项目目录
Set-Location simple_openhands

# 构建 Docker 镜像
docker build -f Dockerfile.windows -t simple-openhands:windows .

# 启动容器
docker run -d --name simple-openhands `
  -p 8000:8000 -p 3000:3000 -p 8001:8001 `
  -v "${PWD}\workspace:C:\simple_openhands\workspace" `
  -e WORK_DIR=C:\simple_openhands\workspace `
  simple-openhands:windows

# 端口说明：
# -p 8000:8000          # 主API服务端口，提供所有API接口
# -p 3000:3000          # VSCode服务器端口，用于Web版VSCode访问
# -p 8001:8001          # Jupyter端口，用于Python代码执行

# 查看启动日志
docker logs -f simple-openhands
```

### 2. API 接口使用

#### 基础服务 API

**健康检查**
```powershell
# 检查服务是否存活
Invoke-WebRequest -Uri "http://localhost:8000/alive" -Method GET

# 获取服务器详细信息
Invoke-WebRequest -Uri "http://localhost:8000/server_info" -Method GET

# 访问根路径
Invoke-WebRequest -Uri "http://localhost:8000/" -Method GET
```

**系统监控**
```powershell
# 获取系统资源统计
Invoke-WebRequest -Uri "http://localhost:8000/system/stats" -Method GET

# 重置 PowerShell session
Invoke-WebRequest -Uri "http://localhost:8000/reset" -Method POST
```
 
#### Git API

```powershell
# 获取当前分支
Invoke-WebRequest -Uri "http://localhost:8000/git/branch" -Method GET
 
# 获取工作区变更（指定工作目录）
Invoke-WebRequest -Uri "http://localhost:8000/git/changes?cwd=C:\simple_openhands\workspace" -Method POST
 
# 获取单文件差异（指定工作目录）
$body = @{ file_path = "test.txt"; cwd = "C:\simple_openhands\workspace" } | ConvertTo-Json
Invoke-WebRequest -Uri "http://localhost:8000/git/diff" -Method POST -ContentType "application/json" -Body $body
```

#### execute_action 统一接口

**标准命令格式**

所有操作都通过 `/execute_action` 端点执行，使用统一的JSON格式。以下是完整的命令结构说明：

```json
{
  "action": {
    "action": "action_type",          // 动作类型：run(命令执行)、run_ipython(Python代码)、read(文件读取)、write(文件写入)、edit(文件编辑)
    "args": {                         // 动作参数，根据动作类型不同而不同
      "command": "没有gei",      // 命令执行：要执行的PowerShell命令
      "code": "print('Hello')",       // Python执行：要执行的Python代码
      "path": "C:\\path\\to\\file",   // 文件操作：文件路径
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
    "command": "执行的命令",           // 命令执行：实际执行的PowerShell命令
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

**1. PowerShell 命令执行**
```powershell
# Output Hello World
$body = @{
    action = @{
        action = "run"
        args = @{
            command = "echo 'Hello World'"
            thought = "Output Hello World message"
        }
    }
} | ConvertTo-Json -Depth 3

Invoke-WebRequest -Uri "http://localhost:8000/execute_action" `
  -Method POST `
  -ContentType "application/json" `
  -Body $body

# 列出当前目录下的内容
$body = @{
    action = @{
        action = "run"
        args = @{
            command = "Get-ChildItem"
            thought = "List current directory contents"
        }
    }
} | ConvertTo-Json -Depth 3

Invoke-WebRequest -Uri "http://localhost:8000/execute_action" `
  -Method POST `
  -ContentType "application/json" `
  -Body $body

# 显示当前工作目录路径
$body = @{
    action = @{
        action = "run"
        args = @{
            command = "Get-Location"
            thought = "显示当前工作目录"
        }
    }
} | ConvertTo-Json -Depth 3

Invoke-WebRequest -Uri "http://localhost:8000/execute_action" `
  -Method POST `
  -ContentType "application/json" `
  -Body $body

# 切换到指定目录
$body = @{
    action = @{
        action = "run"
        args = @{
            command = "Set-Location C:\simple_openhands\workspace"
            thought = "切换到工作目录"
        }
    }
} | ConvertTo-Json -Depth 3

Invoke-WebRequest -Uri "http://localhost:8000/execute_action" `
  -Method POST `
  -ContentType "application/json" `
  -Body $body

# 显示当前登录的用户名
$body = @{
    action = @{
        action = "run"
        args = @{
            command = "whoami"
            thought = "显示当前用户名"
        }
    }
} | ConvertTo-Json -Depth 3

Invoke-WebRequest -Uri "http://localhost:8000/execute_action" `
  -Method POST `
  -ContentType "application/json" `
  -Body $body

# 查找指定类型的文件
$body = @{
    action = @{
        action = "run"
        args = @{
            command = "Get-ChildItem -Recurse -Filter '*.py' | Select-Object -First 5"
            thought = "查找Python文件"
        }
    }
} | ConvertTo-Json -Depth 3

Invoke-WebRequest -Uri "http://localhost:8000/execute_action" `
  -Method POST `
  -ContentType "application/json" `
  -Body $body
```

**2. Python 代码执行**
```powershell
# 执行简单Python代码
$body = @{
    action = @{
        action = "run_ipython"
        args = @{
            code = "print('Hello, World!')"
        }
    }
} | ConvertTo-Json -Depth 3

Invoke-WebRequest -Uri "http://localhost:8000/execute_action" `
  -Method POST `
  -ContentType "application/json" `
  -Body $body

# Check system information
$body = @{
    action = @{
        action = "run_ipython"
        args = @{
            code = "import os`nprint(f'Current directory: {os.getcwd()}')`nprint(f'Files: {os.listdir(`"`.`")}')"
        }
    }
} | ConvertTo-Json -Depth 3

Invoke-WebRequest -Uri "http://localhost:8000/execute_action" `
  -Method POST `
  -ContentType "application/json" `
  -Body $body

# 数据处理示例
$body = @{
    action = @{
        action = "run_ipython"
        args = @{
            code = "numbers = [1, 2, 3, 4, 5]`nsquared = [x**2 for x in numbers]`nprint(f'Numbers: {numbers}')`nprint(f'Squared: {squared}')`nprint(f'Sum: {sum(squared)}')"
        }
    }
} | ConvertTo-Json -Depth 3

Invoke-WebRequest -Uri "http://localhost:8000/execute_action" `
  -Method POST `
  -ContentType "application/json" `
  -Body $body

# 网络请求示例
$body = @{
    action = @{
        action = "run_ipython"
        args = @{
            code = "import requests`ntry:`n    response = requests.get('https://httpbin.org/get')`n    print(f'Status: {response.status_code}')`n    print(f'Response: {response.json()}')`nexcept Exception as e:`n    print(f'Error: {e}')"
        }
    }
} | ConvertTo-Json -Depth 3

Invoke-WebRequest -Uri "http://localhost:8000/execute_action" `
  -Method POST `
  -ContentType "application/json" `
  -Body $body

# 生成图表示例
$body = @{
    action = @{
        action = "run_ipython"
        args = @{
            code = "import matplotlib.pyplot as plt`nimport numpy as np`nx = np.linspace(0, 10, 100)`ny = np.sin(x)`nplt.plot(x, y)`nplt.title('Sine Wave')`nplt.show()"
        }
    }
} | ConvertTo-Json -Depth 3

Invoke-WebRequest -Uri "http://localhost:8000/execute_action" `
  -Method POST `
  -ContentType "application/json" `
  -Body $body
```

**3. 文件操作（read/write/edit）**
```powershell
# 写入文件（write）
$body = @{
    action = @{
        action = "write"
        args = @{
            path = "C:\simple_openhands\workspace\test.txt"
            content = "This is a test file"
            thought = "Create test file"
        }
    }
} | ConvertTo-Json -Depth 3

Invoke-WebRequest -Uri "http://localhost:8000/execute_action" `
  -Method POST `
  -ContentType "application/json" `
  -Body $body

# 编辑文件（edit）
$body = @{
    action = @{
        action = "edit"
        args = @{
            path = "C:\simple_openhands\workspace\test.txt"
            command = "str_replace"
            old_str = "test"
            new_str = "example"
            thought = "Modify file content"
        }
    }
} | ConvertTo-Json -Depth 3

Invoke-WebRequest -Uri "http://localhost:8000/execute_action" `
  -Method POST `
  -ContentType "application/json" `
  -Body $body

# 读取文件（read）
$body = @{
    action = @{
        action = "read"
        args = @{
            path = "C:\simple_openhands\workspace\test.txt"
            thought = "View file content"
        }
    }
} | ConvertTo-Json -Depth 3

Invoke-WebRequest -Uri "http://localhost:8000/execute_action" `
  -Method POST `
  -ContentType "application/json" `
  -Body $body

# 删除文件
$body = @{
    action = @{
        action = "run"
        args = @{
            command = "Remove-Item C:\simple_openhands\workspace\test.txt"
            thought = "清理测试文件"
        }
    }
} | ConvertTo-Json -Depth 3

Invoke-WebRequest -Uri "http://localhost:8000/execute_action" `
  -Method POST `
  -ContentType "application/json" `
  -Body $body
```

#### 文件查看端点

**view-file 特殊端点**

除了execute_action统一接口外，还提供专门的文件查看端点：
```powershell
# 查看图片文件（PNG、JPG、GIF）
Invoke-WebRequest -Uri "http://localhost:8000/view-file?path=C:\path\to\your\image.png"

# 查看PDF文件
Invoke-WebRequest -Uri "http://localhost:8000/view-file?path=C:\path\to\your\document.pdf"

# 注意：/view-file 只支持图片和PDF文件，不支持文本文件
# 文本文件请使用上面的 execute_action——read 文件操作
```

#### 插件管理 API

**插件状态**
```powershell
# 获取所有插件状态
Invoke-WebRequest -Uri "http://localhost:8000/plugins" -Method GET
```

**VSCode 插件** 

**重要提示：VSCode插件在Windows容器中不支持**

Windows版本的Simple OpenHands不支持VSCode插件功能。这是由于OpenVSCode服务器在Windows容器环境中的兼容性限制。

如果您需要代码编辑功能，建议：
1. 使用文件操作API (`read`、`write`、`edit`) 进行代码操作
2. 在宿主机上使用VSCode连接到容器进行开发
3. 使用Jupyter插件进行Python代码执行和调试

```powershell
# ❌ 以下命令在Windows版本中不可用
# Invoke-WebRequest -Uri "http://localhost:8000/plugins/vscode/initialize" -Method POST
# Invoke-WebRequest -Uri "http://localhost:8000/vscode-url" -Method GET

# 获取 VSCode 连接令牌
Invoke-WebRequest -Uri "http://localhost:8000/vscode/connection_token" -Method GET
```

**注意**：
- Jupyter 插件：服务启动时自动初始化，无需手动操作
- AgentSkills 插件：函数集合，立即可用，无需初始化

---

## 开发者使用指南

### 环境配置

**容器内环境说明：**
- 使用 **Poetry** 管理依赖，Python环境通过Poetry虚拟环境管理
- 容器内Python命令需要：`python -m poetry run python -c "your_code_here"`

**容器内目录结构：**
```
C:\simple_openhands\
├── code\                    # 应用代码
├── workspace\               # 工作目录
├── poetry\                  # Poetry环境
└── .openvscode-server\      # VSCode服务器
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

#### **1. PowerShell 命令执行系统**

**命令执行与解析**
- 支持执行单个 PowerShell 命令，包括管道、重定向、条件语句等
- 通过 pythonnet 集成 PowerShell SDK 进行命令执行
- 支持 PowerShell 特有的对象管道和 .NET 集成
- 不支持同时执行多条命令

**会话环境管理**
- 基于 PowerShell Runspace 的持久化 shell 环境
- 支持多会话管理，每个会话有唯一标识
- 支持命令历史记录
- 支持切换工作目录并自动检测工作目录变化

**执行控制与监控**
- 通过 PowerShell Runspace 实时获取命令的标准输出和错误输出
- 支持阻塞和非阻塞模式
- 提供超时机制防止命令长时间阻塞
- 与 .NET CLR 深度集成

**交互与状态管理**
- 支持与运行中的进程交互
- 实时跟踪命令执行状态（运行中、完成、超时等）
- 自动清理命令输出并处理输出截断

**错误处理与容错**
- 完善的错误处理机制，包括命令解析错误、执行错误、超时错误等异常情况
- 提供详细的错误信息和状态反馈

#### **2. Python 代码执行引擎**

**Jupyter 服务器集成**
- 通过 Jupyter Kernel Gateway 执行 Python 代码，支持交互式编程
- 自动启动并使用固定端口（8001）

**智能内核管理**
- 自动初始化、内核生命周期管理、心跳检测、连接重连
- 支持 LocalRuntime 和 Docker 容器运行模式

**代码执行与输出**
- 通过 IPythonRunCellAction 执行代码，支持超时设置
- 多种输出类型处理（文本、图片PNG、ANSI转义序列清理）

**环境集成与错误处理**
- 与 Poetry 虚拟环境集成
- 完善的异常捕获和错误信息展示，支持 Windows 系统完整运行

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

#### **5. VSCode 插件** ❌ **Windows不支持**
 
#### **6. Git 功能**
 
**适配与接口**
- 通过薄适配的 GitHandler 统一执行与输出，API 映射如下：
  - GET `/git/branch` → `GitHandler.get_current_branch()`
  - POST `/git/changes` → `GitHandler.get_git_changes()`（多仓库聚合、状态标准化）
  - POST `/git/diff` → `GitHandler.get_git_diff(file_path)`（返回 original/modified）
 
**跨平台约束（Windows）**
- 避免 `grep`、命令替换 `$(...)` 等仅类 Unix 语法；必要信息通过完整命令输出再在 Python 里解析。
- Windows 容器内通过适配层处理 `git.exe`、临时脚本目录等差异。
 
**返回结构（示例）**
- `/git/changes`：`[{"status": "M|A|D|U", "path": "relative/path"}, ...]`
- `/git/diff`：`{"original": "...", "modified": "..."}`

**OpenVSCode 服务器**
- ❌ Windows容器中不支持OpenVSCode服务器
- 推荐使用文件操作API (`read`、`write`、`edit`) 进行代码编辑
- 支持端口配置（默认3000）和自动端口检测

**连接管理**
- 生成唯一连接令牌，提供 /vscode-url 和 /vscode/connection_token 端点获取连接信息

**工作区配置**
- 自动创建 .vscode/settings.json 配置文件
- Windows 容器内正常支持

### 开发指南

#### 容器内开发环境

**进入容器PowerShell环境**
```powershell
# 方式1：直接进入PowerShell 7
docker exec -it simple-openhands pwsh

# 方式2：先进入cmd，再切换到PowerShell
docker exec -it simple-openhands cmd
pwsh
```

**容器内目录导航**
```powershell
# 进入应用代码目录
cd C:\simple_openhands\code

# 查看当前目录内容
Get-ChildItem

# 查看Python环境
python -m poetry env info

# 激活Poetry环境（自动激活）
python -m poetry shell
```

**开发环境验证**
```powershell
# 检查Python版本
python --version

# 检查Poetry版本
python -m poetry --version

# 检查PowerShell版本
$PSVersionTable.PSVersion

# 检查.NET环境
dotnet --version

# 检查已安装的.NET SDK
dotnet --list-sdks

# 检查已安装的.NET Runtime
dotnet --list-runtimes

# 检查Chocolatey安装的包
choco list --local-only | findstr dotnet
```

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
```powershell
# 进入容器
docker exec -it simple-openhands cmd

# 切换到代码目录
cd C:\simple_openhands\code

# 运行所有测试
python -m poetry run pytest tests -v

# 或者运行特定测试文件
python -m poetry run pytest tests\test_windows_bash.py -v

# 或者运行特定测试函数
python -m poetry run pytest tests\test_python_commands.py::test_basic_commands -v

# ⚠️ Windows测试注意事项
# bash_session相关测试在Windows容器环境下可能失败，这是正常现象：
# python -m poetry run pytest tests\test_bash_session.py -v  # 可能失败
```

### 开发流程
1. **修改代码**
2. **停止旧容器**: `docker stop simple-openhands; docker rm simple-openhands`
3. **构建镜像**: `docker build -f Dockerfile.windows -t simple-openhands:windows .`
4. **启动新容器**: `docker run -d --name simple-openhands -p 8000:8000 -p 3000:3000 -p 8001:8001 -v "${PWD}\workspace:C:\simple_openhands\workspace" simple-openhands:windows`
5. **验证修改**: 测试新功能是否正常工作

### 开发提示
- 大部分操作与用户指南相同
- 主要区别在于依赖安装和测试运行方式
- 代码修改后需要重新构建镜像才能生效
- 使用 PowerShell 特有的语法和 cmdlet
- 支持 .NET 对象和 Windows 特有的功能

### 故障排除

**如果.NET命令不可用**
```powershell
# 检查.NET是否正确安装
dotnet --version

# 如果显示"No .NET SDKs were found"，需要重新构建镜像
# 1. 停止并删除容器
docker stop simple-openhands
docker rm simple-openhands

# 2. 重新构建镜像（确保使用最新的Dockerfile）
docker build -f Dockerfile.windows -t simple-openhands:windows .

# 3. 启动新容器
docker run -d --name simple-openhands -p 8000:8000 simple-openhands:windows

# 4. 验证.NET安装
docker exec -it simple-openhands pwsh -Command "dotnet --version"
```

**如果PowerShell命令不可用**
```powershell
# 检查PowerShell版本
pwsh --version

# 如果PowerShell 7不可用，可以尝试使用Windows PowerShell
powershell --version

# 或者重新安装PowerShell 7
docker exec -it simple-openhands cmd
choco install pwsh -y
```
