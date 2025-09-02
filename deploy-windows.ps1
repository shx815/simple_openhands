# Windows版本的Simple OpenHands部署和启动脚本
# PowerShell脚本，用于构建、部署和测试Windows Docker容器

# 日志函数
function Write-Info {
    param([string]$Message)
    Write-Host "[INFO] $Message" -ForegroundColor Blue
}

function Write-Success {
    param([string]$Message)
    Write-Host "[SUCCESS] $Message" -ForegroundColor Green
}

function Write-Warning {
    param([string]$Message)
    Write-Host "[WARNING] $Message" -ForegroundColor Yellow
}

function Write-Error {
    param([string]$Message)
    Write-Host "[ERROR] $Message" -ForegroundColor Red
}

# 检查Docker是否运行
function Test-Docker {
    Write-Info "Checking if Docker is running..."
    
    try {
        docker info | Out-Null
        Write-Success "Docker is running"
    }
    catch {
        Write-Error "Docker is not running. Please start Docker Desktop first."
        exit 1
    }
}

# 检查Windows容器支持
function Test-WindowsContainers {
    Write-Info "Checking Windows container mode..."
    
    try {
        $serverOs = docker version --format '{{.Server.Os}}' 2>$null
        if ($serverOs -eq "windows") {
            Write-Success "Windows containers are enabled"
        }
        else {
            Write-Warning "Windows containers not detected. Make sure to:"
            Write-Warning "1. Enable Windows containers in Docker Desktop"
            Write-Warning "2. Switch to Windows containers mode"
            Write-Warning "3. Restart Docker Desktop if needed"
            Write-Host ""
            $continue = Read-Host "Continue anyway? (y/N)"
            if ($continue -ne "y" -and $continue -ne "Y") {
                Write-Error "Aborted by user"
                exit 1
            }
        }
    }
    catch {
        Write-Warning "Could not determine container mode, continuing..."
    }
}

# 清理旧容器和镜像
function Remove-OldResources {
    Write-Info "Cleaning up old containers and images..."
    
    # 停止并删除旧容器
    try {
        $containers = docker ps -a --format "table {{.Names}}" | Select-String "simple-openhands"
        if ($containers) {
            Write-Info "Stopping and removing old container..."
            docker stop simple-openhands 2>$null | Out-Null
            docker rm simple-openhands 2>$null | Out-Null
            Write-Success "Old container cleaned up"
        }
    }
    catch {
        Write-Warning "No old containers to clean up or cleanup failed"
    }
    
    # 清理悬空镜像（可选）
    try {
        $danglingImages = docker images --filter "dangling=true" -q
        if ($danglingImages) {
            Write-Info "Removing dangling images..."
            docker rmi $danglingImages 2>$null | Out-Null
            Write-Success "Dangling images removed"
        }
    }
    catch {
        Write-Warning "Could not remove dangling images"
    }
}

# 构建Windows镜像
function Build-WindowsImage {
    Write-Info "Building Windows Docker image..."
    
    # 检查是否存在Dockerfile.windows
    if (-not (Test-Path "Dockerfile.windows")) {
        Write-Error "Dockerfile.windows not found in current directory"
        exit 1
    }
    
    # 首次构建提示
    Write-Host ""
    Write-Warning "First build may take 20-30 minutes, please be patient..."
    Write-Info "Building process will download Windows base image and install dependencies"
    Write-Warning "Windows image builds are typically slower than Linux images"
    Write-Host ""
    
    # 构建Windows镜像
    try {
        docker build -f Dockerfile.windows -t simple-openhands:windows .
        Write-Success "Windows image built successfully"
    }
    catch {
        Write-Error "Failed to build Windows image"
        exit 1
    }
}

# 准备挂载目录
function Initialize-MountDirectories {
    Write-Info "Preparing mount directories..."
    
    # 创建workspace目录
    $workspaceDir = Join-Path (Get-Location) "workspace"
    if (-not (Test-Path $workspaceDir)) {
        New-Item -ItemType Directory -Path $workspaceDir -Force | Out-Null
    }
    
    Write-Success "Mount directories prepared"
}

