# AstronCode 0.0.42 evaluation image with SearchAgent and PPT rendering.
# Runtime credentials and model configuration are not included in this image.
FROM wildclawbench-codex-ubuntu:v0.0

ARG ASTRON_CODE_VERSION=0.0.42
ARG NODEJS_VERSION=22.23.2-1nodesource1
ARG SEARCH_UPDATER_VERSION=0.1.17
ARG NPM_REGISTRY=https://depend.iflytek.com/artifactory/api/npm/npm-repo/

ENV PATH="/root/.local/bin:${PATH}"

# AstronCode 0.0.42 requires Node.js 22 or newer. The Codex base image uses
# NodeSource 20, so v6 switches the existing signed repository to Node 22.
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
    && astron-code --version

# The updater's postinstall script runs bootstrap once in the foreground.
RUN rm -rf /root/.acode \
    && install -d -m 700 /root/.acode \
    && npm install -g "@iflytek/install-search-updater@${SEARCH_UPDATER_VERSION}" \
      --foreground-scripts \
      --registry="${NPM_REGISTRY}"

# AstronCode launches MCP processes with the per-server environment from this
# fragment. Keep Scrapling aligned with the browser location in the base image.
RUN python3 -c 'from pathlib import Path; p = Path("/root/.acode/config.toml"); s = p.read_text(encoding="utf-8"); marker = "[mcp_servers.scrapling.env]\n"; assignment = "PLAYWRIGHT_BROWSERS_PATH = \"/ms-playwright\"\n"; assert marker in s, "scrapling env table missing"; s = s if assignment in s else s.replace(marker, marker + assignment, 1); p.write_text(s, encoding="utf-8")'

COPY verify_search_agent.py /tmp/verify_search_agent.py

RUN /root/.local/bin/uv run --no-project \
      --index-url https://pypi.tuna.tsinghua.edu.cn/simple \
      --with mcp==1.29.0 \
      --with certifi \
      python /tmp/verify_search_agent.py \
    && install-search doctor --full \
    && python3 -c 'import tomllib, sys; config = tomllib.load(open(sys.argv[1], "rb")); sys.exit(0 if set(config) == {"mcp_servers"} and isinstance(config["mcp_servers"], dict) and config["mcp_servers"] and all(isinstance(server, dict) for server in config["mcp_servers"].values()) else "invalid SearchAgent config")' /root/.acode/config.toml \
    && install -d -o root -g root -m 755 /opt/astroncode \
    && install -o root -g root -m 644 /root/.acode/config.toml /opt/astroncode/search-agent.config.toml \
    && rm -f /tmp/verify_search_agent.py

# PPT rubric grading runs inside this same task container. LibreOffice renders
# final PPTX deliverables to PDF; the base eval environment already provides
# PyMuPDF (fitz) for converting PDF pages to PNG evidence.
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
