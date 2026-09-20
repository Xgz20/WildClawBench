# MAC-WORKBUDDY-GENERAL：WorkBuddy macOS General

| 字段 | 当前值 |
| --- | --- |
| 唯一负责人 / 实际任务 ID | 独立开发任务 / `01a0b8d2-0ea9-7012-ac4f-c2bd69dc8b7b`；由 COMMON 控制任务派发 |
| 工作状态 / 代码交付 | ACTIVE / INTEGRATED；P1/P2 离线入口与真实输入修复、CB-B collector/trace-index v2、cleanup/readiness gate 已合入；SLOT05 发送前清空门禁失败关闭，未创建新 attempt，用户草稿保持完整 |
| 计划分支 / worktree | `feat/workbuddy-macos-general-e2e` / `<主项目>/.agents/workbuddy-macos-general-e2e`；绑定已核验 |
| 创建 base / 已采用公共基线 | `03c38f280a64ad9bc9308c768f0f5795050355cc` / COMMON-002 推荐源码 `eb23784a7ed25b0f0364db0392783de277b22b96` |
| 已读台账的 SYNC_SHA / 实际工作 HEAD | COMMON-004 覆盖数校正已采用 `ddba8d645da18af75d04fad4a7a47ec1aaa1c161`；当前工作 HEAD `73d75565b37fb88626f4239411bd0e7cf95b4687` |
| 同步源 / 实现与集成 SHA | `github/feature/astroncode-eval`（COMMON-004 已核验）；P2 `e388dfa43c0f38263ebcf57bf022ba1eb2c3cfeb`；COMMON merge `4529352ca92bf213995fd00433c6d77af3f8fc32`；组件绑定 `b3ac3da374165d74a41a3198e13d05928d671552`；输入修复 `5bea7621e4c90222d3f2e0000ab1ca6093af6e0b`；CB-B 源提交 `519b908`；COMMON-003/004 merge `0eddf84e34f2cd8f738f819eebdd963acda3ae77` / `4be1e02c79cbbd15f7510d1d876f48e5429aeda3`；集成 `be3ca29`；未 push |
| 最后更新 | 2026-09-20（Asia/Shanghai），cleanup/readiness gate 已接收，完成 SLOT05 发行冻结、只读门禁和草稿清空失败安全收尾 |

## 本轮范围与修改归属

实现 WorkBuddy 的 General Driver、轨迹/资源适配、正式 collect、评分交接和声明范围的并发/恢复。客户端专属文件和 fixtures 由本任务负责；公共注册、Schema、聚合与打包机制交给 COMMON 协调。现有 Web 的 WorkBuddy batch 可能被 QwenWork 复用，不能当作独占文件。

技术细项与证据入口：[General 验收清单](../../../general-e2e/通用场景端到端自动化评测实现计划与验收清单.md)中本 Harness 独立记录，映射 C/G、CV/GV；不得覆盖 AstronStudio 的 MAC 行。

工具 completed 与业务 success 分开，积分需核对请求范围/去重/实际结算；历史 Web 样本不能替代当前 General 真机证据。

## 依赖与完成清单

硬依赖：[COMMON](COMMON.md) 的 COMMON-CB04 已发布，且本任务的 adapter/状态/指标接口约定可取得。**不依赖 COMMON-CM01 的全部新增指标实现。** 基线未发布时可继续只读环境盘点、已有日志/fixture 分析和差异清单；不自创公共字段或依赖未合入 worktree。

- [x] P1：本机只读 probe、原生身份与字段/能力映射。实现 `2112a86450ba2f22fb284d37a20921cd7e65db69`；证据：[workbuddy-macos-readonly-20260919](../../../general-e2e/evidence/workbuddy-macos-readonly-20260919/README.md)。
- [ ] P2：单题一次发送、可信终态、恢复和正式证据收口。离线入口与 `Input.insertText + pre-arm enabled` 修复已完成，WorkBuddy 25/25；旧 SLOT03 只消耗 reservation，SLOT05 在临时移出前失败，所有新 attempt/click/send/native session 均为 0，尚不能勾选。
- [ ] P3：原始轨迹/资源对账与完整单题评分/回传/报告。
- [ ] P4：按场景验收三题串行、五题动态补位及声明并发。
- [ ] P5：受影响故障加固、候选不可变与仓库外发行。
- [x] P6：代码/证据/交接集成，必需接收动作完成；集成提交为 `be3ca29`。

