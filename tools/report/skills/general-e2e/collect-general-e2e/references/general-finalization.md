# General 通用正式收口接口（CB-B 第一批）

`collect-general-e2e`、`general-contracts@1.2.0` 提供通用采集验证与冻结接口。除脱敏 fixture、AstronStudio 回归和仓库外 Skill 执行外，WorkBuddy 与 QwenWorkCN 1.0.6 已各有明确范围的 macOS 真机收口证据；这些证据只证明对应批次、版本元数据和运行方式，不能自动外推到其他平台、并发层级或新客户端行为。

## 输入与 wire 版本

- 状态使用 CB-A `wildclawbench.general-e2e-execution-state/v1`。
- 新轨迹索引使用独立 `urn:wildclawbench:schema:general-e2e:trace-index:v2`、`schema_version=2`。v1 不放宽；旧 AstronStudio 归档器、资源采集器及 finalizer wrapper 继续只接受原 v1 链路。
- resource-metrics、execution-record、receipt 仍是 v1；缺失指标继续 null/coverage，不把未验证数据变成零。

新 trace index 必须具备 adapter、identity、session、transcript、raw_trace、binding_evidence、completeness、calls。原生不存在的 thread_id、turn_id、lifecycle_generation 显式为 null；至少一个真实原生 ID 非空。session 的 thread/turn/session/cwd 与 state 严格一致，cwd 必须匹配候选 Workspace。

`transcript.path` 固定 `transcript.jsonl`；多个原始文件放在唯一的 `raw/...` 路径，会话绑定证据放在唯一的 `bindings/...` 路径。每个 artifact 保存 SHA-256 与大小，不接受空原始文件、符号链接、重复、绝对路径或越界路径。`binding_evidence` 的 SHA/大小集合必须与 `state.session.binding_evidence` 完全对应；平台复制真实绑定证据，不为通过校验编造 ID。

规范化 transcript 仍使用 transcript-event v1。每个事件的 identity/adapter 与索引一致，sequence 从 0 连续递增；raw_ref 必须指向本索引中已验证的 raw 或 binding artifact，`#L<n>` 必须落在实际文件行数内。工具 call/result 索引须指向正确的事件类型和同一 call_id。平台原有私有 observation 必须先构造这些正式输出，不能仅替换 schema 名称。

## 来源与冻结

resource collection.sources 的可信集合由已验证输入构造：`execution/automation-state.json`、`trace/trace-index.json`、`trace/raw/...`、`trace/bindings/...`。前两项必需；原始文件可以按该资源采集实际使用的子集引用。未知、重复或哈希不符的来源拒绝；metric_sources 若存在，每个引用必须属于 collection.sources。

Python `collection_validation.py` 直接使用 CB-A 和各标准契约的 validator，检查状态、manifest、prompt、原生绑定、所有原始文件、transcript 和 resource。它返回同一轮校验的输入哈希；Node 核心在清理进程前核对内存里的已读取字节与这些哈希一致，随后归档这些已验证字节，并在候选复制完成、正式发布前再次检查全部输入锁。prompt 的锁定字节再与 state/manifest 双 SHA 对账；transcript 直接校验已锁定字节，路径先检查原始相对路径的每级祖先再解析。读取或清理、冻结期间发生变化会拒绝，不把第三次未验证读取登记成可信证据。

可选最终回复沿用 `state.extensions.evidence.final_response_path/final_response_sha256`；客户端观测可放 `state.extensions.client.version/model/reasoning`。前者必须是单元内、哈希验证的文件；后者的未知值不反推。

## 平台 API

平台 collector 在本 Skill 内调用：

```javascript
import { finalizeGeneralExecution } from "./finalize_general_execution.mjs";

const result = await finalizeGeneralExecution({
  unitRoot, stateFile, traceIndex, resourceMetrics,
  pythonExecutable, // 本机可用 Python 的明确路径；不依赖仓库虚拟环境
  stabilityMilliseconds: 5000,
  processQuietMilliseconds: 5000,
  processWaitMilliseconds: 15000,
}, {
  processCleanup: {
    id: "已实现的清理器标识", version: "0.1.0", harness, platform: "darwin",
    run: terminateTaskProcesses,
  },
});
```

`processCleanup.run(workspace, options)` 是受信任的平台实现，不是用户输入的“成功结果”。没有默认实现，不允许通过 `success=true` 占位。hook 的 Harness/platform 必须匹配 state；平台为 darwin 或 win32。返回 task-process-cleanup/v1：supported/success、正确平台、before/after 支持状态与精确 Workspace、targets/seed_pids/root_pids 数组、termination_attempts、late_process_detected 和 quiet window/observed milliseconds。after.targets 必须为空；quiet 需求必须大于零、观察时长达到需求且不能超过本次 hook 实际单调时钟耗时。unsupported、未实现、清理失败、残留或证据不完整都在冻结前阻断。

现有 `lib/macos-task-processes.mjs` 提供真实 macOS cwd/命令/子进程选择与清理原语；各 Harness 必须验证它覆盖本客户端实际任务进程后再接入。Windows hook 尚需 Windows 任务实现验证。fixture 的假进程快照仅用于测试，不是可发布的平台实现。

CLI 仅暴露帮助与 `--verify-only --unit-root ... --task-id ...`；正式收口由已接入真实 hook 的平台入口调用。不能通过 CLI 自动选择未知清理器。所有 Harness 共用 `lib/general-finalizer.mjs`；旧 `finalize_astronstudio_execution.mjs` 是兼容薄 wrapper，禁止各平台复制核心后各自修改。

## 可消费边界

通用 finalizer、公共 contract validator、`query_trace.mjs` 已明确接受 v2；旧 AstronStudio native archive/resource collector 保持 v1 专用，不接受 v2 输入。评分/编排入口消费冻结的 execution-record/receipt v1，其 wire 不变；公共 contracts 已注册 trace v2，而不是跳过未知 schema。完整新 Harness 评分闭环仍需目标平台验收。

本次同时消费 `desktop-app-discovery@1.2.0`。为避免同一版本对应不同内容哈希，受组件影响的 General Skill 版本为 execute 0.7.0、collect 0.5.0、run 0.5.0、orchestrate 0.9.0、report 0.2.2；版本变化不等于新增平台通过验收。平台更新精确组件 binding 后必须重建 Skill/发行包，保留新的 source_revision/content SHA；旧生产包与 smoke 证据不自动涵盖这些修改。
