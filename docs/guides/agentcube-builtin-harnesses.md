# AgentCube 内置产品适配

执行产品与内置模型候选来自 WindowsAgentArena 控制层。更新默认候选后可用 `tools/e2e-build/publish_controller_capabilities.py --controller-root /path/to/WindowsAgentArena --output /new/path/capabilities.json --template <template>` 发布新的只含非敏感元数据的能力文件，再配置 `WCB_E2E_CAPABILITIES_FILE`；输出文件已存在时拒绝覆盖。

默认发布 AStudio、WorkBuddy 和 ChatGPT 的 AgentCube 能力。AStudio 模型候选来自默认模型 JSON，WorkBuddy 来自默认内置模型集合，ChatGPT 使用版本化的独立模板快照，记录源提交及摘要。AStudio 和 WorkBuddy 也允许透传其他产品内置模型标识并在实际菜单与原生轨迹中验证。ChatGPT 按快照列出的模型校验。目录中的候选需要与实际部署模板和账号权限核对。

WorkBuddy 单元使用 `max_mode: true|false`，与 AStudio `reasoning_effort: none|high|max` 分开；框架先检查已部署控制层的请求字段，再下发开关。WorkBuddy 复用模板登录，AStudio 的运行时与登录注入只作用于 AStudio 驱动。

WorkBuddy 原件保留未裁剪项目 JSONL、控制层报告、诊断、终态 Workspace 和进程收口证明。新规范化器核对唯一原生会话/请求、Workspace、Prompt、原生模型、Max 配置、原生终态、调用配对，并基于 provider 原始 usage 对账；不可核验的用量不补零。评分材料复用标准 General Skill，通过独立归档重放验证。多个无法关联的新增原生会话保留原件并拒绝猜测或拼接。

`environment-status` 是公开 v1 只读命令。`--probe` 仅探测 DNS 与已发布健康端点，不创建沙箱、不调用模型；凭据配置通过不等于鉴权有效。AgentCube 当前的公开工作负载 API 没有模板内模型列表或实时配额接口，因此能力来源与实际部署、配置上限与云配额分别标记。

历史发行和既有批次不原地升级。先测试新发行，再将新建批次默认执行器指向新的不可变 checkout；旧批次与旧评分记录沿用原读取器。

## 能力文件的加载方式

`WCB_E2E_CAPABILITIES_FILE` 可指定部署侧能力文件的绝对路径。文件使用 JSON，顶层包含
`schema: "wildclawbench.e2e-capabilities/v1"` 和 `profiles` 数组。

当前 `src/e2e/protocol.py::profiles()` 的行为如下。

| 环境变量 | 执行器读取来源 |
|---|---|
| 未设置或空字符串 | `default_profiles()` 读取 `src/e2e/builtin_models.json` 和 `src/e2e/builtin_chatgpt_desktop.json`，发布三个客户端 |
| 指向 JSON 文件 | 使用文件中的整个 `profiles` 数组 |
| 指定的文件不存在或解析失败 | 返回错误 |

外部 `profiles` 是完整集合。文件只包含 ChatGPT 时，本次执行器发布的候选也只有
ChatGPT。profile 内的 `models` 数组同样按文件原样读取。该加载逻辑没有按 Harness、
profile ID 或模型 ID 合并默认项的步骤。修改该环境变量只选择执行器能力元数据的来源，
平台数据库中的模型服务连接、沙箱模板记录和服务器凭据由各自配置维护。

ChatGPT 的执行驱动及桌面评分流程已实现。默认 ChatGPT profile 保存在
`src/e2e/builtin_chatgpt_desktop.json`，独立绑定
`winarena-pc-20261122-193046-chatgpt-pro-37fa332a-v5`、控制器
`37fa332a3a2c360406e7b830c5b0036582346ed7`、客户端 `26.1117.4957.0`。
该快照发布 10 个模型、`low/high` 推理档、`general/web` 执行与评分、
`full access` 权限及 Pro 订阅评分。新建 ChatGPT 计划省略模板时采用该独立模板，
默认权限为 `full access`。显式保存的模板和权限继续使用输入值。

外部能力文件继续使用全量替换语义。部署新的默认能力后，留空
`WCB_E2E_CAPABILITIES_FILE` 即可发布三个客户端。若配置了旧的外部文件，则仍由
该文件决定可见客户端。发布其他 ChatGPT 模板的能力时，使用
`chatgpt_desktop_profile()` 和发布工具的 `--chatgpt-desktop-template` 参数。
工具携带该参数时输出包含三个客户端的完整文件，省略时输出 AStudio、WorkBuddy。

## 完整配置示例

参考 [e2e-capabilities.example.json](../examples/e2e-capabilities.example.json)。示例包含
AStudio 的 11 个模型、WorkBuddy 的 20 个模型和 ChatGPT 的 10 个模型。

