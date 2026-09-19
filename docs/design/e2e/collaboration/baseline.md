# 公共基线与同步约定

维护方：COMMON。更新日期：2026-09-19。本文只登记可消费的公共基线与集成决定，不记录每台机器的已采用状态；后者在各任务卡。

| 字段 | 当前记录 |
| --- | --- |
| 集成分支 | `feature/astroncode-eval`，按当前工程工作分支建立协作约定；仅集成负责人合入公共结果 |
| 本 macOS 检出的 upstream | `github/feature/astroncode-eval`；2026-09-19 已 fetch 核验，远端仓库为 `github.com/Xgz20/WildClawBench` |
| Windows remote | 未核验；别名可不同，首次接手核对实际仓库与上述同步源一致并记录在 Windows 任务卡，禁止直接假定 `origin` |
| 最近核验的主项目源码 | `3cf2cc02c0c96ac05b3252262a78afc7a379a691`；保留最新 Git 同步修复；macOS smoke 证据提交为 `86786e219c29730dba26e28426bcbe3f2414dab8` |
| 本轮推荐开发基线 SHA | **待登记**：macOS 最终收口、契约及最小公共接口集成后填写 |
| 本轮基线状态 | `NOT_PUBLISHED`；新卡已初始化，但尚未发起新 Harness 任务 |
| 契约目标 | `E2E-HARNESS-CONTRACT/0.1`，契约/协作初始提交 `9f9389e`；未实现条款仍按适用能力逐步落地 |
| 最小公共接口 | CB-A 开发接口在独立 `.agents/e2e-common-adapters` 实现；CB-B 正式收口独立推进，见[实施边界](implementation-boundaries.md) |
| 现有 macOS 验收参考 | [当前双题 smoke](../../general-e2e/evidence/macos-current-smoke-20260919/README.md)与 [G4-03](../../general-e2e/evidence/g4-03/README.md)已核对；源码 `457e35560ea5cd090db1ce8b68c747de95ae3622` 的受控生产证据不自动继承为新公共接口真机证据 |
| 分发/数据集身份 | 此轮交付是开发基线，不是新发行候选。既有正式包 `general-macos-production-20260919-141301` 的 source 为 `457e355...`，suite SHA `64208e9828cf32457938abb616bd522a914aaeda3828735d9169236f575059ec`，15 个 manifest 产物哈希已本地核验；后续新代码需重新构建并核验自身身份 |
| 是否需等待新增指标全量完成 | 否；原始采集、字段映射和 fixture 可并行，公共字段语义/版本先明确 |

首次发布前的清单：

- [x] 核对最终 AstronStudio macOS 收口提交与证据：86786e2，collect/submission 的本地 SHA 与记录一致，正式包 15 项哈希一致；旧真机证据仅按原版本沿用。
- [ ] 合入接入契约、本协作台账及必要公共接口，记录实际实现/集成 SHA；不存在的接口明确列为后续任务。
- [ ] 明确哪些能力可直接开发、哪些依赖尚未满足；指标的缺失策略一致。
- [ ] 写明公共修改的唯一负责人及各任务允许的修改范围。
- [ ] 在获准同步时推送约定集成分支，并通过远端 ref 核验代码与台账均可获取。
- [ ] 将推荐基线 SHA 填为已存在的集成源码提交，登记变更交接；各平台同步后自行回写已采用状态。

每次推进推荐基线时追加记录，不覆盖旧轮次：

| 基线标识 | 可消费源码 SHA | 交接 ID | 平台受影响项/必需动作 | 发布结果 |
| --- | --- | --- | --- | --- |
| 尚无正式轮次 | — | — | — | NOT_PUBLISHED |

不要把本文所在提交写进自身内容。源码 revision、台账提交、发行包 source revision 和本机实际运行 revision 分别记录；有差异时说明原因。最新集成 HEAD 超过推荐基线时，接收方还应检查中间交接，不能跳过影响核对。
