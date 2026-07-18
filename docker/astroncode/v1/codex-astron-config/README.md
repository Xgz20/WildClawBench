# Astron Code 配置

这个分支只发布 Astron Code 的 Codex 配置，不包含 Codex 源码和构建产物。`master` 保留完整源码，不能用本分支构建 Codex。

配置不包含密钥。运行前需要通过运行环境提供 `ASTRON_SPARK_API_KEY`。

## macOS 和 Linux

```bash
export CODEX_HOME="$HOME/.codex"
git clone --depth 1 --branch astron-config \
  https://git.iflytek.com/hy_spark_agent_builder/codex.git \
  astron-code-config
sh astron-code-config/scripts/install-macos-linux.sh
export ASTRON_SPARK_API_KEY="实际密钥"
codex --profile astron-spark
```

脚本默认安装到 `~/.zcode`。本地复制命令显式使用 `~/.codex`；如需使用其他目录，在执行脚本前设置 `CODEX_HOME`。

## Windows

```powershell
$env:CODEX_HOME = Join-Path $HOME ".codex"
git clone --depth 1 --branch astron-config `
  https://git.iflytek.com/hy_spark_agent_builder/codex.git `
  astron-code-config
& "$PWD\astron-code-config\scripts\install-windows.ps1"
$env:ASTRON_SPARK_API_KEY = "实际密钥"
codex --profile astron-spark
```

## 选择模型

安装脚本默认选择 Spark-X2 Flash。其余模型使用同一个 profile，通过 `-m` 指定：

```bash
codex --profile astron-spark -m xopkimik27code
codex --profile astron-spark -m xopglm52
codex --profile astron-spark -m xopdeepseekv4pro
codex --profile astron-spark -m xsparkx2agent
```

## Docker

```bash
export CODEX_HOME=/acode
git clone --depth 1 --branch astron-config \
  https://git.iflytek.com/hy_spark_agent_builder/codex.git \
  astron-code-config
docker volume create astron-acode-home
docker run --rm --entrypoint sh \
  -e CODEX_HOME \
  -v "$PWD/astron-code-config:/astron-config:ro" \
  -v astron-acode-home:/acode \
  YOUR_CODEX_IMAGE \
  /astron-config/scripts/install-macos-linux.sh

export ASTRON_SPARK_API_KEY="实际密钥"
docker run --rm -it \
  -e CODEX_HOME \
  -e ASTRON_SPARK_API_KEY \
  -v astron-acode-home:/acode \
  YOUR_CODEX_IMAGE \
  codex --profile astron-spark
```

若镜像入口命令已是 `codex`，最后一行改为 `--profile astron-spark`。

## 内容

- `config/astron-spark.json`：五个模型的最小模型metadata。
- `scripts/`：安装到本地 Codex 或容器的脚本。
- `docs/validation.md`：字段保留和关闭的依据。
