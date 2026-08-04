# Codex CLI 升级层：在官方评测底座之上把 Codex CLI 换成新版。
#
# 底座 wildclawbench-codex-ubuntu:v0.0 是 WildClawBench 官方镜像（构建于
# 2026-04-19，内置 @openai/codex@0.121.0）。conda/playwright/chrome/node20/LaTeX
# 这套评测环境继续复用，只叠加一层 npm 全局安装替换 CLI 本身。
#
# 运行期配置不进镜像：runner 每个任务用 heredoc 重写 /root/.codex/config.toml
# （model/provider/base_url/sandbox 全部来自 env），凭据一律走容器启动参数。
ARG EVAL_BASE_IMAGE=wildclawbench-codex-ubuntu:v0.0
FROM ${EVAL_BASE_IMAGE}

# 锁定版本以保证镜像可复现（当前 npm latest 0.146.0）；升级只需改此默认值或传 --build-arg。
ARG CODEX_VERSION=0.146.0
# 淘宝镜像源：公共 registry 在内网/国内直连不稳定，且已验证它同时提供主包与
# @openai/codex-linux-x64 平台包（optionalDependencies 用 npm: 别名指向
# @openai/codex@<ver>-linux-x64，缺了它 bin/codex.js 会报 Missing optional dependency）。
ARG NPM_REGISTRY=https://registry.npmmirror.com

# registry 写进镜像 npmrc，容器内后续 npm 操作也走淘宝源。
RUN npm config set registry "${NPM_REGISTRY}"

# 先卸旧版：0.121.0 与 0.146.0 的平台包 vendor 布局不同
# （vendor/<triple>/codex/codex → vendor/<triple>/bin/codex），不留残留 node_modules。
# 再删 /root/.codex：底座里烘死了 model = "openai/gpt-5.3-codex" 的 config.toml
# 和旧版二进制的 arg0 shim，runner 启动时会重建目录并写入真实配置。
RUN npm uninstall -g @openai/codex >/dev/null 2>&1 || true \
    && npm install -g "@openai/codex@${CODEX_VERSION}" \
      --registry="${NPM_REGISTRY}" \
    && codex --version \
    && rm -rf /root/.codex \
    && install -d -m 700 /root/.codex /root/.codex/sessions
