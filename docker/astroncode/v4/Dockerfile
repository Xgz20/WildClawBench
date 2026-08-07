# AstronCode 0.0.13 evaluation image with a build-time SearchAgent fragment.
# Runtime credentials and model configuration are not included in this image.
FROM wildclawbench-codex-ubuntu:v0.0

ARG ASTRON_CODE_VERSION=0.0.13
ARG SEARCH_UPDATER_VERSION=latest
ARG NPM_REGISTRY=https://depend.iflytek.com/artifactory/api/npm/npm-repo/

ENV PATH="/root/.local/bin:${PATH}"

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
