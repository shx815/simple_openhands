# Git Utilities for Simple OpenHands

这个模块包含了从OpenHands项目移植过来的git相关工具，用于在simple_openhands项目中处理git操作。

## 文件说明

### 1. `git_diff.py`
- **功能**: 获取单个文件的git diff，比较当前版本与远程版本
- **特点**: 独立脚本，无外部依赖
- **用途**: 获取文件的原始版本和修改版本内容

### 2. `git_changes.py`  
- **功能**: 获取当前工作目录相对于远程origin的git变更
- **特点**: 独立脚本，无外部依赖
- **用途**: 列出所有变更的文件及其状态（M=修改，A=新增，D=删除等）

### 3. `git_handler.py`
- **功能**: Git操作的高级封装类
- **特点**: 依赖logger和上述两个脚本
- **用途**: 提供统一的git操作接口

## 使用方法

### 基本使用

```python
from simple_openhands.utils.git import GitHandler, CommandResult

# 定义shell执行函数
def execute_shell(cmd: str, cwd: str | None) -> CommandResult:
    import subprocess
    result = subprocess.run(
        args=cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=cwd
    )
    return CommandResult(
        content=result.stdout.decode() if result.stdout else result.stderr.decode(),
        exit_code=result.returncode
    )

# 定义文件创建函数
def create_file(file_path: str, content: str) -> int:
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    return 0

# 初始化GitHandler
git_handler = GitHandler(execute_shell, create_file)
git_handler.set_cwd("/path/to/your/repo")

# 获取当前分支
branch = git_handler.get_current_branch()
print(f"Current branch: {branch}")

# 获取git变更
changes = git_handler.get_git_changes()
for change in changes:
    print(f"{change['status']}: {change['path']}")

# 获取文件diff
diff = git_handler.get_git_diff("path/to/file.py")
print(f"Original: {diff['original']}")
print(f"Modified: {diff['modified']}")
```

### 直接使用脚本

```bash
# 获取git变更
python3 simple_openhands/utils/git/git_changes.py

# 获取文件diff
python3 simple_openhands/utils/git/git_diff.py "path/to/file.py"
```

## 适配说明

相比原始OpenHands版本，主要做了以下适配：

1. **导入路径**: 将`openhands.core.logger`改为`simple_openhands.core.logger`
2. **模块导入**: 将`openhands.runtime.utils`改为`simple_openhands.utils.git`
3. **命令路径**: 将`/openhands/code/`改为`/simplerun/code/simple_openhands/`
4. **Logger名称**: 使用`simple_openhands_logger`替代`openhands_logger`

## 注意事项

1. 这些工具需要在git仓库中运行才能正常工作
2. `git_handler.py`需要提供shell执行和文件创建的回调函数
3. 脚本会自动处理编码问题，支持UTF-8、GBK、GB2312、Latin-1等编码
4. 大文件（>1MB）会被跳过，避免性能问题

## 测试

运行示例程序：
```bash
python -m simple_openhands.utils.git.example_usage
```
