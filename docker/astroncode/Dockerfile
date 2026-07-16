# AstronCode 评测镜像：在 codex 评测镜像之上叠加 @iflytek/astron-code CLI。
# 构建需要访问 iflytek 内网 npm registry；离线分发通过 docker save 出 tar。
FROM wildclawbench-codex-ubuntu:v0.0

#ARG ASTRON_CODE_VERSION=0.0.5-benchmark-adapt.10
ARG ASTRON_CODE_VERSION=0.0.5-test.8
ARG NPM_REGISTRY=https://depend.iflytek.com/artifactory/api/npm/npm-repo/

RUN npm uninstall -g @iflytek/astron-code >/dev/null 2>&1 || true \
    && npm install -g "@iflytek/astron-code@${ASTRON_CODE_VERSION}" \
      --registry="${NPM_REGISTRY}" \
    && astron-code --version

# Astron Spark 模型配置（provider + model catalog + profile），安装到 /root/.acode：
# - /root/.acode/astron-spark.json          模型 catalog
# - /root/.acode/astron-spark.config.toml   profile（默认 xsparkx2flash）
# - /root/.acode/config.toml                追加 [model_providers.astron-spark]
# 运行时需提供 ASTRON_SPARK_API_KEY（配置包本身不含密钥）
COPY codex-astron-config /opt/codex-astron-config
RUN CODEX_HOME=/root/.acode sh /opt/codex-astron-config/scripts/install-macos-linux.sh \
    && cat /root/.acode/config.toml
