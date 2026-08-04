# AstronCode v4 SearchAgent 镜像集成设计

## 决策摘要

新增自包含的 `docker/astroncode/v4/` 镜像定义，在 `wildclawbench-codex-ubuntu:v0.0` 基础上依次安装 AstronCode 0.0.13 和 SearchAgent。SearchAgent 通过官方安装器提供 Search、Fetch MCP 工具和 SearchBetter Skill；构建阶段运行完整 doctor 检查，避免生成工具不可用的镜像。

构建脚本、AstronCode Harness 默认镜像、`.env.example` 及 Linux/macOS 评测文档统一切换到 `wildclawbench-astroncode-ubuntu:v0.4`。v1-v3 镜像保留，不直接修改旧 Dockerfile，也继续允许显式选择旧 variant 和镜像标签。

SearchAgent 安装器会把 MCP 配置写入 `/root/.acode/config.toml`，而 Harness 每次评测前会重写该文件。v4 构建时因此将安装器生成的 MCP 配置另存为只读片段 `/opt/astroncode/search-agent.config.toml`；Runner 写入动态模型配置前读取并校验该片段，再同时追加到容器实际配置和宿主机脱敏配置。旧镜像不存在片段时保持原行为。

## 现状与问题

- `docker/astroncode/v3/Dockerfile` 只安装 AstronCode 0.0.13，不包含搜索工具、抓取工具或 SearchBetter Skill。
- `script/build-astroncode-image.sh` 默认构建 v3、标签为 `v0.3`，variant 白名单只包含 v1-v3。
- `AstronCodeAgent` 默认运行镜像是 `wildclawbench-astroncode-ubuntu:v0.3`。
- `AstronCodeAgent._write_codex_config()` 使用截断写入方式生成 `/root/.acode/config.toml`。即使 SearchAgent 在镜像构建期间写入 MCP 配置，评测启动后也会被删除。
- SearchAgent 安装器会在 `/root/.acode/` 下安装 `web-search` MCP、Scrapling MCP 和 `search-better` Skill，并生成对应 MCP 配置。Skill 目录不会被 Runner 的配置写入删除，但 MCP 配置必须显式保留和合并。

## 目标与非目标

### 目标

1. v4 镜像固定安装 AstronCode 0.0.13，并安装可覆盖版本的 SearchAgent updater。
2. 镜像内的 Search、Fetch 工具和 SearchBetter Skill 在实际评测配置写入后仍可用。
3. 默认构建、默认运行和评测文档都指向 v0.4。
4. v1-v3 和不包含 SearchAgent 配置片段的自定义镜像继续可用。
5. 构建和运行时配置不引入模型服务凭证泄漏。

### 非目标

- 不修改 AstronCode 或 SearchAgent 核心代码。
- 不删除或重写 v1-v3 Dockerfile。
- 不为其他 Harness 安装 SearchAgent。
- 不在本次改造中增加搜索服务地址、代理或凭证的运行时配置界面。
- 不改变现有 AstronCode provider、模型目录、trace 和 session 采集行为。

## v4 镜像设计

### 基础镜像与构建参数

新增 `docker/astroncode/v4/Dockerfile`，不依赖 v0.3 镜像层，直接使用：

```dockerfile
FROM wildclawbench-codex-ubuntu:v0.0
```

构建参数为：

```dockerfile
ARG ASTRON_CODE_VERSION=0.0.13
ARG SEARCH_UPDATER_VERSION=latest
ARG NPM_REGISTRY=https://depend.iflytek.com/artifactory/api/npm/npm-repo/
```

`ASTRON_CODE_VERSION` 默认固定为 0.0.13，确保默认构建可复现 AstronCode 版本。`SEARCH_UPDATER_VERSION` 默认采用 `latest`，同时允许构建时指定版本以便故障回退或复现。两个 npm 包使用同一内网 registry。

### 安装顺序

Dockerfile 按以下顺序执行：

