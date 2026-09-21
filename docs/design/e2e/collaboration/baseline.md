# 公共基线与同步约定

维护方：COMMON。更新日期：2026-09-21。本文登记可消费基线；各平台自行回写采用和验证。

| 字段 | 当前记录 |
| --- | --- |
| 控制集成分支 | `feat/e2e-harness-contract` / 后续直接在本分支串行迭代，不再派发平台 worktree |
| 主工作分支 / 同步仓库 | `feature/astroncode-eval` / `https://github.com/Xgz20/WildClawBench.git` |
| 已核验 remote | macOS 为 `github`，fetch/push URL 一致；Windows 接收方核对实际 URL，不假定 `origin` |
| 推荐开发源码基线 | `414beeff50ad456a4624038f4519dd0a9b8412d8`；包含父提交 `4537fff`、`73edb63` 与 `e17c11c` |
| 基线状态 | `DEVELOPMENT_LOCAL_VALIDATED`；WorkBuddy macOS 值守单槽为 `CONTROLLED_PRODUCTION_READY`；本轮提交尚未推送，接收方暂不能仅靠 fetch 取得 |
| 当前必读交接 | [COMMON-001](handoffs/COMMON-001.md)、[COMMON-002](handoffs/COMMON-002.md)、[COMMON-003](handoffs/COMMON-003.md)、[COMMON-004](handoffs/COMMON-004.md)、[WorkBuddy 当前任务卡](tasks/MAC-WORKBUDDY-GENERAL.md)，以及本页登记的 2026-09-21 超时语义变更 |
| 实现提交 | CB-A `abce5da8`；CB-B `eb23784a`；WorkBuddy 五题收口至 `645d9ca`；迟到评分恢复 `73edb63`；受控 submission 刷新 `414beef`；无 Harness 总执行时限 `0563b94`、`7a2142a`、`9885a4c` |
| 契约 / 版本 | `E2E-HARNESS-CONTRACT/0.1` / `run-general-e2e@0.5.0` / `general-contracts@1.2.0`；General execute 0.10.3、collect 0.6.1、orchestrate 0.9.2、score 0.8.1；Web execute 1.16.0 |
| 开发接口 | [通用执行状态接口](../../../../tools/report/skills/general-e2e/run-general-e2e/references/adapter-execution-state.md)，已集成 CB-A；CB-B 通用 finalizer / trace v2 已可消费，平台原生采集与真实 cleanup hook 仍需分别实现验证 |
| 验证范围 | 合并后 E2E 组合回归 578/578：General Node 162、General Python 80、Web Node 275、Web Python 61；MiniMax 新增测试 19/19、相关 tool/layout 67/67；submission 刷新相关 42/42；更宽 anomaly 套件仍有 1 个既有 AstronClaw 样本断言失败。WorkBuddy v4 为执行/采集/评分/回传/报告 5/5，主流程受控生产可用；无新 Windows/QwenWork/DoubaoWork 正式闭环声明 |
| 串行任务 | WorkBuddy 本轮完成；下一平台可从 QwenWork selector/真实一次发送继续，切换前先按当前控制 HEAD 核验代码和现场 |
| 后续迭代规则 | 直接在控制分支逐项修改并单独提交；旧平台 worktree 仅保留审计，不作为新任务来源 |
| 未完成公共项 | Qwen selector/关闭库 probe；Doubao 可信 terminal/cwd、公共 cleanup/finalizer；COMMON-CM01 新增五项指标；WorkBuddy 后台并发、无人值守、Apple Silicon 与 60 题属于扩容项 |
| macOS 既有 smoke | [双题 smoke](../../general-e2e/evidence/macos-current-smoke-20260919/README.md)、[G4-03](../../general-e2e/evidence/g4-03/README.md)；证据提交 `86786e219c29730dba26e28426bcbe3f2414dab8`，实际执行源码 `457e35560ea5cd090db1ce8b68c747de95ae3622` |
| 发行身份 | WorkBuddy 生产套件 `general-macos-workbuddy-production-20260921-122448`，source revision `414beeff50ad456a4624038f4519dd0a9b8412d8`，suite SHA `1697bc6d4b695dea9e92b5b8d9b2d7ec61755d1251094f08c9effa1bdf9f5e83`，目录与 suite 双重校验 PASS；旧包身份继续保留 |

首次发布检查：

- [x] 核对原 macOS 收口提交、collect/submission 和旧生产包哈希。
- [x] 集成契约、协作台账及 CB-A，明确接口版本、缺失值策略和文件归属。
- [x] 在集成源码完成 55 项聚焦回归。
- [x] 推送推荐源码，通过远端 ref 核验。
- [x] 编写 COMMON-001 与真实派发记录；台账随本次提交同步，接收方记录包含它的 SYNC_SHA。

| 基线标识 | 可消费源码 SHA | 交接 ID | 必需动作 | 发布结果 |
| --- | --- | --- | --- | --- |
| E2E-PROD-WORKBUDDY-MACOS-20260921-A | `414beeff50ad456a4624038f4519dd0a9b8412d8` | WorkBuddy 当前任务卡 | 使用新 suite；首个正式批次先跑 3–5 个 L1 canary；不外推后台并发、Apple Silicon 或 60 题 | CONTROLLED_PRODUCTION_READY |
| E2E-DEV-20260921-A | `4537fff2c64600395ca499f7def0e2f579af386a` | 当前台账 | 采用无 Harness 总执行时限、迟到评分恢复和控制分支现有平台能力；旧真机证据保持原 revision | DEVELOPMENT_LOCAL_VALIDATED |
| E2E-DEV-20260919-D | `2023b4d5d1d703c81ff8ed15e0d5ada29cd0dca4` | COMMON-004 | WorkBuddy 输入修复、execute 0.8.1、Web 等价绑定方案；当前 live 按原身份收口 | DEVELOPMENT_PUBLISHED |
| E2E-DEV-20260919-C | `dc5ff64c3d7b91ae0ecc6669583f5bd3d69c13c3` | COMMON-003 | 采用三个开发 Driver 与 execute 版本；处理真机限制及 CLI 修复；活动 attempt 不切版本 | DEVELOPMENT_PUBLISHED |
| E2E-DEV-20260919-B | `eb23784a7ed25b0f0364db0392783de277b22b96` | COMMON-002 | 更新组件绑定与受影响 Skill；接入 trace v2 / cleanup hook；平台真机另验 | DEVELOPMENT_PUBLISHED |
| E2E-DEV-20260919-A | `ed366b30bc5ddd2ae35ef6361c3ac7c72ce9963a` | COMMON-001 | 采用源码及最新台账、完成相关 fixture；本平台真机另验 | DEVELOPMENT_PUBLISHED |

源码 SHA、台账 SYNC_SHA、本机实际 HEAD、发行 source revision 分别记录。本文不引用自身未知提交；接收方固定 fetch 得到的完整 SYNC_SHA，确认包含推荐源码、本交接和后来所有适用交接后再采用。旧 smoke 只证明其原 revision 和声明范围。
