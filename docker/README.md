# Harness CLI 镜像构建约定

后续新增或升级 Harness CLI 评测镜像，必须提供统一的
`docker/<harness>/build.sh` 入口和 `versions.json` 版本清单；构建命令写入
对应目录的 README。版本目录与镜像 tag 分别登记，不能从目录编号推断 tag。

- `versions.json` 绑定默认版本、完整镜像 tag、构建上下文、Dockerfile、CLI
  固定版本和基础镜像；升级时新建版本目录并保留历史映射。
- `build.sh` 支持省略版本时选择默认值，以及 `--version <镜像版本>` 和
  `--skip-save`；服务器仅构建时使用 `--skip-save`，避免占用离线包空间。
- 构建前确认依赖底座存在，构建失败必须退出；构建后检查实际 CLI 版本与
  清单一致。CLI 版本和基础镜像参数不能与选定版本的清单冲突。
- 支持 `NPM_REGISTRY` 和构建代理变量；API key 等运行时凭据不写入镜像。
- 读取版本清单的 Python 按仓库 `.venv/bin/python3`、`.venv/bin/python`、
  系统 `python3`、`uv run python` 的顺序选择。无需先激活虚拟环境，路径相对
  脚本所在仓库解析，支持从其他目录调用。
- 增加 Docker 替身测试，覆盖默认/历史版本、跳过导出和失败路径。静态测试
  与脚本测试通过不能替代真实镜像构建和评测冒烟。

当前四个 CLI 的服务器构建命令（仓库根目录执行，均不导出离线包）：

```bash
NPM_REGISTRY=https://registry.npmmirror.com bash docker/codex/build.sh --version v0.2 --skip-save
NPM_REGISTRY=https://registry.npmmirror.com bash docker/deepseek-harness/build.sh --version v0.3 --skip-save
NPM_REGISTRY=https://registry.npmmirror.com bash docker/claudecode/build.sh --version v0.4 --skip-save
NPM_REGISTRY=https://registry.npmmirror.com bash docker/opencode/build.sh --version v0.1 --skip-save
```

四者均使用 `wildclawbench-codex-ubuntu:v0.0` 作为评测底座；DeepSeek Harness
和 Claude Code 还需要可获取 `node:24-bookworm-slim`。各 Harness 的额外构建
依赖和历史版本以其版本清单与 README 为准。
