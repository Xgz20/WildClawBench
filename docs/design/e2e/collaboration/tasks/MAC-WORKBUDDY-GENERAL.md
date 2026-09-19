# MAC-WORKBUDDY-GENERAL：WorkBuddy macOS General

| 字段 | 当前值 |
| --- | --- |
| 唯一负责人 / 实际任务 ID | 待创建独立 macOS 任务；尚未启动 |
| 工作状态 / 代码交付 | PLANNED / LOCAL_ONLY（当前仅有任务定义，无本任务实现交付） |
| 计划分支 / worktree | `feat/workbuddy-macos-general-e2e` / `<主项目>/.agents/workbuddy-macos-general-e2e`，尚未创建 |
| 创建 base / 已采用公共基线 | 待 COMMON-CB04 / 未采用 |
| 已读台账的 SYNC_SHA / 实际工作 HEAD | 尚未同步本轮远端台账；接手核验后分别记录 |
| 同步源 / 实现与集成 SHA | 接手核对实际仓库及本机 remote；未提交、未集成 |
| 最后更新 | 2026-09-19（Asia/Shanghai），控制任务初始化；接手后由本任务维护 |

## 本轮范围与修改归属

实现 WorkBuddy 的 General Driver、轨迹/资源适配、正式 collect、评分交接和声明范围的并发/恢复。客户端专属文件和 fixtures 由本任务负责；公共注册、Schema、聚合与打包机制交给 COMMON 协调。现有 Web 的 WorkBuddy batch 可能被 QwenWork 复用，不能当作独占文件。

技术细项与证据入口：[General 验收清单](../../../general-e2e/通用场景端到端自动化评测实现计划与验收清单.md)中本 Harness 独立记录，映射 C/G、CV/GV；不得覆盖 AstronStudio 的 MAC 行。

工具 completed 与业务 success 分开，积分需核对请求范围/去重/实际结算；历史 Web 样本不能替代当前 General 真机证据。

## 依赖与完成清单

硬依赖：[COMMON](COMMON.md) 的 COMMON-CB04 已发布，且本任务的 adapter/状态/指标接口约定可取得。**不依赖 COMMON-CM01 的全部新增指标实现。** 基线未发布时可继续只读环境盘点、已有日志/fixture 分析和差异清单；不自创公共字段或依赖未合入 worktree。

- [ ] P1：本机只读 probe、原生身份与字段/能力映射。
- [ ] P2：单题一次发送、可信终态、恢复和正式证据收口。
- [ ] P3：原始轨迹/资源对账与完整单题评分/回传/报告。
- [ ] P4：按场景验收三题串行、五题动态补位及声明并发。
- [ ] P5：受影响故障加固、候选不可变与仓库外发行。
- [ ] P6：代码/证据/交接集成，必需接收动作完成。

勾选附实现/集成 SHA 与验收证据；此卡不复制技术验收 PASS 表。

## 下一项与阻塞

下一项：核对 WorkBuddy 安装/版本/CDP、原生会话/Workspace 绑定和日志来源，形成只读能力清单；按最终公共接口决定复用项与 General 专属缺口。

当前依赖缺口：首次公共基线尚未发布，责任方 COMMON，恢复条件为公共基线及相关交接可从集成分支取得。当前未开始平台实施，不把未知本机条件写成测试失败。

## 本机现场与恢复

未登记，接手先检查本机活动进程、队列与既有批次；不能推断桌面空闲。登记本地证据根、实际版本/配置、batch/unit/attempt、原生 session/thread/turn/cwd、候选状态及真实 resume 入口。代码更新仅在相关批次安全收口后进行，不覆盖历史现场。

## 接收记录

| 交接 ID | 状态 | 已采用集成 SHA | 处理结果、验收证据/阻塞 | 下一项 |
| --- | --- | --- | --- | --- |
| 尚无记录 | — | — | 接手扫描全部目标含 MAC-WORKBUDDY-GENERAL/ALL 的正式交接；此行不表示不存在新交接 | P1 |

## 本轮交付

仅初始化任务定义；无实现、无本平台新真机证据、无提交/推送。后续每批交付新增交接 ID，登记来源 revision、差异、验证范围及发给其他任务的具体动作。
