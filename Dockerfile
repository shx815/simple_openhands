FROM ubuntu:22.04

SHELL ["/bin/bash", "-c"]

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
    USERNAME=peter \
    VSCODE_PORT=3000 \
    JUPYTER_PORT=8001

# Install base system dependencies and Python 3.12
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        software-properties-common gnupg2 && \
    add-apt-repository ppa:deadsnakes/ppa -y && \
    apt-get update && \
    TZ=Etc/UTC DEBIAN_FRONTEND=noninteractive \
    apt-get install -y --no-install-recommends \
        wget curl ca-certificates sudo apt-utils git tmux build-essential \
        python3.12 python-is-python3 python3-pip python3.12-venv \
        file tree binutils && \
    # Set Python 3.12 as the default python3
    update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.12 1 && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Install Poetry system-wide (matches OpenHands template)
RUN curl -fsSL --compressed https://install.python-poetry.org | python -

# Install uv (required by MCP) 
RUN curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR="/simple_openhands/bin" sh

# Add /simple_openhands/bin to PATH
ENV PATH="/simple_openhands/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

# Remove UID 1000 named pn or ubuntu, so the 'simple_openhands' user can be created from ubuntu hosts
RUN (if getent passwd 1000 | grep -q pn; then userdel pn; fi) && \
    (if getent passwd 1000 | grep -q ubuntu; then userdel ubuntu; fi)

# Create necessary directories 
RUN mkdir -p /simple_openhands && \
    mkdir -p /simple_openhands/poetry

# Install micromamba
RUN mkdir -p /simple_openhands/micromamba/bin && \
    /bin/bash -c "PREFIX_LOCATION=/simple_openhands/micromamba BIN_FOLDER=/simple_openhands/micromamba/bin INIT_YES=no CONDA_FORGE_YES=yes $(curl -L https://micro.mamba.pm/install.sh)" && \
    /simple_openhands/micromamba/bin/micromamba config remove channels defaults && \
    /simple_openhands/micromamba/bin/micromamba config list

# Create the simple_openhands virtual environment and install poetry and python
RUN /simple_openhands/micromamba/bin/micromamba create -n simple_openhands -y && \
    /simple_openhands/micromamba/bin/micromamba install -n simple_openhands -c conda-forge poetry python=3.12 -y

# 创建工作目录 
RUN mkdir -p /simple_openhands/code && \
    mkdir -p /simple_openhands/workspace

# 复制Poetry配置文件 (提前复制以利用Docker缓存)
COPY pyproject.toml /simple_openhands/code/

# 设置工作目录
WORKDIR /simple_openhands/code

# Configure micromamba and poetry (必须在 WORKDIR 之后，因为 poetry env use 需要 pyproject.toml)
RUN /simple_openhands/micromamba/bin/micromamba config set changeps1 False && \
    /simple_openhands/micromamba/bin/micromamba run -n simple_openhands poetry config virtualenvs.path /simple_openhands/poetry && \
    /simple_openhands/micromamba/bin/micromamba run -n simple_openhands poetry env use python3.12

# 为测试与本地运行提供稳定的模块搜索路径
ENV PYTHONPATH=/simple_openhands/code:/simple_openhands/code/simple_openhands

# 安装依赖和配置环境 (按照 OpenHands 的方式在一个 RUN 中完成)
RUN \
    # Install project dependencies (包括 server 和 cli extras)
    /simple_openhands/micromamba/bin/micromamba run -n simple_openhands poetry install --no-interaction --no-root --extras "server cli" && \
    # Set environment variables
    /simple_openhands/micromamba/bin/micromamba run -n simple_openhands poetry run python -c "import sys; print('OH_INTERPRETER_PATH=' + sys.executable)" >> /etc/environment && \
    # Set permissions before cleanup
    chmod -R g+rws /simple_openhands/poetry && \
    mkdir -p /simple_openhands/workspace && chmod -R g+rws,o+rw /simple_openhands/workspace && \
    # Clean up cache
    /simple_openhands/micromamba/bin/micromamba run -n simple_openhands poetry cache clear --all . -n && \
    apt-get clean && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/* && \
    /simple_openhands/micromamba/bin/micromamba clean --all

# 复制应用代码 (在安装依赖之后复制，避免缓存失效)
RUN mkdir -p /simple_openhands/code/simple_openhands && \
    touch /simple_openhands/code/simple_openhands/__init__.py
COPY --chown=peter:peter --chmod=777 simple_openhands/ /simple_openhands/code/simple_openhands/
COPY --chown=peter:peter --chmod=777 tests/ /simple_openhands/code/tests/

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

# 创建用户并配置 sudo 权限
RUN useradd -m -s /bin/bash -u 1000 peter \
    && echo "peter ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/peter \
    && chmod 0440 /etc/sudoers.d/peter \
    && chown peter:peter /simple_openhands \
    && chmod 777 /simple_openhands

# 完全替换 .bashrc 文件，避免任何 PS1 冲突
RUN rm -f /home/peter/.bashrc \
    && echo '# Minimal .bashrc for App' > /home/peter/.bashrc \
    && echo 'unset PROMPT_COMMAND' >> /home/peter/.bashrc \
    && chown peter:peter /home/peter/.bashrc

# 创建 tmux 目录并设置权限
RUN mkdir -p /tmp/tmux-1000 \
    && chown -R peter:peter /tmp/tmux-1000 \
    && chmod 700 /tmp/tmux-1000

# 设置文件权限
RUN chmod -R g+rws,o+rw /simple_openhands/workspace && \
    chmod -R g+rws,o+rw /simple_openhands/code

# 确保 CA 证书可用并刷新
USER root
RUN update-ca-certificates

# 切换到用户
USER peter

# 暴露端口
EXPOSE 8000 3000 8001

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/alive || exit 1

# 直接使用 Poetry 虚拟环境的 Python
CMD ["/bin/bash", "-c", "source /etc/environment && /simple_openhands/micromamba/bin/micromamba run -n simple_openhands poetry run python -m simple_openhands.main"]