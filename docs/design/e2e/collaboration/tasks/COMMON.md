# COMMON：公共基线、共享能力与集成协调

| 字段 | 当前值 |
| --- | --- |
| 唯一负责人 | 本 macOS 控制任务；ID `01a0b79a-09d7-7271-810a-7796036b8f35` |
| 工作状态 / 代码交付 | ACTIVE / INTEGRATED；契约、CB-A/CB-B 与三个平台开发 Driver 已集成；正式采集、真机问题修复与新增指标继续推进 |
| 分支 / worktree | 文档：`feat/e2e-harness-contract` / `<主项目>/.agents/e2e-harness-contract`；CB-A：`feat/e2e-common-adapters` / `<主项目>/.agents/e2e-common-adapters` |
| 创建 base | `457e35560ea5cd090db1ce8b68c747de95ae3622` |
| 已采用本轮公共基线 / 实现与集成 SHA | 推荐源码 `2023b4d5d1d703c81ff8ed15e0d5ada29cd0dca4`；平台与公共原提交保留，见 COMMON-001/002/003/004 |
| 已读台账的 SYNC_SHA / 实际工作 HEAD | 初始 fetch `3cf2cc02c0c96ac05b3252262a78afc7a379a691`；公共台账 82e947b 已 push/ls-remote 核验；本轮输入修复与 COMMON-004 同步发布，实际 SYNC_SHA 由接收方固定，避免自指 SHA |
| 同步来源 | `github/feature/astroncode-eval`，已在本轮 fetch 核验 |
| 最后更新 | 2026-09-19（Asia/Shanghai），三个平台开发入口集成与采样交接 |

## 范围与修改归属

维护 [公共基线](../baseline.md)、任务归属、公共接口和集成交接。现有 AstronStudio macOS 最终 smoke 由“通用端到端自动化评测”任务收口，本卡负责核对其最终提交与证据，不再次跑一套或改它的活动工作区。此卡不意味着共享指标代码已经启动。

契约的要求以[统一契约](../../端到端自动化评测Harness接入契约.md)为准；技术验收引用 [General 清单](../../../general-e2e/通用场景端到端自动化评测实现计划与验收清单.md)与 [Web 清单](../../../web-e2e/Web站点端到端自动化评测生产验收清单.md)。共享 adapter 注册、状态/采集映射、指标 Schema/聚合、队列与发行变更先确定唯一实现负责人，平台任务按明确接口接入。

## 完成清单

- [x] **COMMON-DOC01**：契约、Windows 启动包和跨平台台账提交为 `9f9389e`，已随推荐源码发布。
- [x] **COMMON-CB01**：核对最终 smoke 提交 `86786e2`，来源任务已完成；collect/submission 和正式包 15 项哈希一致。未知交互/timeout、全量及 Windows 等边界沿用原记录，未提升支持声明。
- [x] **COMMON-CB02**：CB-A 集成于 `ed366b3`；run 0.4.0 / general-contracts 1.1.0；旧 AstronStudio macOS 兼容，新平台通用状态。trace/resource wire 不变，缺失策略保留。
- [x] **COMMON-CB03**：按实施边界确定公共文件负责人；集成源码 55 项测试通过，含 ZIP 脱仓；核对 GitHub fetch/push URL 和远端源码 SHA。
- [x] **COMMON-CB04**：推荐源码已发布，实际 SHA 及接收动作见 [COMMON-001](../handoffs/COMMON-001.md)；台账随后续提交同步。三个 Mac 任务已创建并核验绑定；Windows 接收方未代填通过。
- [x] **COMMON-CB05**：CB-B 第一批通用机制提交 `eb23784`，trace v2 / 多来源 / 共用 finalizer / cleanup hook 校验与脱仓执行完成；本轮 General 94 + Web 61 通过。平台真实原生采集和 cleanup 实现及正式闭环尚待各任务验收。
- [ ] **COMMON-CM01**：公共五项新增指标聚合/报告与 AstronStudio 参考映射，含 fixtures 和实际来源对账；不阻塞依赖已明确的客户端适配。
- [x] **COMMON-IN01**：接收并审查首批三平台 P2 与修复，保留原提交合入；COMMON-003 组合回归及本批变更复跑共 254/254，通过新增 COMMON-004。此勾选仅代表本批，不代表完整平台验收。
- [x] **COMMON-IN02**：WorkBuddy 输入修复及 canary 交接已集成，Qwen SLOT04 证据/COMMON-003 接收记录已集成；Web 最小复用方案明确，发布 COMMON-004。
- [ ] **COMMON-IN03**：WorkBuddy SLOT05 真实结果及专属 collector、Qwen selector/只读 DB/collector、Doubao cleanup 动态反例与等价绑定、COMMON 公共 Web 接线；逐项审查，不因前批已合入而跳过。

