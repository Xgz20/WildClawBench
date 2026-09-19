# COMMON：公共基线、共享能力与集成协调

| 字段 | 当前值 |
| --- | --- |
| 唯一负责人 | 本 macOS 控制任务；ID `01a0b79a-09d7-7271-810a-7796036b8f35` |
| 工作状态 / 代码交付 | ACTIVE / LOCAL_ONLY，契约已本地提交；公共接口实施中，尚待集成发布 |
| 分支 / worktree | 文档：`feat/e2e-harness-contract` / `<主项目>/.agents/e2e-harness-contract`；CB-A：`feat/e2e-common-adapters` / `<主项目>/.agents/e2e-common-adapters` |
| 创建 base | `457e35560ea5cd090db1ce8b68c747de95ae3622` |
| 已采用本轮公共基线 / 实现与集成 SHA | 本轮待发布；文档初始提交 `9f9389e`，已在契约 worktree 合入主项目 `3cf2cc0` |
| 已读台账的 SYNC_SHA / 实际工作 HEAD | 远端同步核验 `3cf2cc02c0c96ac05b3252262a78afc7a379a691`；后续文档/接口提交以 Git 历史为准 |
| 同步来源 | `github/feature/astroncode-eval`，已在本轮 fetch 核验 |
| 最后更新 | 2026-09-19（Asia/Shanghai），控制任务初始化记录 |

## 范围与修改归属

维护 [公共基线](../baseline.md)、任务归属、公共接口和集成交接。现有 AstronStudio macOS 最终 smoke 由“通用端到端自动化评测”任务收口，本卡负责核对其最终提交与证据，不再次跑一套或改它的活动工作区。此卡不意味着共享指标代码已经启动。

契约的要求以[统一契约](../../端到端自动化评测Harness接入契约.md)为准；技术验收引用 [General 清单](../../../general-e2e/通用场景端到端自动化评测实现计划与验收清单.md)与 [Web 清单](../../../web-e2e/Web站点端到端自动化评测生产验收清单.md)。共享 adapter 注册、状态/采集映射、指标 Schema/聚合、队列与发行变更先确定唯一实现负责人，平台任务按明确接口接入。

## 完成清单

- [x] **COMMON-DOC01**：契约、Windows 启动包和跨平台台账提交为 `9f9389e`；已在文档分支合入最新主项目，尚待公共发布。
- [x] **COMMON-CB01**：核对最终 smoke 提交 `86786e2`，来源任务已完成；collect/submission 和正式包 15 项哈希一致。未知交互/timeout、全量及 Windows 等边界沿用原记录，未提升支持声明。
- [ ] **COMMON-CB02**：契约与最小公共接口集成，明确 adapter/状态/指标字段版本、兼容和缺失值策略；未实现项如实列出。
- [ ] **COMMON-CB03**：确定公共文件负责人，完成必要回归；核对两机同步仓库与集成分支。
- [ ] **COMMON-CB04**：在既有授权内发布可消费基线及交接，登记真实 SHA；此项是四个新平台任务进入适配实施的共同前提。
- [ ] **COMMON-CB05**：CB-B 公共正式收口、原生身份映射、多源 trace/provenance 和平台进程清理 hook；新 General adapter 的正式 collect 依赖此项，probe/执行与 fixtures 可先推进。
- [ ] **COMMON-CM01**：公共五项新增指标聚合/报告与 AstronStudio 参考映射，含 fixtures 和实际来源对账；不阻塞依赖已明确的客户端适配。
- [ ] **COMMON-IN01**：接收平台改动、合入并派发受影响回归；每一批新增交接 ID，不能以本项勾选替代所有后续轮次。

## 下一项与依赖

下一项：审查并合入 CB-A adapter/state 接口，验证旧 AstronStudio 与脱仓闭包，完成 COMMON-CB02/03/04，派发三个 macOS 独立任务与 Windows 交接。公共接口代码由本控制任务的独立 worktree 实现，不能由平台分支分别改造。

之后完成 COMMON-CB02/03/04。公共指标全实现不是 CB04 的条件；但接口和缺失值语义必须有明确依据，不能把一个文档草案当作通用 adapter 入口已经实现。

## 本机现场与恢复

文档与公共接口 worktree 已登记；本轮没有发送评测 Prompt。原 General 任务已确认 idle/completed，但这不代表全桌面没有其他工作，任何后续操作先检查现场。三个新 macOS 任务首阶段只做独立开发与只读盘点，真机时段由本控制任务安排。调试产物使用 `/Users/gzx/debug-workspace/e2e-evaluate`，原始候选/轨迹不放进台账。

## 接收记录

| 交接 ID | 状态 | 已采用集成 SHA | 处理结果与证据 | 下一项 |
| --- | --- | --- | --- | --- |
| 原 General smoke 收口（历史交付） | VERIFIED | `86786e219c29730dba26e28426bcbe3f2414dab8` | 本地 collect/submission 哈希及生产包 15 项通过；不冒充新接口真机证据 | COMMON-CB02 |

## 本轮交付

文档初始提交为 `9f9389e`，已在契约 worktree 合入 `3cf2cc0`；本轮开发基线尚未 push，正式交接待公共接口通过后发布。初始 14 份文档/100 个本地链接、5 张任务卡与索引及契约 3 章/32 个唯一要求校验通过；补充并行实施边界和历史指标盘点后再次检查链接、代码块与 `git diff --check` 通过。这些是文档结构检查，不作为平台真机证据。
