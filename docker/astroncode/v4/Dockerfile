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
    && astron-code --version \
    && rm -rf /root/.acode \
    && install -d -m 700 /root/.acode \
    && npm install -g "@iflytek/install-search-updater@${SEARCH_UPDATER_VERSION}" \
      --foreground-scripts \
      --registry="${NPM_REGISTRY}" \
    && install-search \
    && install-search doctor --full \
    && python3 -c 'import tomllib, sys; config = tomllib.load(open(sys.argv[1], "rb")); sys.exit(0 if set(config) == {"mcp_servers"} and isinstance(config["mcp_servers"], dict) and config["mcp_servers"] and all(isinstance(server, dict) for server in config["mcp_servers"].values()) else "invalid SearchAgent config")' /root/.acode/config.toml \
    && install -d -o root -g root -m 755 /opt/astroncode \
    && install -o root -g root -m 644 /root/.acode/config.toml /opt/astroncode/search-agent.config.toml
