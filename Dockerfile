FROM python:3.12-slim-bookworm

ENV LANG=C.UTF-8 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    WORK_DIR=/simple_openhands/workspace \
    HOST=0.0.0.0 \
    PORT=8000 \
    USERNAME=peter \
    OH_ENABLE_PLUGINS=0

RUN apt-get update && \
    apt-get install -y --no-install-recommends bash ca-certificates curl git tmux && \
    rm -rf /var/lib/apt/lists/* && \
    useradd -m -U -s /bin/bash -u 1000 peter && \
    install -d -o peter -g peter /simple_openhands/code /simple_openhands/workspace && \
    printf 'unset PROMPT_COMMAND\n' > /home/peter/.bashrc

WORKDIR /simple_openhands/code
COPY pyproject.toml README.md ./
COPY --chown=peter:peter simple_openhands/ ./simple_openhands/
RUN pip install --no-cache-dir '.[runtime]'

USER peter
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/alive | grep -q '"bash_session_active":true'

CMD ["python", "-m", "simple_openhands.main"]
