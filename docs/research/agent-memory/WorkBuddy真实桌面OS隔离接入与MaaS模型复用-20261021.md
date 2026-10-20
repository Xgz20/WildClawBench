# WorkBuddy 真实桌面 OS 隔离接入与 MaaS 模型复用

2026-10-21 北京时间。全部源码修改与本地提交仍在 `.agents/memory-e2e` / `feat/memory-e2e`。
**真实桌面后端与原生工作进程的合成 OS 检查通过；本机记忆七步链仍0/7，评测 Prompt 为0，正式20题未启动。**

前序合成网关与旧失败见[原生执行网关验收](WorkBuddy原生执行网关与跨单元OS边界合成验收-20261021.md)。

## 实际接入

`workbuddy_scope.py` 创建独立 app-home/tmp/candidate，使用原生 `WORKBUDDY_CONFIG_DIR`、
`CODEBUDDY_CONFIG_DIR`、`WORKBUDDY_USER_DATA_DIR`。安装版5.8.3的 ASAR、CLI、原生二进制、
renderer源码及相关控制源码均冻结摘要；不是给旧 General 探针增加版本白名单。

`workbuddy-unit-launch.mjs` 监督签名 Electron 的真实桌面启动；通过临时 loopback Main Inspector
在应用入口安装 `workbuddy-seatbelt-spawn-guard.cjs`，保持原生五条 stdio/fd3/fd4 通道。
只把准确的后端/Center启动纳入附加文件策略，未修改安装文件、签名或 Chromium 原生沙箱开关。
后端以受支持的 `--require` 参数加载执行网关守卫。当前版本 Editor SDK 的 stderr pipe 与安装目录 cwd
已补齐，真实原生 PID、stderr 流、退出码与信号经绑定通道返回，无本地执行回退。

OS 边界的对象为后端直接文件 IO、Center 的委托 IO，以及经原生执行服务创建的数据工作进程。
UI Main 保留原有角色，未证明全部外部 OS broker 都被穷尽隔离；不能扩大为任意系统通道的绝对安全保证。

## OS 验收分母

证据根：
`/Users/LQ4T7293TX/debug-workspace/e2e-evaluate/memory-e2e/workbuddy-desktop-bootstrap-20261021-r1`。

- `zero-01`：真实后端读取本单元正控成功，保护目录及其符号链接均实际 EPERM；Main与后端的实际 PID、
  私有配置目录和账号指纹已绑定。安装版原生服务的6个工作进程中，读/写正控退出0，
  保护目录读、链接读、旧单元读和单元外写共4项均退出1 / Operation not permitted。
- `zero-02`、`zero-03`、`zero-07`：复用正确自定义模型配置后，在各自真实桌面后端再完成相同6项。
  这些是逐单元合成检查，不能拼成正式评测分母。
- `zero-03`：额外查询真实后端和Center的 OS 策略，保护文件读取以及本单元根目录 unlink 均被拒绝。
  对真实 Codex 父目录仅作 `sandbox_check` 策略字符串查询，没有打开真实记忆或配置。
- 前序证据根 `workbuddy-admission-20261021-r1/gateway-07` 验证 Editor SDK 启动形态；
  `gateway-08` 在安装版 Electron +原生服务上完成9项工作进程检查（2正控、7拒绝），
  以及后端5项直接 IO（1正控、4拒绝）。新增根目录重命名的实际拒绝。

单元根目录禁止 unlink，避免被替换后再生成策略；网关每条消息重新核对单元路径的 canonical identity。
原生 Center 只获得本纪元 socket 和两份精确协调锁的写入许可，这些许可不能进入数据工作进程策略。
原生 sandbox 模式和全部原生策略片段保留，只追加拒绝。

## 确认了 xopglm52 的真实来源

普通实例在退出前，界面模型为 `xopglm52`；原生数据库中的既有已完成会话记录
`model=custom-local:xopglm52`，权限为 `bypassPermissions`。

该模型来自普通 WorkBuddy 的 `models.json`，是 MaaS 自定义模型；其 endpoint origin 为
`https://maas-api.cn-huabei-1.xf-yun.com`。安装版 CLI 的自定义模型处理器会去掉 `custom-local:` 前缀，
将请求模型写为 `xopglm52`。内置 `GLM-5.2` 的目录ID是 `glm-5.2`，不能凭显示名将两条路由视为同一配置。
`zero-01` 曾选择内置条目，但发送前被保留为 MODEL_NOT_PINNED，没有产生任何评测请求。

