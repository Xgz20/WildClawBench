# MAC-WORKBUDDY-GENERAL：WorkBuddy macOS General

| 字段 | 当前值 |
| --- | --- |
| 唯一负责人 / 实际任务 ID | 独立开发任务 / `01a0b8d2-0ea9-7012-ac4f-c2bd69dc8b7b`；由 COMMON 控制任务派发 |
| 工作状态 / 代码交付 | ACTIVE / LOCAL_ONLY；P1/P2 离线入口与真实输入修复已提交；真实 canary 在实际发送前失败关闭，用户草稿已完整恢复 |
| 计划分支 / worktree | `feat/workbuddy-macos-general-e2e` / `<主项目>/.agents/workbuddy-macos-general-e2e`；绑定已核验 |
| 创建 base / 已采用公共基线 | `03c38f280a64ad9bc9308c768f0f5795050355cc` / COMMON-002 推荐源码 `eb23784a7ed25b0f0364db0392783de277b22b96` |
| 已读台账的 SYNC_SHA / 实际工作 HEAD | `46a23a43572aed34bc2eec457d67423e2bce08af` / 更新本卡前真实输入修复 HEAD `5bea7621e4c90222d3f2e0000ab1ca6093af6e0b` |
| 同步源 / 实现与集成 SHA | `github/feature/astroncode-eval`（COMMON 已核验）；P2 `e388dfa43c0f38263ebcf57bf022ba1eb2c3cfeb`；COMMON merge `4529352ca92bf213995fd00433c6d77af3f8fc32`；组件绑定 `b3ac3da374165d74a41a3198e13d05928d671552`；输入修复 `5bea7621e4c90222d3f2e0000ab1ca6093af6e0b`；均未 push/未集成回公共分支 |
| 最后更新 | 2026-09-19（Asia/Shanghai），完成真实 canary 安全收尾、用户草稿恢复和 armed 前输入就绪修复 |

## 本轮范围与修改归属

实现 WorkBuddy 的 General Driver、轨迹/资源适配、正式 collect、评分交接和声明范围的并发/恢复。客户端专属文件和 fixtures 由本任务负责；公共注册、Schema、聚合与打包机制交给 COMMON 协调。现有 Web 的 WorkBuddy batch 可能被 QwenWork 复用，不能当作独占文件。

技术细项与证据入口：[General 验收清单](../../../general-e2e/通用场景端到端自动化评测实现计划与验收清单.md)中本 Harness 独立记录，映射 C/G、CV/GV；不得覆盖 AstronStudio 的 MAC 行。

工具 completed 与业务 success 分开，积分需核对请求范围/去重/实际结算；历史 Web 样本不能替代当前 General 真机证据。

## 依赖与完成清单

硬依赖：[COMMON](COMMON.md) 的 COMMON-CB04 已发布，且本任务的 adapter/状态/指标接口约定可取得。**不依赖 COMMON-CM01 的全部新增指标实现。** 基线未发布时可继续只读环境盘点、已有日志/fixture 分析和差异清单；不自创公共字段或依赖未合入 worktree。

- [x] P1：本机只读 probe、原生身份与字段/能力映射。实现 `2112a86450ba2f22fb284d37a20921cd7e65db69`；证据：[workbuddy-macos-readonly-20260919](../../../general-e2e/evidence/workbuddy-macos-readonly-20260919/README.md)。
- [ ] P2：单题一次发送、可信终态、恢复和正式证据收口。离线入口与 `Input.insertText + pre-arm enabled` 修复已完成，WorkBuddy 25/25；真实 canary 只消耗 reservation，实际 click/send/native session 均为 0，尚不能勾选。
- [ ] P3：原始轨迹/资源对账与完整单题评分/回传/报告。
- [ ] P4：按场景验收三题串行、五题动态补位及声明并发。
- [ ] P5：受影响故障加固、候选不可变与仓库外发行。
- [ ] P6：代码/证据/交接集成，必需接收动作完成。

勾选附实现/集成 SHA 与验收证据；此卡不复制技术验收 PASS 表。

## 下一项与阻塞