## 下一项与依赖

三个开发 Driver、组件绑定、execute 版本与 Qwen CLI 脱仓修复已纳入 [COMMON-003](../handoffs/COMMON-003.md)。WorkBuddy SLOT03 没有实际发送且已恢复用户草稿；Qwen SLOT04 因发送前项目控件歧义退出、已释放；Doubao 更正了已生成网站的证据，继续离线处理 terminal/cwd/cleanup。下一批重点为真实输入和正式 collector，公共 Web 适配范围由 COMMON 集中确定。

Windows 接收 COMMON-001/002/003 后直接推进本机 G5-01，无需等待 Mac 新 Harness 完成。活动批次先按原 revision 收口，空闲干净后再采用新源码。

随后推进 COMMON-CM01 的指标聚合与 AstronStudio 原始来源对账。客户端适配无需等全部指标完成；正式 General collect 依赖 CB-B，不复制现有 finalizer。

## 本机现场与恢复

控制集成 worktree 为 `.agents/e2e-harness-contract`；三个平台保持原绑定。SLOT01/02/03 已释放，SLOT04 也已释放；WorkBuddy 已获 SLOT05，Qwen/Doubao 继续离线修复。WorkBuddy 用户草稿已精确恢复，Doubao 候选 HTTP 服务残留不等于安全清理完成。实时状态以平台回报为准；完整调度见[控制推进记录](../control-progress.md)。原始数据位于 `/Users/gzx/debug-workspace/e2e-evaluate`，不写入仓库或 report-workspace。

## 接收记录

| 交接 ID | 状态 | 已采用集成 SHA | 处理结果与证据 | 下一项 |
| --- | --- | --- | --- | --- |
| 原 General smoke 收口（历史交付） | VERIFIED | `86786e219c29730dba26e28426bcbe3f2414dab8` | 本地 collect/submission 哈希及生产包 15 项通过；不冒充新接口真机证据 | COMMON-CB02 |
| MAC-WORKBUDDY-GENERAL-001 及 P2 后续交付 | ADOPTED | merge `8dac427`，含 `b3ac3da` | 源码/fixture 审查和 Node 23/23 通过；SLOT03 发送按钮 disabled，未实际发送，草稿已恢复 | 输入修复 5bea762 与新 handoff 已集成；SLOT05 真机与 collector待验 |
| MAC-QWENWORK-GENERAL-001/002 及恢复修复 | ADOPTED | merge `c4b1f7b`，含 `9081df5` | Node 32 + Python 3 与 Swift typecheck 通过；CLI 脱仓另修为 `dc5ff64` | 修 selector/关闭库 probe、交接 SLOT04 失败关闭证据与独立 collector |
| MAC-DOUBAOWORK-WEB-001/002 | ADOPTED | merge `b484085`、`769e9b5`，含 `3a3057c` | Node 39/39；一次发送/绑定、网站生成已核对；可信终态/cleanup/正式闭环未完成 | 原生来源、精确 cleanup 与 Web 公共接入 |

## 本轮交付

推荐源码 `2023b4d`。完整集成回归 254/254：General Python63、Node130、Web Python61；其中本批 WorkBuddy Node25、General Python46 已复跑。General execute0.8.1、Web execute1.15.0；COMMON-004 给出输入修复、Web等价证据和下一批动作。Doubao 0f6d2c6 因动态进程反例退回，未合入。没有新生产发行，也没有把三个客户端标成完整E2E通过。