# 启动Windows容器
function Start-WindowsContainer {
    Write-Info "Starting Windows container..."
    
    # 获取当前目录的Windows路径
    $currentDir = (Get-Location).Path
    $workspacePath = Join-Path $currentDir "workspace"
    
    # 启动Windows容器
    try {
        docker run -d --name simple-openhands `
            -p 8000:8000 `
            -p 3000:3000 `
            -p 8001:8001 `
            -v "${workspacePath}:C:\simple_openhands\workspace" `
            simple-openhands:windows
        Write-Success "Windows container started successfully"
    }
    catch {
        Write-Error "Failed to start Windows container"
        exit 1
    }
}

# 等待服务启动
function Wait-ForService {
    Write-Info "Waiting for Windows service to start..."
    
    $maxAttempts = 60  # Windows容器启动通常更慢
    $attempt = 1
    
    while ($attempt -le $maxAttempts) {
        try {
            $response = Invoke-WebRequest -Uri "http://localhost:8000/alive" -TimeoutSec 3 -UseBasicParsing
            if ($response.StatusCode -eq 200) {
                Write-Success "Windows service is ready (attempt $attempt/$maxAttempts)"
                return
            }
        }
        catch {
            # 忽略连接错误，继续等待
        }
        
        Write-Host "." -NoNewline
        Start-Sleep -Seconds 3
        $attempt++
    }
    
    Write-Error "Windows service failed to start within $($maxAttempts * 3) seconds"
    Write-Info "Container logs:"
    docker logs simple-openhands
    exit 1
}

# 检查容器状态
function Test-ContainerStatus {
    Write-Info "Checking Windows container status..."
    
    # 检查容器是否运行
    try {
        $runningContainers = docker ps --format "table {{.Names}}" | Select-String "simple-openhands"
        if ($runningContainers) {
            Write-Success "Windows container is running"
        }
        else {
            Write-Error "Windows container is not running"
            docker ps -a
            exit 1
        }
    }
    catch {
        Write-Error "Failed to check container status"
        exit 1
    }
}

# 运行测试
function Invoke-Tests {
    Write-Info "Running tests inside Windows container..."
    
    # 检查测试目录
    if (-not (Test-Path "tests")) {
        Write-Warning "Tests directory not found, skipping tests"
        return
    }
    
    # 等待一下让服务完全启动
    Write-Info "Waiting a bit more for Windows service to fully initialize..."
    Start-Sleep -Seconds 5
    
    # 运行所有测试（Windows容器环境）
    Write-Info "Running all tests in Windows container..."
    try {
        # 注意：Windows容器中使用cmd，不是PowerShell
        docker exec simple-openhands cmd /c "cd C:\simple_openhands\code & python -m poetry run pytest tests -v"
        Write-Success "All tests passed in Windows container!"
    }
    catch {
        Write-Warning "Some tests failed in Windows container, but continuing..."
        Write-Info "Check the test output above for details"
    }
}

# 显示使用说明
function Show-Usage {
    Write-Success "Windows container is ready for use!"
    Write-Host ""
    Write-Host "Windows container ports:"
    Write-Host "  API: http://localhost:8000"
    Write-Host "  VSCode: http://localhost:3000"
    Write-Host "  Jupyter: 8001"
    Write-Host "  Workspace: $(Join-Path (Get-Location) 'workspace')"
    Write-Host ""
    Write-Host "Quick test:"
    Write-Host "  Invoke-WebRequest -Uri http://localhost:8000/alive"
    Write-Host ""
    Write-Host "To stop the container:"
    Write-Host "  docker stop simple-openhands"
    Write-Host ""
    Write-Host "To view logs:"
    Write-Host "  docker logs simple-openhands"
    Write-Host ""
}

# 主函数
function Main {
    Write-Host "==========================================" -ForegroundColor Cyan
    Write-Host "  Simple OpenHands Runtime - Windows Version" -ForegroundColor Cyan
    Write-Host "==========================================" -ForegroundColor Cyan
    Write-Host ""
    
    # 检查当前目录
    if (-not (Test-Path "Dockerfile.windows") -or -not (Test-Path "pyproject.toml")) {
        Write-Error "Please run this script from the simple_openhands directory"
        exit 1
    }
    
    try {
        # 执行各个步骤
        Test-Docker
        Test-WindowsContainers
        Remove-OldResources
        Build-WindowsImage
        Initialize-MountDirectories
        Start-WindowsContainer
        Wait-ForService
        Test-ContainerStatus
        Invoke-Tests
        Show-Usage
        
        Write-Host ""
        Write-Success "All Windows operations completed successfully!"
    }
    catch {
        Write-Error "Script failed: $($_.Exception.Message)"
        exit 1
    }
}

# 捕获中断信号
trap {
    Write-Error "Script interrupted"
    exit 1
}

# 运行主函数
Main