后续只迁移 `xopglm52` 一条模型的10个已核验配置字段，以及与该模型有关的选择/思考选项：
`custom-local:xopglm52`、thinking=true、effort=high。未导入日常记忆、历史、插件、工作区或其他模型。
现有 provider credential 随模型配置保存在单元私有 `models.json`，不展示、不进入Git；
这与复用 WorkBuddy 当前登录账号是两件事。WorkBuddy登录文件没有被控制端复制，隔离界面的账号指纹与普通实例一致。

`zero-02`、`zero-03`、`zero-04` 已在真实UI回读 `xopglm52`，模型配置准备回执保留。
**尚无真实 LLM 请求的 requested-model/响应证据，也未验证 MaaS 本轮请求的额度和认证结果。**

诊断实例保留原生 `default-sandbox` 权限。普通实例原有 Full Access 没有被改动；
未为兼容性切换到更宽权限。当前诊断条件不能直接冒充普通 Full Access 条件的同构评测或正式比较。

## 启动观察失败与恢复

- `zero-02`：UI端口已监听但主页面尚未创建，首次发现返回0。保留失败；之后沿同一 Main PID
  只读确认页面/账号/目录，再完成此前尚未执行的模型配置准备，未重启或重发题目。
- `zero-03`：30秒模型元数据观察窗未取得就绪结果；后续同一实例中的读取成功。失败原因当时细分记录不足，
  不把观察超时当作进程结束。原失败与后续配置准备记录并存。
- `zero-04`：启动阶段出现 CDP 连接失败，仍沿同一实例确认存活并补齐未执行的准备。
- `zero-05/06`：保留启动期 context/RPC 未就绪与只读元数据超时，未产生模型配置成功回执或评测请求。
  单独等待 Main Inspector 关闭没有消除这一问题，不能把它写成已经定位到唯一根因。
- 新模型准备器先等唯一编辑器/模型/权限控件就绪，在**只读元数据阶段**关闭失效连接并重连同一受绑定实例；
  配置写入和页面刷新没有自动重放。已经准备过的单元只允许观察，避免刷新正在执行的上下文。
  `zero-07` 自动复验已通过：只读阶段先发生元数据超时，随后重连时目标ID由
  `546F8ACF3620005F17452F9ACF0C2A09` 变为 `30DA7C5B4001E653D88CFC62115FAAA1`，
  Main PID始终为21306。新连接取得当前账号与自定义模型后完成配置及UI回读，生成完整启动就绪回执。
  没有重启Main、重放配置写入或派发Prompt。其后6项真实原生进程检查也全部通过。

临时 Main Inspector 的恢复从“请求关闭”增强为“确认端口及连接均已关闭”的独立回执。
新增观测记录阶段、目标ID和标量状态，避免以后只能看到一个总超时。原 `desktop-bootstrap-failed.json`
不覆盖，不用后续成功重解释旧失败。启动监督器本身不发送 Prompt。

## 普通配置、数据和收尾

退出普通实例前，通过只读原生库元数据确认：1个会话已完成；自动化任务、运行状态和投递队列均为空。
读取限于状态/模型/权限等元数据，没有提取日常记忆或聊天正文。当前源码的 `checkMemoryUpdating`
固定回 false，未将它当作后台空闲证据。

普通模型文件摘要前后均为 `8884410df80809ad5371c544356e26a04d634a397f7187fe86108a5eec486fdc`。
普通实例为核对模型路由临时用9229启动过，检查后正常退出；配置值和日常记忆没有清空。
`zero-01`至`zero-06`均在原生状态为空闲/零评测请求时正常退出，相关监督器终态保留。
当前没有把“普通窗口重新打开”描述成已恢复；`zero-07` 的独立诊断实例保持运行，
后续继续绑定批次和Driver，仍未进入记忆题目执行阶段。

全部源码和提交只在指定worktree。未修改ACode原仓库，未执行待用户确认的完整 Rust 套件，
未操作Codex记忆配置或真实记忆，也未重发旧机接受未知的评测操作。

回归：Python **130/130**、Node **102/102**。原件包含 `backend-first-synthetic-proof.json`、
各单元 `admission-probe/result.json`、`model-selection-prepared/resumed.json`、
`zero-stage-preclose-audit.json`、`source-snapshot` 和主进程/监督器退出回执。

剩余工作是将本单元的 OS、账号、模型和路径证据绑定到 memory Native Profile /批次/Driver，
保留桌面UI发送与原生接受/完整轨迹收集门禁，再执行全新七步 canary、A1→B1→A2 实际记忆隔离。
**当前未验证模型层的跨用例/跨重复无污染，不能仅凭目录或配置成功宣告记忆评测准确。**
