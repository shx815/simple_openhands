FROM python:3.12-slim

# Shared environment variables 
ENV POETRY_VIRTUALENVS_PATH=/simple_openhands/poetry \
    MAMBA_ROOT_PREFIX=/simple_openhands/micromamba \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    EDITOR=code \
    VISUAL=code \
    GIT_EDITOR="code --wait" \
    OPENVSCODE_SERVER_ROOT=/simple_openhands/.openvscode-server \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    WORK_DIR=/simple_openhands/workspace \
    HOST=0.0.0.0 \
    PORT=8000 \
    USERNAME=appuser \
    VSCODE_PORT=3000 \
    JUPYTER_PORT=8001

# Install base system dependencies 
RUN set -eux; \
    apt-get update -o Acquire::Retries=5 && \
    apt-get install -y --no-install-recommends --fix-missing \
      wget curl ca-certificates sudo apt-utils git tmux build-essential && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Install uv (required by MCP) 
RUN curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR="/simple_openhands/bin" sh
# Add /simple_openhands/bin to PATH
ENV PATH="/simple_openhands/bin:${PATH}"

# Remove UID 1000 named pn or ubuntu, so the 'simple_openhands' user can be created from ubuntu hosts
RUN (if getent passwd 1000 | grep -q pn; then userdel pn; fi) && \
    (if getent passwd 1000 | grep -q ubuntu; then userdel ubuntu; fi)

# Create necessary directories 
RUN mkdir -p /simple_openhands && \
    mkdir -p /simple_openhands/logs && \
    mkdir -p /simple_openhands/poetry

# Install micromamba
RUN mkdir -p /simple_openhands/micromamba/bin && \
    /bin/bash -c "PREFIX_LOCATION=/simple_openhands/micromamba BIN_FOLDER=/simple_openhands/micromamba/bin INIT_YES=no CONDA_FORGE_YES=yes $(curl -L https://micro.mamba.pm/install.sh)" && \
    /simple_openhands/micromamba/bin/micromamba config remove channels defaults && \
    /simple_openhands/micromamba/bin/micromamba config list

# Create the simple_openhands virtual environment and install poetry and python
RUN /simple_openhands/micromamba/bin/micromamba create -n simple_openhands -y && \
    /simple_openhands/micromamba/bin/micromamba install -n simple_openhands -c conda-forge poetry python=3.12 -y

# Configure micromamba and poetry
RUN /simple_openhands/micromamba/bin/micromamba config set changeps1 False && \
    /simple_openhands/micromamba/bin/micromamba run -n simple_openhands poetry config virtualenvs.path /simple_openhands/poetry

# 创建工作目录 
RUN mkdir -p /simple_openhands/code && \
    mkdir -p /simple_openhands/workspace

# 复制Poetry配置文件 (提前复制以利用Docker缓存)
COPY pyproject.toml /simple_openhands/code/

# 设置工作目录
WORKDIR /simple_openhands/code

# 为测试与本地运行提供稳定的模块搜索路径
ENV PYTHONPATH=/simple_openhands/code:/simple_openhands/code/simple_openhands

# 安装依赖（所有依赖都在主依赖中）
RUN /simple_openhands/micromamba/bin/micromamba run -n simple_openhands poetry install --no-interaction --no-root

# 复制应用代码 (在安装依赖之后复制，避免缓存失效)
RUN mkdir -p /simple_openhands/code/simple_openhands && \
    touch /simple_openhands/code/simple_openhands/__init__.py
COPY --chown=appuser:appuser --chmod=777 simple_openhands/ /simple_openhands/code/simple_openhands/
COPY --chown=appuser:appuser --chmod=777 tests/ /simple_openhands/code/tests/