勾选附实现/集成 SHA 与验收证据；此卡不复制技术验收 PASS 表。

## 下一项与阻塞

下一项：控制任务标记 SLOT05_RELEASED 后，不再重试本轮清空；采用 COMMON-004 后续 0.8.1 发行身份，CB-B collector 与 cleanup/readiness gate 已审查并合入，下一阶段是受控真机 collect/cleanup 验收。未来真机须另行明确授予 slot，并先解决安全临时移出/恢复路径，再创建全新 attempt。

当前依赖缺口：COMMON-004 已采用；WorkBuddy 专属 collector、trace-index v2 和 cleanup/readiness gate 已离线合入，仍待真实 WorkBuddy 子进程验证、正式 collect 和评分闭环。专属 driver 继续只放行已核验的 `5.5.3 + Electron`，是否公共化由 COMMON 决定。旧 attempt `3e554524-6599-4182-aecc-3257977867c0` 永不重发或重置；SLOT05 未创建新 attempt，清空门禁失败后草稿仍与备份一致。控制任务释放前不得再访问桌面。

## 本机现场与恢复

本地证据根：`/Users/gzx/debug-workspace/e2e-evaluate/workbuddy-macos-general-e2e/`。prestart 时 WorkBuddy 主进程 0、原生 session 仅有历史 Completed；随后启动并核验 5.5.3/x86_64、loopback CDP 精确归属和唯一 WorkBuddy page target。运行时回读为 `xopglm52/default-sandbox`；单题 prepare/batch verify 已通过。释放桌面时应用仍运行且 CDP 存在，但该状态可能漂移，后续不得沿用而不重探。

旧 canary attempt 的 journal 为 `NEEDS_ATTENTION`：旧实现把 Prompt 直接写入 DOM 后发送按钮仍 disabled，reservation 为 1，但实际 click/send/native session 为 0；conversation/request/cwd 均未绑定。同 attempt `--resume --observe-once` 没有重发。SLOT05 没有 journal/attempt：只读 probe 通过，临时清空失败后立即停止，当前草稿仍与私有 0700/0600 备份一致。私有正文和截图不入 Git、候选或评分包。

## 接收记录