| profile 字段 | 用途 |
|---|---|
| `id` | profile 标识，批次模板绑定和执行预检使用该标识 |
| `harness` | 客户端标识，分别为 `astronstudio`、`workbuddy`、`chatgpt-desktop` |
| `backend` | 沙箱后端，当前示例为 `agentcube` |
| `template` / `template_namespace` | 已注册的沙箱模板及其命名空间 |
| `models` | 模型候选，每项包含 `id`、`display_name`、`kind`，可单独指定 `reasoning_efforts` |
| `reasoning_efforts` | profile 允许的推理档位，模型没有单独配置时沿用该数组 |
| `scenarios` | 允许执行的场景，`general`、`web` |
| `desktop_scoring_scenarios` | ChatGPT 允许评分的场景，缺失时使用 `general` |
| `default_permission` | ChatGPT 评分要求 `full access` |
| `chatgpt_scoring_auth` | ChatGPT 评分鉴权方式，`subscription` 或 `gateway`，缺失时使用 `gateway` |
| `controller_revision` | 模板对应的 WindowsAgentArena 源码修订，ChatGPT 评分会与平台模板绑定核对 |
| `enabled` | 是否发布该 profile，执行器还会检查对应驱动是否已注册 |

示例的 AStudio、WorkBuddy 部分来自框架当前默认快照。ChatGPT 部分由模板台账
`winarena-pc-20261122-193046-chatgpt-pro-37fa332a-v5` 对应的 WindowsAgentArena
`37fa332a3a2c360406e7b830c5b0036582346ed7` 的客户端驱动生成，并明确发布
`subscription` 评分及 `general`、`web` 场景。该台账记录了 Pro 订阅模板的 Web 评分与截图验收。
复制示例用于其他模板时，按该模板实际控制器修订、模型菜单、评分验收和登录方式更新这些字段。

ChatGPT 执行使用网关地址和 `WCB_CHATGPT_API_KEY`。`chatgpt_scoring_auth=subscription`
选择桌面评分的 Pro 订阅方式，执行认证配置继续由执行驱动读取。

部署后端 `.env` 中指定发布文件。

```dotenv
WCB_E2E_CAPABILITIES_FILE=/etc/wcb/e2e-capabilities.json
```

由 CICD 将该文件以相同绝对路径挂载到后端容器。通过执行器只读 `describe` 命令验证
返回的 `profiles` 包含所需客户端。平台还会根据“镜像与模板”中启用的默认模板绑定
补充实际模板信息，ChatGPT 的评分默认模板需要与能力文件中的模板和修订一致。

修改或新增能力时可以使用现有发布工具，控制器路径应对应目标沙箱镜像的源码修订。

```bash
python3 tools/e2e-build/publish_controller_capabilities.py \
  --controller-root /absolute/path/to/matching-WindowsAgentArena \
  --template winarena-pc-20261118-a \
  --chatgpt-desktop-template winarena-pc-20261122-193046-chatgpt-pro-37fa332a-v5 \
  --chatgpt-desktop-template-namespace agentcube-windows \
  --chatgpt-desktop-scoring-auth subscription \
  --output /absolute/path/to/new-e2e-capabilities.json
```

发布工具会生成三个客户端的完整 `profiles`。当前工具不自动写入
`desktop_scoring_scenarios`，需要在所生成的 ChatGPT profile 中依据验收结果设置该字段。
ChatGPT 的 Web 评分要求 `scenarios` 和 `desktop_scoring_scenarios` 都包含 `web`。

客户端版本绑定、增量配置和管理员界面的后续方案见
[客户端能力配置与管理员可视化评估](../design/e2e-client-capability-management.md)。

## ChatGPT 桌面端试点

ChatGPT Desktop profile 绑定独立 AgentCube 模板。通过控制器能力发布工具的
`--chatgpt-desktop-template` 参数从该模板对应的控制器修订发布 Codex Local 的模型、推理档、场景和权限。旧控制器继续发布原来的单模型目录。批次预检使用当前模板的能力目录，原生轨迹必须回读到所选模型和推理档。

执行器的 AgentCube 配置通过 `chatgpt_gateway_url` 指定网关 HTTPS 基地址。评测服务进程
通过环境变量 `WCB_CHATGPT_API_KEY` 接收相应凭据。控制层只在一次性 Windows 运行副本中
准备客户端登录与网关设置。能力目录、模板、镜像和批次的请求只记录非敏感配置。

原生 rollout 用客户端来源、Windows 项目路径、Prompt、会话和轮次标识做绑定。原件随
标准执行备份封存。

AStudio 和 ChatGPT 桌面评分在「镜像与模板」中分别设置评分默认模板。自动评分和新建评分任务根据该模板列出内置模型及推理档，发起后冻结评分模型和模板。ChatGPT 在独立沙箱读取冻结评分 Skill，通用场景复用规则校验，Web 场景使用 Codex Desktop Browser 和 Skill 的截图接收器。ChatGPT 模板默认开放通用评分。验证该模板的 Browser 控制和截图回传后，可在 profile 的 `desktop_scoring_scenarios` 加入 `web`。浏览器或证据链失败时保留原生轨迹和错误，评分状态为评测异常。


发布 ChatGPT Pro 订阅评分能力时，在控制器能力发布工具中指定 `--chatgpt-desktop-template`、`--chatgpt-desktop-template-namespace` 以及 `--chatgpt-desktop-scoring-auth subscription`。生成的 profile 会用模板名、命名空间和 `chatgpt_scoring_auth` 绑定该评分方式。平台冻结该鉴权方式后，执行器在 Windows 实例就绪后读取客户端当前账号的订阅类型，确认 Pro 才发题。订阅评分沿用实例已经授权的登录态，评分任务、镜像和模板描述均通过非敏感字段绑定身份。未指定该字段的 profile 沿用网关方式。该设置只用于桌面评分。