1. 卸载基础镜像中可能存在的 `@iflytek/astron-code`，安装 `@iflytek/astron-code@${ASTRON_CODE_VERSION}`。
2. 执行 `astron-code --version`，在构建阶段校验 CLI 可执行。
3. 删除基础镜像或 AstronCode 安装过程产生的 `/root/.acode`，重新创建权限为 `0700` 的空目录。
4. 安装 `@iflytek/install-search-updater@${SEARCH_UPDATER_VERSION}`，参数包含 `--foreground-scripts` 和内网 registry。
5. 执行 `install-search`，安装 MCP 服务、Python/浏览器依赖和 SearchBetter Skill。
6. 执行 `install-search doctor --full`，校验依赖、MCP handshake 和 Skill。
7. 校验安装器生成的 `/root/.acode/config.toml` 顶层只包含非空的 `mcp_servers` 表，保存为 `/opt/astroncode/search-agent.config.toml`。
8. 将配置片段及其父目录设为 root 所有、普通用户不可写；保留 `/root/.acode/skills/search-better` 和 MCP 实现文件。

清理 `/root/.acode` 必须发生在 `install-search` 之前，否则会删除 SearchBetter Skill、MCP 实现和安装状态。v4 不把 API Key、模型 provider 配置或评测任务配置写入镜像层。

## 运行时配置合并

### 配置片段契约

固定路径：

```text
/opt/astroncode/search-agent.config.toml
```

该文件是镜像内静态配置，只允许以下结构：

```toml
[mcp_servers.<server-name>]
# SearchAgent 安装器生成的命令、参数和环境配置
```

片段不得包含 `model_provider`、`model_providers`、模型服务 bearer token 或其他 AstronCode 全局配置。构建时和运行时都使用 TOML 解析器检查顶层键集合严格等于 `{"mcp_servers"}`，且 `mcp_servers` 是非空表。校验后仍保留安装器原始 TOML 文本，不自行序列化 MCP 子表，避免数组、布尔值或嵌套表在转换时丢失类型。

### Runner 数据流

`AstronCodeAgent._write_codex_config()` 在已有模型配置渲染流程中增加一个独立的片段读取步骤：

1. 通过 `docker exec` 检查并读取容器内固定路径。
2. 文件不存在时返回空片段，按 v1-v3 旧镜像行为继续。
3. 文件存在时使用 Python 标准库 `tomllib` 解析并校验顶层结构。
4. 文件不可读、TOML 非法、结构不符合契约或 `mcp_servers` 为空时立即终止当前评测，并给出不含片段内容的配置错误。
5. 将通过校验的片段追加到容器实际 `config.toml`。
6. 将同一片段追加到评测结果目录的脱敏 `config.toml`。

动态模型配置与 MCP 片段之间写入一个空行，并保证文件末尾换行。动态配置本身不生成 `mcp_servers`，因此不存在 TOML 表重名。容器实际配置仍以 `0600` 权限写入。

宿主机 `config.toml` 继续对模型 provider bearer token 脱敏。SearchAgent 片段属于镜像静态内容，构建契约禁止包含运行时凭证，因此可以原样进入调试产物，便于确认实际启用的 MCP server、命令和参数。

### 兼容行为

- v4 镜像：存在合法片段，评测配置包含模型 provider 和 SearchAgent MCP 两部分。
- v1-v3 镜像：片段不存在，生成内容与改造前一致。
- 自定义镜像：片段不存在时兼容旧行为；若主动提供该固定路径，则必须满足同一严格契约。
- v4 片段损坏：不静默降级为无搜索工具，当前评测在模型启动前失败，以免生成表面成功但缺少 Search/Fetch 的结果。

## 构建与默认值切换

更新 `script/build-astroncode-image.sh`：

- 默认 `ASTRONCODE_DOCKER_VARIANT=v4`。
- 默认 `IMAGE_TAG=v0.4`。
- variant 白名单扩展为 `v1|v2|v3|v4`。
- 新增可选环境变量 `SEARCH_UPDATER_VERSION`，非空时传递为 Docker build arg。
- 注释和使用示例说明 v4 是默认构建，并保留 v1-v3 显式覆盖方式。

更新运行和文档默认值：

- `AstronCodeAgent` 默认镜像改为 `wildclawbench-astroncode-ubuntu:v0.4`。
- `.env.example` 的 `DOCKER_IMAGE_ASTRONCODE` 改为 v0.4。
- Linux 评测命令速查和 macOS 本地调试指南中的 AstronCode 镜像统一改为 v0.4。
- 文档说明 v0.4 内置 Search、Fetch 和 SearchBetter Skill；现有评测命令无需增加 SearchAgent 开关。

文档只切换 AstronCode Harness 相关命令，不修改其他 Harness 的镜像或评测参数。

## 错误处理与安全边界