# 清理缓存 (缓存清理策略)
RUN /simple_openhands/micromamba/bin/micromamba run -n simple_openhands poetry cache clear --all . -n && \
    apt-get clean && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/* && \
    /simple_openhands/micromamba/bin/micromamba clean --all

# 测试Poetry安装是否成功
RUN /simple_openhands/micromamba/bin/micromamba run -n simple_openhands poetry --version

# 关键修复：设置 Poetry 虚拟环境的 PATH
RUN /simple_openhands/micromamba/bin/micromamba run -n simple_openhands poetry env info --path > /tmp/poetry_env_path.txt && \
    echo "export PATH=\"$(cat /tmp/poetry_env_path.txt)/bin:\$PATH\"" >> /etc/environment && \
    rm /tmp/poetry_env_path.txt

# Set environment variables and permissions (环境变量设置)
RUN /simple_openhands/micromamba/bin/micromamba run -n simple_openhands poetry run python -c "import sys; print('OH_INTERPRETER_PATH=' + sys.executable)" >> /etc/environment && \
    chmod -R g+rws /simple_openhands/poetry

# ================================================================
# Setup VSCode Server 
# ================================================================
# Reference:
# 1. https://github.com/gitpod-io/openvscode-server
# 2. https://github.com/gitpod-io/openvscode-releases

# Setup VSCode Server
ARG RELEASE_TAG="openvscode-server-v1.98.2"
ARG RELEASE_ORG="gitpod-io"

RUN if [ -z "${RELEASE_TAG}" ]; then \
        echo "The RELEASE_TAG build arg must be set." >&2 && \
        exit 1; \
    fi && \
    arch=$(uname -m) && \
    if [ "${arch}" = "x86_64" ]; then \
        arch="x64"; \
    elif [ "${arch}" = "aarch64" ]; then \
        arch="arm64"; \
    elif [ "${arch}" = "armv7l" ]; then \
        arch="armhf"; \
    fi && \
    wget https://github.com/${RELEASE_ORG}/openvscode-server/releases/download/${RELEASE_TAG}/${RELEASE_TAG}-linux-${arch}.tar.gz && \
    tar -xzf ${RELEASE_TAG}-linux-${arch}.tar.gz && \
    if [ -d "${OPENVSCODE_SERVER_ROOT}" ]; then rm -rf "${OPENVSCODE_SERVER_ROOT}"; fi && \
    mv ${RELEASE_TAG}-linux-${arch} ${OPENVSCODE_SERVER_ROOT} && \
    cp ${OPENVSCODE_SERVER_ROOT}/bin/remote-cli/openvscode-server ${OPENVSCODE_SERVER_ROOT}/bin/remote-cli/code && \
    rm -f ${RELEASE_TAG}-linux-${arch}.tar.gz

# 创建用户 (优化版本，避免递归chown)
RUN useradd -m -s /bin/bash appuser \
    && chown appuser:appuser /simple_openhands \
    && chmod 777 /simple_openhands

# 完全替换 .bashrc 文件，避免任何 PS1 冲突
RUN rm -f /home/appuser/.bashrc \
    && echo '# Minimal .bashrc for App' > /home/appuser/.bashrc \
    && echo 'export PATH=/simple_openhands/bin:/usr/local/bin:/usr/bin:/bin' >> /home/appuser/.bashrc \
    && echo 'export PATH="/simple_openhands/poetry/simple-openhands-*/bin:$PATH"' >> /home/appuser/.bashrc \
    && echo 'unset PROMPT_COMMAND' >> /home/appuser/.bashrc \
    && chown appuser:appuser /home/appuser/.bashrc

# 创建 tmux 目录并设置权限
RUN mkdir -p /tmp/tmux-1000 \
    && chown -R appuser:appuser /tmp/tmux-1000 \
    && chmod 700 /tmp/tmux-1000

# 设置文件权限
RUN chmod -R g+rws,o+rw /simple_openhands/workspace && \
    chmod -R g+rws,o+rw /simple_openhands/code

# 切换到用户
USER appuser

# 暴露端口
EXPOSE 8000 3000 8001

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/alive || exit 1

# 直接使用 Poetry 虚拟环境的 Python
CMD ["/bin/bash", "-c", "source /etc/environment && /simple_openhands/micromamba/bin/micromamba run -n simple_openhands poetry run python -m simple_openhands.main"]