下一项：等待控制任务审查 `5bea762` 和新交接；从该 revision 或更高 revision 重建独立 release，取得新的桌面 slot 后重新运行原生/UI 空闲门禁，并为同一任务创建全新 attempt，验证一次实际发送、conversation/request/cwd 捕获和同 attempt 恢复。离线并行接入 WorkBuddy collector、trace-index v2 与真实 cleanup hook。

当前依赖缺口：COMMON-002/CB-B 已采用，但 WorkBuddy 专属 collector、原生 v2 输出和经真实子进程验证的 macOS cleanup hook 尚未实现。专属 driver 继续只放行已核验的 `5.5.3 + Electron`，是否公共化由 COMMON 决定。旧 attempt `3e554524-6599-4182-aecc-3257977867c0` 永不重发或重置；`5bea762` 尚无真实 WorkBuddy 输入事件证明。控制桌面状态为 `SLOT03_RELEASED`，不得自动继续客户端验证。

## 本机现场与恢复

本地证据根：`/Users/gzx/debug-workspace/e2e-evaluate/workbuddy-macos-general-e2e/`。prestart 时 WorkBuddy 主进程 0、原生 session 仅有历史 Completed；随后启动并核验 5.5.3/x86_64、loopback CDP 精确归属和唯一 WorkBuddy page target。运行时回读为 `xopglm52/default-sandbox`；单题 prepare/batch verify 已通过。释放桌面时应用仍运行且 CDP 存在，但该状态可能漂移，后续不得沿用而不重探。

canary attempt 的 journal 为 `NEEDS_ATTENTION`：旧实现把 Prompt 直接写入 DOM 后发送按钮仍 disabled，reservation 为 1，但实际 click/send/native session 为 0；conversation/request/cwd 均未绑定。同 attempt `--resume --observe-once` 没有重发。用户旧草稿已从私有 0700/0600 备份恢复，正文与 HTML 哈希均完全一致，仅动态 `style` 属性不同；candidate Prompt 已移除，Workspace/conversation 为空。私有正文和截图不入 Git、候选或评分包。

## 接收记录

| 交接 ID | 状态 | 已采用集成 SHA | 处理结果、验收证据/阻塞 | 下一项 |
| --- | --- | --- | --- | --- |
| COMMON-001 | VERIFIED | `0dd42824cb8eb510ab126fd74553f93312c9f201`（推荐源码 `ed366b30...963a`） | 无活动 WorkBuddy 进程后 merge；已按 CB-A 输出真实 conversation/request/cwd 映射，thread 为 null；公共 55/55、新增 Node 9/9 与语法检查通过 | P2 真机时段；CB-B 接口交接 |
| COMMON-002 | VERIFIED | `4529352ca92bf213995fd00433c6d77af3f8fc32`（SYNC `46a23a...08af`，推荐源码 `eb23784...2b96`） | WorkBuddy 精确绑定已更新到 discovery/contracts 1.2.0；shared/layout/contracts/build/collection Python 46/46、WorkBuddy/finalizer/discovery Node 38/38 通过 | 实现专属 trace v2 collector 与 cleanup hook；继续 canary |

## 本轮交付

P1 `2112a86450ba2f22fb284d37a20921cd7e65db69` 提供只读 probe/adapter；P2 `e388dfa43c0f38263ebcf57bf022ba1eb2c3cfeb` 提供安全可恢复单题入口；`5bea762` 改用 CDP `Input.insertText` 并将精确回读、唯一 enabled 发送控件前移到 armed 之前。WorkBuddy 25/25、General Node 93/93、相关 Python 60/60、专属依赖闭包、语法和 diff 检查通过。证据见 [P1 只读](../../../general-e2e/evidence/workbuddy-macos-readonly-20260919/README.md)和 [P2/canary 收口](../../../general-e2e/evidence/workbuddy-macos-p2-offline-20260919/README.md)；新交接为 [MAC-WORKBUDDY-GENERAL-002](../handoffs/MAC-WORKBUDDY-GENERAL-002.md)。真实 canary 没有实际发送、模型执行、原生 session、collect、评分或发行结论；用户现场已恢复。未 push、未集成。