- AstronCode、SearchAgent 安装或 `doctor --full` 任一步失败，Docker build 失败，不产出 v0.4 镜像和离线包。
- Runner 读取片段时区分“文件不存在”和“读取失败”。只有文件不存在可兼容跳过，权限错误、Docker exec 异常和格式错误都应失败。
- 配置错误只报告固定路径、失败阶段和结构原因，不记录完整片段，避免未来片段内容变化时泄漏敏感信息。
- v4 Dockerfile 不设置 `ASTRON_API_KEY`、`OPENROUTER_API_KEY`、`ONE_IFLYTEK_API_KEY` 等凭证环境变量。
- 模型服务凭证仍只在任务容器运行时注入，宿主机调试配置继续使用 `***`。
- npm registry 地址作为构建参数记录，但不在 Dockerfile 或脚本中持久化 registry 认证信息。

## 测试与验收

### 静态镜像和构建脚本测试

新增 `tests/test_astroncode_v4_image.py`，保留 `tests/test_astroncode_v3_image.py` 作为历史版本契约。测试至少覆盖：

- v4 Dockerfile 存在并直接基于 `wildclawbench-codex-ubuntu:v0.0`。
- AstronCode 默认版本为 0.0.13，Search updater 默认版本为 `latest`。
- AstronCode 安装和版本检查发生在 SearchAgent 安装前。
- `/root/.acode` 清理发生在 SearchAgent 安装前，之后不再删除该目录。
- Search updater 使用 `--foreground-scripts` 和指定 registry。
- 构建时执行 `install-search` 和 `install-search doctor --full`。
- 配置片段保存到固定路径，并在保存前检查只含非空 `mcp_servers`。
- Dockerfile 不写入凭证环境变量。
- 构建脚本默认 variant/tag 为 v4/v0.4，白名单包含 v4，并传递 `SEARCH_UPDATER_VERSION`。

### Runner 单元测试

扩展 `tests/test_astroncode_config.py`，至少覆盖：

- 默认镜像为 v0.4。
- 合法 MCP 片段同时进入容器实际配置和宿主机脱敏配置，完整结果可被 `tomllib` 解析。
- MCP 片段缺失时保持旧镜像配置内容。
- 文件存在但为空、TOML 语法错误、顶层包含非 `mcp_servers` 配置、`mcp_servers` 不是表或为空时失败。
- 片段读取权限或 Docker exec 异常时失败。
- 模型 bearer token 在合并后仍不出现在宿主机配置、命令参数、日志或异常信息中。

运行聚焦测试：

```bash
uv run python -m unittest \
  tests.test_astroncode_config \
  tests.test_astroncode_v3_image \
  tests.test_astroncode_v4_image -v
```

再运行项目完整单测，确认默认镜像切换没有影响其他 Harness：

```bash
uv run python -m unittest discover -s tests -p 'test_*.py'
```

### 真实镜像验收

默认构建并导出 v0.4：

```bash
bash script/build-astroncode-image.sh
```

构建后执行：

```bash
docker run --rm wildclawbench-astroncode-ubuntu:v0.4 astron-code --version
docker run --rm wildclawbench-astroncode-ubuntu:v0.4 install-search doctor --full
```

验收要求：

1. AstronCode 版本输出为 0.0.13。
2. SearchAgent doctor 的依赖、MCP handshake 和 Skill 检查全部通过。
3. `/opt/astroncode/search-agent.config.toml` 存在，顶层只包含非空 `mcp_servers`。
4. `/root/.acode/skills/search-better` 和 MCP 实现文件存在。
5. `Images/wildclawbench-astroncode-ubuntu_v0.4.tar.gz` 可由 `docker load` 加载。

条件允许时使用一个 `04_Search_Retrieval` 单用例执行 AstronCode 冒烟评测。除原有 score、usage、session、trace 和 workspace 产物外，还必须确认结果目录的脱敏 `config.toml` 包含预期 MCP server，执行日志中没有 MCP 初始化或工具不可用错误。真实模型或搜索服务不可达时应记录为环境阻塞，不能替代静态、单元测试和容器内 doctor 结果。

## 回退

运行时显式设置：

```bash
DOCKER_IMAGE_ASTRONCODE=wildclawbench-astroncode-ubuntu:v0.3
```

即可恢复到不包含 SearchAgent 的 v3 镜像。构建时可显式设置 `ASTRONCODE_DOCKER_VARIANT=v3 IMAGE_TAG=v0.3`。由于旧 Dockerfile 和片段缺失兼容路径均保留，回退不要求修改 Runner 代码。
