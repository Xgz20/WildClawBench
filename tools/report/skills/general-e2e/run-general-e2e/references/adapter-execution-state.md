# General E2E 通用执行状态接口（CB-A）

新 Harness 使用 `wildclawbench.general-e2e-execution-state/v1` 输出可恢复的执行状态，再由 `record-execution` 登记已经验证的终态。此接口支持开发执行器与登记执行结果；**正式 `collect-evidence` 仍依赖 CB-B 公共收口器与各 Harness 原生采集器**。本接口不生成 receipt，不证明已完成原生客户端 smoke、评分或生产验收。

## 1. 接入与兼容

运行期唯一 Schema 是本 Skill 内的 `vendor/e2e-shared/general-contracts/schemas/general-execution-state-v1.schema.json`，校验器是 同目录的 `execution_state.py`。两者从 canonical `eval_general_e2e/contracts/` 构建进入 `general-contracts@1.1.0`，运行时直接读取 Schema 并验证其所用关键字；未知关键字失败关闭。Skill 版本为 `run-general-e2e@0.4.0`。

旧 `wildclawbench.general-e2e-astronstudio-execution-state/v1` 保留既有字段检查，只能登记到 AstronStudio macOS 单元（`platform=macos` 或 `macos-*`）。新 Windows 实现使用通用 Schema，不伪装为旧 Mac Driver。

仓库布局检查 `inspect_shared_component_layout(repo_root, adapter="workbuddy")` 显式校验 `eval_general_e2e/adapters/workbuddy/components.json`；无参调用仍检查 AstronStudio，并保留原报告字段。新 binding 的 `adapter` 必须匹配选定 slug，入口固定为该目录 `components.mjs`，`components` 为 canonical catalog 的非空、准确版本子集。此 binding 只声明源码依赖，不自动调度 Driver 或放行客户端版本。发行代码必须使用本 Skill 的依赖，不能跨 Skill 或依赖仓库位置。

## 2. 字段与校验

| 字段 | 约束 |
|---|---|
| `driver` | `id/version/harness/platform` 必填；Harness 与 platform 精确匹配冻结的单元 manifest，版本为 SemVer |
| `identity/dataset` | `batch_id/unit_id/task_id/attempt_id` 和 dataset `id/digest` 必填；任务必须属于单元 |
| `task_root/candidate_workspace` | 本机绝对路径；必须与 manifest 中该题路径一致，候选必须在该任务目录内 |
| `prompt` | 实际 prompt 文件路径、SHA、`send_status/sent_at` 必填；文件 SHA 与 manifest `sent_sha256` 一致 |
| `send` | `dispatch_attempt_count` 是 0 或 1 的整数，不接受布尔值 |
| `session` | `thread_id/turn_id/session_id/cwd/verified/binding_evidence` 必填；原生不存在的 ID 显式写 `null`，不得编造 |
| `execution` | 业务终态、开始/结束时间、时长、错误及 `cancellation_confirmed`；未知值显式 `null`，时间包含时区 |
| `human_assistance` | 自动或人机协作、操作次数和语义干预次数 |
| `extensions` | 可选对象，用于 Driver 私有恢复状态；不得覆盖公共字段语义 |

`binding_evidence` 是单元根目录内的非空原生会话绑定证据列表，每项有相对 `path`、`sha256`、`size`。Driver 负责保留原生来源及其如何证明“本次 prompt、原生会话、当前 Workspace”属于同一任务的依据；公共入口检查证据文件存在、非空、无符号链接/越界、无重复且哈希与大小一致，**不会把任意文件内容自动解释为真实原生绑定**。`verified=true` 还要求至少一个真实 native ID、`cwd` 与候选 Workspace 一致及非空证据列表。缺少原生 ID 时保持未验证，不构造 AstronStudio 的 thread/turn 层级。

未发送终态只允许 `not_sent + dispatch=0 + sent_at=null + infrastructure_error`。已发送的正常或失败终态必须 `sent + dispatch=1`，有发送时间、经验证的原生会话及 Workspace 绑定。`intent_persisted/uncertain` 不可登记为终态：必须保留 `NEEDS_ATTENTION`，核对原会话后恢复，不能改写成 `FAILED` 绕过检查或重发。

`COMPLETED` 只对应业务 `completed`，其它已确认业务终态使用 `FAILED`。`timeout/cancelled` 要求 `cancellation_confirmed=true`；无法确认客户端停止时继续待核对，不冻结候选。`record-execution` 的阶段 `COMPLETED` 表示已收齐执行终态，实际任务的 `business_status` 仍独立保留，失败任务不变成成功。

## 3. 使用与后续边界

```bash
python scripts/run_general_e2e.py record-execution \
  --root /absolute/unit-root \
  --state /absolute/unit-root/.general-e2e/execution/task-one/automation-state.json
```

单次登记要求状态文件覆盖该单元 manifest 的完整任务顺序。文件和证据须位于单元内；读取时锁定 state 字节的 SHA/大小，记录前校验文件没有变化，产物索引使用这份已验证快照。登记完成只推进 execute，collect-evidence 保持原状态。

CB-B 负责公共 finalizer、原生 trace 多文件来源、平台进程清理 hook，以及与现有 trace-index/执行回执的适配。CB-A 不改变 trace-index、resource-metrics 或任何旧原生采集器的 wire 语义。新增五项指标仍由 COMMON 统一维护；平台采集原始证据，不私自在现有严格 Schema 添加字段。

构建新 Skill/发行包时记录新的 `source_revision`、`content_sha256` 和各组件版本/哈希；不能复用旧生产包身份，旧 smoke 证据也不自动覆盖新增 Harness。
