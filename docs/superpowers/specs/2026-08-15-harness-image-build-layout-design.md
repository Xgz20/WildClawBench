# Harness 镜像构建目录与版本绑定设计

## 目标

将仓库自建 Harness 镜像的构建入口与 Dockerfile 放在同一 Harness 目录中，并建立正式镜像 tag、Dockerfile 和默认构建参数的固定映射，避免 Dockerfile variant 与 `IMAGE_TAG` 被任意组合。

## 决策

采用“一个 Harness 一个构建脚本、一个版本清单、每个镜像迭代一个版本目录”的结构：

```text
docker/<harness>/
  build.sh
  versions.json
  v<version>/Dockerfile
```

- `build.sh` 维护构建、代理参数、能力检查和离线导出的公共逻辑。
- `versions.json` 是正式镜像名称、tag、Dockerfile 路径和版本 build arg 的唯一映射，使用 Python 标准库解析，不要求宿主机安装 PyYAML。
- 每次基于旧镜像产生新镜像版本时新增一个 `v1`/`v2` 版本目录，不在多个目录之间复制 Dockerfile。
- 现有 `script/build-*-image.sh` 保留为兼容包装，转发参数和环境变量到新入口。
- 历史设计/计划文档保留原路径；当前镜像更新日志、测试和源码注释切换到新入口。

## 命令接口

```bash
bash docker/astroncode/build.sh --version v0.4-ppt
bash docker/codex/build.sh --version v0.1
```

不传 `--version` 时使用清单的 `default`。正式版本不再接受独立的 `IMAGE_TAG` 与 Dockerfile variant 组合。为兼容已有调用，包装脚本把旧环境变量转换为版本选择；无法形成清单中合法映射时立即失败。

本阶段继续支持 `SKIP_SAVE=1`、npm registry 和内部代理。版本清单固定 CLI、SearchAgent 和基础镜像等影响镜像内容的参数；显式传入不同值时终止构建。改变输出日志或压缩行为不要求新增镜像 tag；改变 Dockerfile、基础镜像或影响镜像内容的 build arg 必须新增正式 tag。

## 版本映射

AstronCode 清单覆盖：

- `v0.1-test.8` -> `v1/Dockerfile`
- `v0.2` -> `v2/Dockerfile`
- `v0.3` -> `v3/Dockerfile`
- `v0.4-ppt` -> `v4/Dockerfile`

当前仓库无法从工作树中的 `v4/Dockerfile` 重建历史 `v0.4`，因为该文件已加入 PPT 依赖。因此 `v0.4` 只保留在更新日志中，不注册为可构建版本，避免错误复现。

Codex 清单覆盖 `v0.1` 和 `v1/Dockerfile`，固定 `CODEX_VERSION=0.146.0` 和 `EVAL_BASE_IMAGE=wildclawbench-codex-ubuntu:v0.0`，并拒绝不同的显式覆盖值。未来基于 `v0.1` 产生新 Codex 镜像时，新增 `v2/Dockerfile` 并更新清单。

## 校验与兼容性

- 静态契约测试验证每个清单版本的 Dockerfile 存在、路径不越界、完整 tag 与版本键一致。
- 构建脚本拒绝未知版本、未知参数、旧 variant/tag 不匹配和路径穿越。
- Docker stub 测试验证所选 Dockerfile、完整输出 tag、gzip 文件名和 `SKIP_SAVE` 行为。
- 旧命令路径在兼容期内保持可执行，且只负责 `exec` 新入口。
- AstronClaw-Eval 当前 CICD 没有直接引用这两个构建脚本，无需同步修改。