| 交接 ID | 状态 | 已采用集成 SHA | 处理结果、验收证据/阻塞 | 下一项 |
| --- | --- | --- | --- | --- |
| COMMON-001 | VERIFIED | `0dd42824cb8eb510ab126fd74553f93312c9f201`（推荐源码 `ed366b30...963a`） | 无活动 WorkBuddy 进程后 merge；已按 CB-A 输出真实 conversation/request/cwd 映射，thread 为 null；公共 55/55、新增 Node 9/9 与语法检查通过 | P2 真机时段；CB-B 接口交接 |
| COMMON-002 | VERIFIED | `4529352ca92bf213995fd00433c6d77af3f8fc32`（SYNC `46a23a...08af`，推荐源码 `eb23784...2b96`） | WorkBuddy 精确绑定已更新到 discovery/contracts 1.2.0；shared/layout/contracts/build/collection Python 46/46、WorkBuddy/finalizer/discovery Node 38/38 通过 | 实现专属 trace v2 collector 与 cleanup hook；继续 canary |
| COMMON-003 | VERIFIED | `0eddf84e34f2cd8f738f819eebdd963acda3ae77`（SYNC `82e947b926a4525aac7ba2de08b76830ee9c739b`，推荐源码 `dc5ff64...13c3`） | 远端 SHA、推荐源码祖先关系核验；General Python 63/63、组合 Node 130/130、Web Python 61/61；WorkBuddy 采用 5bea762 离线修复，旧 SLOT03 reservation=1/click=0/send=0，草稿已恢复 | 新交接输入修复与受控 SLOT05 canary |
| COMMON-004 | ADOPTED | `73d75565b37fb88626f4239411bd0e7cf95b4687`（SYNC `ddba8d645da18af75d04fad4a7a47ec1aaa1c161`，推荐源码 `2023b4d...ca4`） | execute 0.8.1 与 WorkBuddy 输入修复已进入当前工作树；按要求先冻结 0.8.0 release 做 SLOT05 发送前门禁，因无法安全清空旧草稿停止，未创建新 attempt；公共组合覆盖数校正已核验 | 后续发行采用 0.8.1；不重试本轮清空 |
| MAC-WORKBUDDY-GENERAL-006 | ADOPTED | `0fbdd57`、集成 `eec4a2e` | cleanup/readiness gate 增加 request turn、conversation session、native cwd、terminal status 的显式原生来源校验；缺失或由 candidate workspace 推导时失败关闭；来源反例 7/7 | 新时段执行一次全新 General attempt，完成真实 collect、cleanup quiet window、正式回执与评分交接 |
| MAC-WORKBUDDY-GENERAL-004 | ADOPTED | `be3ca29`（源提交 `519b908`） | CB-B collector/trace-index v2 输出 transcript、多个 raw history/binding artifacts，并保留 null+known subtotal+coverage 资源语义；Node 26/26 通过；未操作客户端 | 真实 collect、cleanup hook 与原生终态核验 |
| MAC-WORKBUDDY-GENERAL-005 | ADOPTED | `3783b2b`（源提交 `a05b793`） | cleanup/readiness gate 校验 batch/unit/task/attempt、trace v2、资源 null/coverage、cleanup workspace/quiet window/残留进程；Node 33/33；未操作客户端 | 受控真机 collect、cleanup 与原生终态核验 |

## 本轮交付

### CB-B 离线 collector 与 cleanup/readiness gate（已合入 COMMON）

`eval_general_e2e/adapters/workbuddy/native-history.mjs` 新增 `collectWorkBuddyGeneralEvidence()` 和 `buildWorkBuddyTraceIndex()`；`cleanup.mjs` 以公共 macOS task-process primitive 校验 identity、trace/resource readiness、cleanup quiet-window/残留进程，并在 `0fbdd57` 增加原生 request/session/cwd/terminal 来源门禁。未知 `thread_id`、lifecycle、transport retry、terminal cleanup 和未验证积分不会被推断或补写。离线 fixture 已通过 trace/resource/cleanup 契约校验；该交付不等于真机正式 collect 或评分准入。

P1 `2112a86450ba2f22fb284d37a20921cd7e65db69` 提供只读 probe/adapter；P2 `e388dfa43c0f38263ebcf57bf022ba1eb2c3cfeb` 提供安全可恢复单题入口；`5bea762` 改用 CDP `Input.insertText` 并将精确回读、唯一 enabled 发送控件前移到 armed 之前。COMMON-004/execute 0.8.1 已采用到当前工作树；冻结的 0.8.0 release prepare/batch verify PASS，但 SLOT05 临时移出失败，未创建新 attempt。WorkBuddy 25/25、General Node 93/93、相关 Python 60/60、组合基线 254/254、专属依赖闭包、语法和 diff 检查通过。证据见 [P1 只读](../../../general-e2e/evidence/workbuddy-macos-readonly-20260919/README.md)和 [P2/canary 收口](../../../general-e2e/evidence/workbuddy-macos-p2-offline-20260919/README.md)；前序交接为 [MAC-WORKBUDDY-GENERAL-002](../handoffs/MAC-WORKBUDDY-GENERAL-002.md)，本轮 SLOT05 阻断交接为 [MAC-WORKBUDDY-GENERAL-003](../handoffs/MAC-WORKBUDDY-GENERAL-003.md)，新失败原件留在 debug 根。真实 canary 没有实际发送、模型执行、原生 session、collect、评分或发行结论；用户现场未被改变。未 push。
