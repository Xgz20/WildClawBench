# AstronClaw 评测镜像：保留产品镜像，只叠加 WildClawBench 的稳定评测环境。
# 构建依赖本地已有 wildclawbench-codex-ubuntu:v0.0；可通过 build-arg 替换。
ARG EVAL_BASE_IMAGE=wildclawbench-codex-ubuntu:v0.0
ARG ASTRONCLAW_BASE_IMAGE=artifacts.iflytek.com/docker-private/hy-spark-agent-builder/astronclaw-core-cicd:v0.2.9
FROM ${EVAL_BASE_IMAGE} AS eval-base

FROM ${ASTRONCLAW_BASE_IMAGE}

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

ARG PIP_INDEX_URL=https://pypi.org/simple

# 复用已验证的 Python 3.11 评测环境。目标路径同时满足 SAM3 任务的固定路径约定。
COPY --from=eval-base /root/miniconda3/envs/eval /root/miniconda3/envs/eval
COPY --from=eval-base /usr/lib/node_modules/agent-browser /usr/lib/node_modules/agent-browser

ENV PATH="/root/miniconda3/envs/eval/bin:${PATH}" \
    PIP_BREAK_SYSTEM_PACKAGES=1 \
    PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright \
    PLAYWRIGHT_HOST_PLATFORM_OVERRIDE=ubuntu24.04-x64

RUN ln -sfn /root/miniconda3/envs/eval/bin/python /usr/local/bin/python \
    && ln -sfn /root/miniconda3/envs/eval/bin/python3 /usr/local/bin/python3 \
    && ln -sfn /root/miniconda3/envs/eval/bin/pip /usr/local/bin/pip \
    && ln -sfn /root/miniconda3/envs/eval/bin/pip3 /usr/local/bin/pip3 \
    && ln -sfn /usr/lib/node_modules/agent-browser/bin/agent-browser-linux-x64 /usr/local/bin/agent-browser

# SAM3 warmup 固定要求这两个版本；其余依赖来自统一 eval 环境。
RUN pip install --no-cache-dir --index-url="${PIP_INDEX_URL}" \
      numpy==1.26.4 \
      opencv-python==4.9.0.80 \
      ortools==9.10.4067 \
    && python3 -m playwright install chromium

RUN rm -f /etc/apt/sources.list \
    && sed -i \
      -e 's#http://archive.ubuntu.com/ubuntu/#https://mirrors.aliyun.com/ubuntu/#g' \
      -e 's#http://security.ubuntu.com/ubuntu/#https://mirrors.aliyun.com/ubuntu/#g' \
      /etc/apt/sources.list.d/ubuntu.sources \
    && apt-get -o Acquire::Retries=5 update \
    && apt-get -o Acquire::Retries=5 install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# 构建期门禁：同时验证评测依赖和 AstronClaw CLI，防止只构建成功但无法跑批。
RUN python3 -c "import PIL, cv2, numpy, playwright; print(numpy.__version__, cv2.__version__)" \
    && test -x /root/miniconda3/envs/eval/bin/pip \
    && python3 -c "from pathlib import Path; from playwright.sync_api import sync_playwright; p = sync_playwright().start(); executable = Path(p.chromium.executable_path); print(executable); assert executable.is_file(); p.stop()" \
    && agent-browser --version \
    && ffmpeg -version | head -n 1 \
    && openclaw --version
