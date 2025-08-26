#!/bin/bash

# Windows版本的部署和启动脚本
# 设置错误时退出
set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 日志函数
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 检查Docker是否运行
check_docker() {
    if ! docker info >/dev/null 2>&1; then
        log_error "Docker is not running. Please start Docker Desktop first."
        exit 1
    fi
    log_success "Docker is running"
}

# 检查Windows容器模式
check_windows_containers() {
    log_info "Checking Windows container mode..."
    
    # 检查Docker是否支持Windows容器
    if docker version --format '{{.Server.Os}}' 2>/dev/null | grep -q "windows"; then
        log_success "Windows containers are enabled"
    else
        log_warning "Windows containers not detected. Make sure to:"
        log_warning "1. Enable Windows containers in Docker Desktop"
        log_warning "2. Switch to Windows container mode"
        log_warning "3. Restart Docker Desktop if needed"
        echo
        read -p "Continue anyway? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log_error "Aborted by user"
            exit 1
        fi
    fi
}

# 清理旧容器和镜像
cleanup() {
    log_info "Cleaning up old containers and images..."
    
    # 停止并删除旧容器
    if docker ps -a --format "table {{.Names}}" | grep -q "simple-openhands-windows"; then
        log_info "Stopping and removing old container..."
        docker stop simple-openhands-windows 2>/dev/null || true
        docker rm simple-openhands-windows 2>/dev/null || true
        log_success "Old container cleaned up"
    fi
    
    # 检查是否有同名镜像
    if docker images --format "table {{.Repository}}" | grep -q "^simple-openhands-windows$"; then
        log_info "Found existing image: simple-openhands-windows"
        read -p "Do you want to remove old image and force rebuild? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            log_info "Removing old image..."
            docker rmi simple-openhands-windows 2>/dev/null || true
            log_success "Old image removed"
        fi
    else
        log_info "No existing image found, will build new one"
    fi
}

# 构建Windows镜像
build_windows_image() {
    log_info "Building Windows Docker image..."
    
    # 检查是否存在Dockerfile.windows
    if [ ! -f "Dockerfile.windows" ]; then
        log_error "Dockerfile.windows not found in current directory"
        exit 1
    fi
    
    # 首次构建提示
    echo
    log_warning "⚠️  首次构建时间较长，请耐心等待..."
    log_info "构建过程中会下载Windows基础镜像和安装依赖包"
    log_warning "Windows镜像构建通常比Linux镜像慢"
    echo
    
    # 构建Windows镜像
    if docker build -f Dockerfile.windows -t simple-openhands-windows .; then
        log_success "Windows image built successfully"
    else
        log_error "Failed to build Windows image"
        exit 1
    fi
}

# 准备挂载目录
prepare_mounts() {
    log_info "Preparing mount directories..."
    
    # 创建workspace目录（让Docker自动处理权限）
    mkdir -p "$(pwd)/workspace"
    
    log_success "Mount directories prepared"
}

# 启动Windows容器
start_container() {
    log_info "Starting Windows container..."
    
    # 启动Windows容器
    docker run -d --name simple-openhands-windows \
        -p 8000:8000 \
        -p 3000:3000 \
        -p 8001:8001 \
        -v "$(pwd)/workspace:C:/workspace" \
        simple-openhands-windows
    
    if [ $? -eq 0 ]; then
        log_success "Windows container started successfully"
    else
        log_error "Failed to start Windows container"
        exit 1
    fi
}

# 等待服务启动
wait_for_service() {
    log_info "Waiting for Windows service to start..."
    
    local max_attempts=60  # Windows容器启动通常更慢
    local attempt=1
    
    while [ $attempt -le $max_attempts ]; do
        if curl -s "http://localhost:8000/alive" >/dev/null 2>&1; then
            log_success "Windows service is ready (attempt $attempt/$max_attempts)"
            return 0
        fi
        
        log_info "Waiting for Windows service... (attempt $attempt/$max_attempts)"
        sleep 3  # Windows容器需要更多时间
        attempt=$((attempt + 1))
    done
    
    log_error "Windows service failed to start within $((max_attempts * 3)) seconds"
    log_info "Container logs:"
    docker logs simple-openhands-windows
    exit 1
}

# 检查容器状态
check_container_status() {
    log_info "Checking Windows container status..."
    
    # 检查容器是否运行
    if docker ps --format "table {{.Names}}" | grep -q "simple-openhands-windows"; then
        log_success "Windows container is running"
    else
        log_error "Windows container is not running"
        docker ps -a
        exit 1
    fi
    
    # 显示容器信息
    log_info "Windows container details:"
    docker ps --filter "name=simple-openhands-windows" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
    
    # 显示容器日志（最近15行）
    log_info "Recent Windows container logs:"
    docker logs --tail 15 simple-openhands-windows
}

# 运行测试（Windows版本）
run_tests() {
    log_info "Running tests inside Windows container..."
    
    # 检查测试目录
    if [ ! -d "tests" ]; then
        log_warning "Tests directory not found, skipping tests"
        return 0
    fi
    
    # 等待一下让服务完全启动
    log_info "Waiting a bit more for Windows service to fully initialize..."
    sleep 10  # Windows容器需要更多时间
    
    # 运行所有测试（Windows PowerShell环境）
    log_info "Running all tests in Windows container..."
    if docker exec -it simple-openhands-windows powershell -Command "cd C:/simple_openhands/code; C:/simple_openhands/micromamba/bin/micromamba.exe run -n simple_openhands poetry run pytest tests -v"; then
        log_success "All tests passed in Windows container!"
    else
        log_warning "Some tests failed in Windows container, but continuing..."
        log_info "You can check test details later with: docker exec -it simple-openhands-windows powershell"
    fi
}

# 显示使用说明
show_usage() {
    log_info "Windows container is ready for use!"
    echo
    echo "Windows container ports:"
    echo "  API: http://localhost:8000"
    echo "  VSCode: http://localhost:3000"
    echo "  Jupyter: 8001"
    echo "  Workspace: $(pwd)/workspace"
    echo
    echo "Quick test:"
    echo "  curl http://localhost:8000/alive"
    echo
    echo "Useful commands:"
    echo "  View logs:        docker logs -f simple-openhands-windows"
    echo "  Enter container:  docker exec -it simple-openhands-windows powershell"
    echo "  Stop container:   docker stop simple-openhands-windows"
    echo "  Remove container: docker rm simple-openhands-windows"
    echo
    echo "Note: This container uses Windows PowerShell instead of bash"
}

# 主函数
main() {
    echo "=========================================="
    echo "  Simple OpenHands Runtime - Windows Version"
    echo "=========================================="
    echo
    
    # 检查当前目录
    if [ ! -f "Dockerfile.windows" ] || [ ! -f "pyproject.toml" ]; then
        log_error "Please run this script from the simple_openhands directory"
        exit 1
    fi
    
    # 执行各个步骤
    check_docker
    check_windows_containers
    cleanup
    build_windows_image
    prepare_mounts
    start_container
    wait_for_service
    check_container_status
    run_tests
    show_usage
    
    echo
    log_success "All Windows operations completed successfully!"
}

# 捕获中断信号
trap 'log_error "Script interrupted"; exit 1' INT TERM

# 运行主函数
main "$@"
