# 公共基线与同步约定

维护方：COMMON。更新日期：2026-09-19。本文登记可消费基线；各平台自行回写采用和验证。

| 字段 | 当前记录 |
| --- | --- |
| 集成分支 / 同步仓库 | `feature/astroncode-eval` / `https://github.com/Xgz20/WildClawBench.git` |
| 已核验 remote | macOS 为 `github`，fetch/push URL 一致；Windows 接收方核对实际 URL，不假定 `origin` |
| 推荐开发源码基线 | `dc5ff64c3d7b91ae0ecc6669583f5bd3d69c13c3` |
| 基线状态 | `DEVELOPMENT_PUBLISHED`；COMMON-003 随本轮台账发布；接收方 fetch 后核验推荐源码祖先关系，不是新平台生产准入 |
| 当前必读交接 | [COMMON-001](handoffs/COMMON-001.md)、[COMMON-002](handoffs/COMMON-002.md)、[COMMON-003](handoffs/COMMON-003.md)；须取得含全部适用交接的最新台账提交 |
| 实现提交 | CB-A `abce5da832f16b48cd402ceef04a6abda544a379`；CB-B `eb23784a7ed25b0f0364db0392783de277b22b96`，均保留原提交 |
| 契约 / 版本 | `E2E-HARNESS-CONTRACT/0.1` / `run-general-e2e@0.5.0` / `general-contracts@1.2.0`；General execute 0.8.0 / Web execute 1.15.0；全量版本见 COMMON-003 |
| 开发接口 | [通用执行状态接口](../../../../tools/report/skills/general-e2e/run-general-e2e/references/adapter-execution-state.md)，已集成 CB-A；CB-B 通用 finalizer / trace v2 已可消费，平台原生采集与真实 cleanup hook 仍需分别实现验证 |
| 验证范围 | 本轮 252 项组合测试通过（General Python 63、Node 128、Web Python 61），含新 Driver ZIP 脱仓入口；没有新 Harness/Windows 正式闭环通过声明 |
| 并行任务 | 三个 macOS 独立任务已启动并核验 worktree 绑定，见[派发记录](dispatch.md)；平台卡由各自负责人更新后交付集成 |
| 未完成公共项 | WorkBuddy 输入事件修复、各平台正式收口与真机验收、COMMON-CM01 新增五项指标；不阻塞已有接口的独立开发 |
| macOS 既有 smoke | [双题 smoke](../../general-e2e/evidence/macos-current-smoke-20260919/README.md)、[G4-03](../../general-e2e/evidence/g4-03/README.md)；证据提交 `86786e219c29730dba26e28426bcbe3f2414dab8`，实际执行源码 `457e35560ea5cd090db1ce8b68c747de95ae3622` |
| 发行身份 | 本轮未新建生产包；旧包 `general-macos-production-20260919-141301` 的 suite SHA 为 `64208e9828cf32457938abb616bd522a914aaeda3828735d9169236f575059ec`，15 个产物哈希已核验；新代码不得借用旧身份或真机证据 |

首次发布检查：

- [x] 核对原 macOS 收口提交、collect/submission 和旧生产包哈希。
- [x] 集成契约、协作台账及 CB-A，明确接口版本、缺失值策略和文件归属。
- [x] 在集成源码完成 55 项聚焦回归。
- [x] 推送推荐源码，通过远端 ref 核验。
- [x] 编写 COMMON-001 与真实派发记录；台账随本次提交同步，接收方记录包含它的 SYNC_SHA。

| 基线标识 | 可消费源码 SHA | 交接 ID | 必需动作 | 发布结果 |
| --- | --- | --- | --- | --- |
| E2E-DEV-20260919-C | `dc5ff64c3d7b91ae0ecc6669583f5bd3d69c13c3` | COMMON-003 | 采用三个开发 Driver 与 execute 版本；处理真机限制及 CLI 修复；活动 attempt 不切版本 | DEVELOPMENT_PUBLISHED |
| E2E-DEV-20260919-B | `eb23784a7ed25b0f0364db0392783de277b22b96` | COMMON-002 | 更新组件绑定与受影响 Skill；接入 trace v2 / cleanup hook；平台真机另验 | DEVELOPMENT_PUBLISHED |
| E2E-DEV-20260919-A | `ed366b30bc5ddd2ae35ef6361c3ac7c72ce9963a` | COMMON-001 | 采用源码及最新台账、完成相关 fixture；本平台真机另验 | DEVELOPMENT_PUBLISHED |

源码 SHA、台账 SYNC_SHA、本机实际 HEAD、发行 source revision 分别记录。本文不引用自身未知提交；接收方固定 fetch 得到的完整 SYNC_SHA，确认包含推荐源码、本交接和后来所有适用交接后再采用。旧 smoke 只证明其原 revision 和声明范围。
