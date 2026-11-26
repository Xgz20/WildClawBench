# OpenCode 评测镜像

OpenCode 镜像使用版本目录、`versions.json` 和统一 `build.sh` 构建入口维护。
当前正式版本为 `wildclawbench-opencode-ubuntu:v0.1`，内置
`opencode-ai@1.19.6`，构建上下文为 `v2`；`v1` 和 `v0.0` 保留用于历史结果复现。

## 构建

前置条件：本机 Docker daemon 已加载 `wildclawbench-codex-ubuntu:v0.0`。
读取版本清单时优先使用仓库 `.venv/bin/python3` 或 `.venv/bin/python`，
无需激活环境；没有仓库虚拟环境时回退到系统 `python3` 或 `uv run python`。

```bash
NPM_REGISTRY=https://registry.npmmirror.com \
  bash docker/opencode/build.sh --version v0.1 --skip-save

docker run --rm --entrypoint opencode \
  wildclawbench-opencode-ubuntu:v0.1 --version
```

省略 `--skip-save` 会导出：

```text
Images/wildclawbench-opencode-ubuntu_v0.1.tar.gz
```

省略 `--version` 会使用 `versions.json` 中的默认版本。历史镜像可显式构建：

```bash
bash docker/opencode/build.sh --version v0.0 --skip-save
```

构建脚本会校验版本、基础镜像、Dockerfile 所属版本目录，并在构建后执行
`opencode --version`；不会把运行时 API key 写入镜像。

## MaaS 模型上限

`WILDCLAW_MAAS_MAX_TOKENS_ENABLED` 默认关闭。开启时，runner 为 OpenCode
同时生成 `limit.context` 和 `limit.output`，不能只配置 output。

- 输出上限保持现有规则：显式 `MAAS_MAX_TOKENS` 优先，否则读取模型目录的
  `max_output_tokens`；没有可用输出上限时不注入 `limit`。
- 上下文长度优先使用显式 `OPENCODE_CONTEXT_WINDOW`，否则读取同一模型目录
  的 `context_window`，不写死全局默认值。无可信上下文、显式值无效或输出预算
  超过上下文长度时，预检直接报错，不启动任务容器。
- `model_limit_resolution.json` 保存实际 context、output 及来源，续跑沿用快照。
  旧快照若开启了输出注入却缺少 context，须使用新输出目录重新解析，不静默改变
  历史运行配置。
- 显式输出值超过目录发布上限时会告警，但保留用户覆盖值；是否被上游接受仍须
  独立验证。输出预算和上下文长度是两个不同参数，不可互相替代。

例如，可开启开关并省略两个显式数值，从目录解析模型限制；离线使用时则先从
可信模型资料核实两个数值，再同时设置 `MAAS_MAX_TOKENS` 和
`OPENCODE_CONTEXT_WINDOW`。只关闭开关时，这两个显式值不会注入 OpenCode。

上述修复位于宿主机 runner，无需因此改写已有镜像 tag 或重建 CLI 镜像。

真实镜像的离线配置/请求字段回归（镜像需已存在，不调用真实模型）：

```bash
WCB_RUN_OPENCODE_DOCKER_TESTS=1 \
  .venv/bin/python -m unittest tests.test_opencode_limit_integration
```

若本机没有 Docker daemon，可额外设置 `WCB_OPENCODE_DOCKER_SSH=user@host`，
使用该主机已有的同版镜像。测试只运行 `--rm --network none` 临时容器，在容器
回环地址启动 mock 服务；不挂载评测结果，不修改远程仓库或镜像。
