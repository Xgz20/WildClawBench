# AstronCode 0.0.42 evaluation image with connector-based SearchAgent, local
# Web Fetch MCP, and PPT rendering. Runtime credentials are not included.
FROM wildclawbench-codex-ubuntu:v0.0

ARG ASTRON_CODE_VERSION=0.0.42
ARG NODEJS_VERSION=22.23.2-1nodesource1
ARG NPM_REGISTRY=https://depend.iflytek.com/artifactory/api/npm/npm-repo/

ENV PATH="/root/.local/bin:${PATH}"

# AstronCode 0.0.42 requires Node.js 22 or newer. The Codex base image uses
# NodeSource 20, so this image switches the existing signed repository.
RUN rm -f /etc/apt/sources.list.d/google-chrome.list \
      /etc/apt/sources.list.d/google-chrome.sources \
    && sed -i 's#https://deb.nodesource.com/node_20.x#https://deb.nodesource.com/node_22.x#' \
      /etc/apt/sources.list.d/nodesource.sources \
    && apt-get update \
    && apt-get install -y --no-install-recommends "nodejs=${NODEJS_VERSION}" \
    && rm -rf /var/lib/apt/lists/* \
    && node -e 'const major = Number(process.versions.node.split(".")[0]); if (major < 22) process.exit(1)' \
    && node --version \
    && npm --version

RUN npm uninstall -g @iflytek/astron-code >/dev/null 2>&1 || true \
    && npm install -g "@iflytek/astron-code@${ASTRON_CODE_VERSION}" \
      --registry="${NPM_REGISTRY}" \
    && astron-code --version \
    && rm -rf /root/.acode \
    && install -d -o root -g root -m 700 /root/.acode

# web_fetch is a Linux x86_64 offline bundle supplied as a BuildKit named
# context. It remains outside Git and is copied into the image verbatim.
COPY --from=web_fetch / /opt/astroncode/web-fetch/
COPY search-agent.config.toml /opt/astroncode/search-agent.config.toml
COPY verify_search_agent.py /tmp/verify_search_agent.py

# macOS case-insensitive filesystems collapse duplicate A/a and X/x terminfo
# aliases. They are unrelated to web_fetch, so verify every other checksummed
# payload and validate the executable runtime below.
RUN chmod 755 \
      /opt/astroncode/web-fetch/start-mcp.sh \
      /opt/astroncode/web-fetch/check-system-deps.sh \
    && cd /opt/astroncode/web-fetch \
    && awk '$2 !~ /^\.\/python\/share\/terminfo\//' SHA256SUMS \
      | sha256sum --check --quiet - \
    && ./check-system-deps.sh \
    && ./python/bin/python3 /tmp/verify_search_agent.py \
    && python3 -c 'import tomllib, sys; config = tomllib.load(open(sys.argv[1], "rb")); server = config.get("mcp_servers", {}).get("web_fetch"); expected = {"enabled": True, "command": "/opt/astroncode/web-fetch/start-mcp.sh", "startup_timeout_sec": 60, "tool_timeout_sec": 300, "default_tools_approval_mode": "approve"}; sys.exit(0 if server == expected and set(config) == {"mcp_servers"} else "invalid web_fetch MCP config")' /opt/astroncode/search-agent.config.toml \
    && rm -f /tmp/verify_search_agent.py

# PPT rubric grading runs inside this same task container. LibreOffice renders
# final PPTX deliverables to PDF; the base image provides PyMuPDF for PNG output.
RUN sed -i \
      -e 's#http://archive.ubuntu.com/ubuntu/#https://mirrors.tuna.tsinghua.edu.cn/ubuntu/#g' \
      -e 's#http://security.ubuntu.com/ubuntu#https://mirrors.tuna.tsinghua.edu.cn/ubuntu#g' \
      /etc/apt/sources.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends libreoffice-impress \
    && rm -rf /var/lib/apt/lists/* \
    && command -v soffice \
    && soffice --version \
    && python3 -c 'import fitz; print(fitz.__version__)'
