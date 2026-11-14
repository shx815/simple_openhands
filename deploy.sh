#!/bin/bash

# Linux版本的部署和启动脚本
# 设置错误时退出
set -e

if ! command -v docker >/dev/null 2>&1 && [ -x "$HOME/.docker/bin/docker" ]; then
    export PATH="$HOME/.docker/bin:$PATH"
fi

image=simple-openhands:latest
dockerfile=Dockerfile

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

# 替换同名容器
cleanup() {
    log_info "Checking for an existing container..."

    # 停止并删除旧容器
    if docker ps -a --format "{{.Names}}" | grep -qx "simple-openhands"; then
        log_info "Stopping and removing old container..."
        docker stop simple-openhands 2>/dev/null || true
        docker rm simple-openhands 2>/dev/null || true
        log_success "Old container cleaned up"
    fi
}

# 构建Linux镜像
build_linux_image() {
    log_info "Building Linux Docker image..."
    
    # 检查是否存在Dockerfile
    if [ ! -f "$dockerfile" ]; then
        log_error "$dockerfile not found in current directory"
        exit 1
    fi
    
    # 首次构建提示
    echo
    log_warning "⚠️  首次构建时间较长，请耐心等待..."
    log_info "构建过程中会下载基础镜像和安装依赖包"
    echo
    
    # 构建Linux镜像
    if docker build -f "$dockerfile" -t "$image" .; then
        log_success "Linux image built successfully"
    else
        log_error "Failed to build Linux image"
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

# 启动容器
start_container() {
    log_info "Starting container..."
    
    local bind_host=${OH_BIND_HOST:-127.0.0.1}
    local ports=(-p "${bind_host}:8000:8000")
    if [[ "$dockerfile" == Dockerfile.full ]]; then
        ports+=(-p 127.0.0.1:3000:3000)
    fi
    docker run -d --name simple-openhands \
        "${ports[@]}" \
        -e OH_API_TOKEN \
        -v "$(pwd)/workspace:/simple_openhands/workspace" \
        -e WORK_DIR=/simple_openhands/workspace \
        "$image"
    
    if [ $? -eq 0 ]; then
        log_success "Container started successfully"
    else
        log_error "Failed to start container"
        exit 1
    fi
}

# 等待服务启动
wait_for_service() {
    log_info "Waiting for service to start..."
    
    local max_attempts=45  # 增加等待时间
    local attempt=1
    
    while [ $attempt -le $max_attempts ]; do
        if docker exec simple-openhands curl -fsS --max-time 3 http://127.0.0.1:8000/alive 2>/dev/null |
            grep -q '"bash_session_active":true'; then
            log_success "Service is ready (attempt $attempt/$max_attempts)"
            return 0
        fi
        
        log_info "Waiting for service... (attempt $attempt/$max_attempts)"
        sleep 2
        attempt=$((attempt + 1))
    done
    
    log_error "Service failed to start within $((max_attempts * 2)) seconds"
    log_info "Container logs:"
    docker logs simple-openhands
    exit 1
}

# 检查容器状态
check_container_status() {
    log_info "Checking container status..."
    
    # 检查容器是否运行
    if docker ps --format "table {{.Names}}" | grep -q "simple-openhands"; then
        log_success "Container is running"
    else
        log_error "Container is not running"
        docker ps -a
        exit 1
    fi
    
    # 显示容器信息
    log_info "Container details:"
    docker ps --filter "name=simple-openhands" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
    
    # 显示容器日志（最近15行）
    log_info "Recent container logs:"
    docker logs --tail 15 simple-openhands
}

# 运行测试
run_tests() {
    if [[ "$dockerfile" == Dockerfile ]]; then
        log_info "Checking the base runtime's Shell API..."
        docker exec -i simple-openhands python - <<'PY'
import json
import os
from urllib.request import Request, urlopen

headers = {"Content-Type": "application/json"}
token = os.environ.get("OH_API_TOKEN")
if token:
    headers["Authorization"] = f"Bearer {token}"

request = Request(
    "http://127.0.0.1:8000/execute_action",
    data=json.dumps({"action": {"action": "run", "args": {"command": "pwd"}}}).encode(),
    headers=headers,
)
with urlopen(request, timeout=10) as response:
    result = json.load(response)
assert result["extras"]["metadata"]["exit_code"] == 0, result
assert result["content"].strip() == os.environ["WORK_DIR"], result
PY
        return
    fi

    log_info "Running tests inside container..."
    
    # 检查测试目录
    if [ ! -d "tests" ]; then
        log_warning "Tests directory not found, skipping tests"
        return 0
    fi
    
    # 等待一下让服务完全启动
    log_info "Waiting a bit more for service to fully initialize..."
    sleep 5
    
    # 运行所有测试
    log_info "Running all tests..."
    if docker exec simple-openhands bash -c "cd /simple_openhands/code && /simple_openhands/micromamba/bin/micromamba run -n simple_openhands poetry run pytest tests -v"; then
        log_success "All tests passed!"
    else
        log_error "Tests failed."
        log_info "You can check test details later with: docker exec -it simple-openhands bash"
        return 1
    fi
}

# 显示使用说明
show_usage() {
    log_info "Container is ready for use!"
    echo
    echo "Container ports:"
    echo "  API port: ${OH_BIND_HOST:-127.0.0.1}:8000"
    if [[ "$dockerfile" == Dockerfile.full ]]; then
        echo "  VS Code: http://localhost:3000"
    fi
    echo "  Workspace: $(pwd)/workspace"
    echo
    echo "Quick test:"
    echo "  docker exec simple-openhands curl http://127.0.0.1:8000/alive"
    echo
    echo "Useful commands:"
    echo "  View logs:        docker logs -f simple-openhands"
    echo "  Enter container:  docker exec -it simple-openhands bash"
    echo "  Stop container:   docker stop simple-openhands"
    echo "  Remove container: docker rm simple-openhands"
}

# 主函数
main() {
    case "${1:-}" in
        "") ;;
        --full)
            image=simple-openhands:full
            dockerfile=Dockerfile.full
            ;;
        *)
            log_error "Usage: ./deploy.sh [--full]"
            exit 2
            ;;
    esac

    echo "=========================================="
    echo "  Simple OpenHands Runtime - Linux Version"
    echo "=========================================="
    echo
    
    # 检查当前目录
    if [ ! -f "Dockerfile" ] || [ ! -f "pyproject.toml" ]; then
        log_error "Please run this script from the simple_openhands directory"
        exit 1
    fi
    
    export OH_API_TOKEN
    if [[ ${OH_BIND_HOST:-127.0.0.1} != 127.0.0.1 && -z ${OH_API_TOKEN:-} ]]; then
        log_error "Set OH_API_TOKEN before publishing the API on a non-loopback address."
        exit 1
    fi

    # 执行各个步骤
    check_docker
    build_linux_image
    cleanup
    prepare_mounts
    start_container
    wait_for_service
    check_container_status
    run_tests
    show_usage
    
    echo
    log_success "All operations completed successfully!"
}

# 捕获中断信号
trap 'log_error "Script interrupted"; exit 1' INT TERM

# 运行主函数
main "$@"
