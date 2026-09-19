# AstronStudio macOS 只读探针契约

## 适用范围

`scripts/probe_astronstudio_macos.mjs` 只用于 G2-01 运行环境预检与配置冻结，不执行用例。输出遵循：

- [探针结果 schema](astronstudio-probe-v1.schema.json)
- [冻结运行配置 schema](astronstudio-run-config-v1.schema.json)

当前 Skill 为 `operational`，但探针仍只是执行前的只读门禁。探针 `PASS` 只证明本次记录的 macOS、AstronStudio、CDP、状态库、模型/推理/权限和依赖组合满足启动执行的条件；它本身不证明后续 Prompt 发送、终态识别、轨迹采集、评分或报告已经成功。

## 只读边界

探针允许：

- 通过共享发现组件按显式路径、运行进程、Spotlight Bundle ID 和标准目录解析应用包，并读取版本、Bundle ID、进程身份、监听端口和 GUI 锁定状态；
- 读取当前 Skill、source revision（发行包中可用）和 vendored 组件版本/哈希；
- 对本机 loopback CDP 执行 `/json/version`、`/json/list` GET；
- 通过 `Runtime.evaluate` 查询可见模型/推理按钮和权限按钮的文本；
- 复制 `state.sqlite`、`-wal`、`-shm` 到临时目录，在快照上执行 `quick_check` 和白名单查询；
- 读取 Node、Python、SQLite、Docker 和 Codex 版本；
- 在用户指定的新路径写探针结果和通过后的冻结配置。

探针不得启动、退出或重启 AStudio，不得点击或填写 UI，不得打开模型/权限菜单，不得选择工作空间，不得读取 composer 内容，不得发送 Prompt，也不得直接打开源状态库进行写操作。

进程身份通过 `ps` 的完整可执行路径和父子关系选择唯一根 PID；锁屏状态只读取 `ioreg.IOConsoleLocked`。探针不调用 `System Events` 或目标 App Apple Events，也不需要 macOS Automation 授权。`ioreg` 无法给出锁屏状态时失败关闭，不用前台应用名称猜测。

## 失败关闭

以下任一条件使结果为 `NEEDS_ATTENTION`，且 `frozen_run_config=null`：

- 平台不是 macOS，应用包、Bundle ID、版本或主进程身份不能精确核对；
- 图形会话锁定或状态未知；
- CDP 不可连接、端口不属于已核对主进程，或找不到 AStudio page target；
- `DevToolsActivePort` 早于当前主进程时，只记为陈旧证据，不能据此声明 CDP 可用；
- 状态库快照 `quick_check` 失败或缺少必需投影表；
- 当前模型、推理强度或权限不能通过 CDP 可见控件回读；
- Node 或状态库读取后端不可用。

状态库中的最近线程模型只记录为 `latest_persisted_model`，其 `current_ui_verified=false`。它用于解释现场和后续对账，不参与 PASS 判定，也不能写入冻结运行配置。

## 输出和退出码

- `0`：`PASS`，可写冻结运行配置。
- `3`：`NEEDS_ATTENTION`，环境或可见配置尚未满足冻结条件。
- `2`：参数、输出文件冲突或探针自身错误。

`--output` 和 `--config-output` 使用创建新文件语义，拒绝覆盖已有证据。新冻结配置的执行并发默认值为 3、上限为 8，UI Prompt 发送仍固定单槽；旧的并发 1 冻结配置继续可用。G4-03 已完成旧版本五题三槽真机闭环；共享应用发现和无 Apple Events 路径属于后续新版本，仍需分别补 macOS/Windows 真机 smoke，不能沿用旧证据直接宣称通过。

`config_digest` 使用 `sha256-canonical-json/v1`：递归按对象键排序、数组保持原顺序，以紧凑 JSON 编码后计算 SHA-256；计算前移除 `config_digest_algorithm` 和 `config_digest` 两个 digest 元数据字段。读取方必须同时校验 schema 对算法字段的固定值和重算结果。
