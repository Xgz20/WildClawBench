# COMMON：公共基线、共享能力与集成协调

| 字段 | 当前值 |
| --- | --- |
| 唯一负责人 | 本 macOS 控制任务；ID `01a0b79a-09d7-7271-810a-7796036b8f35` |
| 工作状态 / 代码交付 | ACTIVE / INTEGRATED；契约与 CB-A 已集成并发布，CB-B 和新增指标待实施 |
| 分支 / worktree | 文档：`feat/e2e-harness-contract` / `<主项目>/.agents/e2e-harness-contract`；CB-A：`feat/e2e-common-adapters` / `<主项目>/.agents/e2e-common-adapters` |
| 创建 base | `457e35560ea5cd090db1ce8b68c747de95ae3622` |
| 已采用本轮公共基线 / 实现与集成 SHA | 推荐源码 `ed366b30bc5ddd2ae35ef6361c3ac7c72ce9963a`；CB-A 实现 `abce5da832f16b48cd402ceef04a6abda544a379`，原提交保留 |
| 已读台账的 SYNC_SHA / 实际工作 HEAD | 初始 fetch `3cf2cc02c0c96ac05b3252262a78afc7a379a691`；推荐源码已 push/ls-remote 核验。后续台账提交和实际 HEAD 以 Git 历史为准，避免自指 SHA |
| 同步来源 | `github/feature/astroncode-eval`，已在本轮 fetch 核验 |
| 最后更新 | 2026-09-19（Asia/Shanghai），首次开发基线发布 |

## 范围与修改归属

维护 [公共基线](../baseline.md)、任务归属、公共接口和集成交接。现有 AstronStudio macOS 最终 smoke 由“通用端到端自动化评测”任务收口，本卡负责核对其最终提交与证据，不再次跑一套或改它的活动工作区。此卡不意味着共享指标代码已经启动。

契约的要求以[统一契约](../../端到端自动化评测Harness接入契约.md)为准；技术验收引用 [General 清单](../../../general-e2e/通用场景端到端自动化评测实现计划与验收清单.md)与 [Web 清单](../../../web-e2e/Web站点端到端自动化评测生产验收清单.md)。共享 adapter 注册、状态/采集映射、指标 Schema/聚合、队列与发行变更先确定唯一实现负责人，平台任务按明确接口接入。

## 完成清单

- [x] **COMMON-DOC01**：契约、Windows 启动包和跨平台台账提交为 `9f9389e`，已随推荐源码发布。
- [x] **COMMON-CB01**：核对最终 smoke 提交 `86786e2`，来源任务已完成；collect/submission 和正式包 15 项哈希一致。未知交互/timeout、全量及 Windows 等边界沿用原记录，未提升支持声明。
- [x] **COMMON-CB02**：CB-A 集成于 `ed366b3`；run 0.4.0 / general-contracts 1.1.0；旧 AstronStudio macOS 兼容，新平台通用状态。trace/resource wire 不变，缺失策略保留。
- [x] **COMMON-CB03**：按实施边界确定公共文件负责人；集成源码 55 项测试通过，含 ZIP 脱仓；核对 GitHub fetch/push URL 和远端源码 SHA。
- [x] **COMMON-CB04**：推荐源码已发布，实际 SHA 及接收动作见 [COMMON-001](../handoffs/COMMON-001.md)；台账随后续提交同步。三个 Mac 任务已创建并核验绑定；Windows 接收方未代填通过。
- [ ] **COMMON-CB05**：CB-B 公共正式收口、原生身份映射、多源 trace/provenance 和平台进程清理 hook；新 General adapter 的正式 collect 依赖此项，probe/执行与 fixtures 可先推进。
- [ ] **COMMON-CM01**：公共五项新增指标聚合/报告与 AstronStudio 参考映射，含 fixtures 和实际来源对账；不阻塞依赖已明确的客户端适配。
- [ ] **COMMON-IN01**：接收平台改动、合入并派发受影响回归；每一批新增交接 ID，不能以本项勾选替代所有后续轮次。

## 下一项与依赖

COMMON-001 已交付三个 Mac 任务，首轮实现/证据与公共需求已收到。本轮审查修复、P2推进和桌面时段见[控制推进记录](../control-progress.md)。COMMON-CB05 正在独立公共 worktree 实现，未发布的新接口不作为已采用基线。Windows 仍按 COMMON-001 自行开始本机任务并回写接收结果。

随后推进 COMMON-CM01 的指标聚合与 AstronStudio 原始来源对账。客户端适配无需等全部指标完成；正式 General collect 依赖 CB-B，不复制现有 finalizer。

## 本机现场与恢复

文档与公共接口 worktree 已登记。三个 Mac 任务沿用原绑定，见[派发记录](../dispatch.md)；第二轮已将唯一桌面时段分配给 DoubaoWork 开发采样，其余任务离线开发。实际发送/活动现场以平台回报为准，不能从时段分配推断已发送或已停止。调试产物使用 `/Users/gzx/debug-workspace/e2e-evaluate`，原始候选/轨迹不放进台账。

## 接收记录

| 交接 ID | 状态 | 已采用集成 SHA | 处理结果与证据 | 下一项 |
| --- | --- | --- | --- | --- |
| 原 General smoke 收口（历史交付） | VERIFIED | `86786e219c29730dba26e28426bcbe3f2414dab8` | 本地 collect/submission 哈希及生产包 15 项通过；不冒充新接口真机证据 | COMMON-CB02 |
| MAC-WORKBUDDY-GENERAL-001 | SEEN | 未集成 | 已读首轮交付并要求修复状态/来源路径/工具结局，公共需求纳入 CB-B | 复核后集成 |
| MAC-QWENWORK-GENERAL-001 | SEEN | 未集成 | 已读首轮交付并要求修复终态/会话选择/工具结局，公共需求纳入 CB-B | 复核后集成 |
| MAC-DOUBAOWORK-WEB-001 | SEEN | 未集成 | 已读交付；路径/去重反例待修复，分配首个开发采样时段 | 采样与公共接入 |

## 本轮交付

契约与 CB-A 已发布为推荐源码 `ed366b3`，55 项集成测试通过。首条跨平台交接 COMMON-001 明确源码/版本、平台动作、CB-B 依赖和证据边界；真实 Mac 任务 ID/worktree 单列派发记录，Windows 启动 Prompt 与清单随代码可取。文档结构检查与 fixture/脱仓测试不作为新平台真机证据。
