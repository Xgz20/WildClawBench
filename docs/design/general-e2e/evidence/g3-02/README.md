# G3-02 本地受管规则评分运行时证据

> 证据边界：本文只记录所列日期、批次和 revision 的事实，保留原失败与未知项。当前集成进度和下一步统一见[集成契约](../../../e2e/端到端自动化评测Harness接入契约.md#integration-progress)，不从本文旧“当前/下一步”推导最新支持状态。

## 结论

2026-09-18 在 macOS `26.6.2/x86_64` 上完成 General E2E 无 Docker 规则评分运行时的实现与验证。`score-general-e2e` `0.3.0/interface_only` 已能从正式 execution record 和独立 scoring ZIP 创建私有单题 attempt，在专用 Python Worker 中运行冻结自动规则，并生成规则组件与运行审计。

当前交付只覆盖自动规则子能力。语义裁判、合分审计和标准 `score.json` 仍由 G3-03 至 G3-05 实现，因此不能把规则组件当作完整 General E2E 成绩，也不能把 `score-general-e2e` 整体标为 `operational`。

## 固定运行时

| 项目 | 固定值 |
| --- | --- |
| Python | `3.11`；本次探针为 `3.11.14` |
| Python 依赖 | PyYAML `6.0.3`、Playwright `1.55.0`、greenlet `3.5.6`、pyee `13.0.1`、typing_extensions `4.16.0` |
| 浏览器 | Chromium revision `1187`，version `140.0.7339.16` |
| runtime lock SHA-256 | `2e2f86fb667c320e085363671b5d34939ede1d5799071119c9ce06514abcf554` |
| requirements SHA-256 | `f0225b6cf5baa31d232c4b12f838b48d43387c908458c16cccb14e19e03c31c9` |
| bootstrap 探针 | 五个锁定包版本匹配；Chromium headless 启动成功，页面标题 `general-e2e-runtime` |

依赖与浏览器身份由 Skill 内的 [runtime lock](../../../../../tools/report/skills/general-e2e/score-general-e2e/references/scoring-runtime-lock.json) 和 [requirements](../../../../../tools/report/skills/general-e2e/score-general-e2e/references/scoring-runtime-requirements.txt) 固定。运行时 marker 的本机验证 SHA-256 为 `84fa106c8345230980d394282f45ae1f4170fef668d5bdcbc80d6e5a88334ec0`；该 marker 含临时绝对路径，不作为发行制品提交。

## 真实 S1 冻结用例

| 项目 | 结果 |
| --- | --- |
| task | `02_Code_Intelligence_task_001_temperature_cli_fix` |
| execution attempt | `693c1c28-a78a-409b-82d7-b0dfcadb3132` |
| scoring attempt | `g3-02-locked-runtime` |
| dataset | `general-custom60-v1` / `119568a06a100461445c92544ca4c90e0c5c70fba49711a0fd915a6c708f1d0a` |
| transcript | 24 个完整标准事件；SHA-256 `a829deabe469e9827497d7e13dc8df5d2f6c5d70d5bc6d541b0e17a64abf2ed7` |
| 候选原件 | 只读；SHA-256 `87cf47353206e9ceb4c4d9bb67a4326bc76ef7376cf26b03c82da5514362e070` |
| 规则结果 | `completed`，四项 criterion 均为 `1.0`，规则组件总分 `1.0` |
| 运行审计 | `local-managed-python-worker`；`docker_used=false`；未超时；Worker 返回码 0 |
| runtime 漂移 | 初始/终态 SHA-256 均为 `d6a7c9b2476daa8adb19b009c4fd72bbadf68d09f4be435f4adb8ad94586e10d` |
| 摘要产物 SHA-256 | attempt manifest `7dddfabf3ac62c15f505134729d421565675da037935ab68c11cb2fa364faeb2`；rule component `486fc5b9a084f94990468c5eb5379cec08daa79a2df40231c5e6500015f75bdc`；rule audit `8aa82c9e80d7fa10a16d7c823beea1c421bf589eba7f543890253a5d1ff4b9fa` |

该 attempt 复用 G2-05 已冻结的正式 S1 execution record，没有重跑 Harness 或发送新 Prompt。私有 scoring ZIP、GT、完整 transcript、Worker request 和一次性 runtime 副本只保留在本机临时目录，不复制到文档仓库。

## 运行与失败门禁

- 候选只读原件和一次性可写 runtime 副本分离；GT 仅在执行完成后注入 runtime 的 `gt/`。
- Worker 通过结构化 JSON IPC 接收真实本机 workspace 绝对路径和完整 transcript；`/tmp_workspace` 只作为题目协议的逻辑路径。
- Worker 只继承固定环境变量白名单，不继承 HOME、云凭据或模型凭据；日志、结果和执行时间均有限额。
- POSIX Worker 使用独立进程组。超时测试启动 Worker 子进程，确认先记录 `SIGTERM`，随后 Worker 与子进程均不存在，审计中 `remaining=false`。
- ZIP 路径穿越、重复成员、越界 symlink、候选漂移、runtime 漂移、候选自带 `gt`、私有材料冲突和 attempt 覆盖均失败关闭。
- 独立 Skill ZIP 可自动定位 vendored `grading-core`，不依赖当前 checkout；独立 release build/verify 已通过。

## 平台与安全边界

| 平台 | 状态 | 说明 |
| --- | --- | --- |
| macOS x86-64 | PASS | bootstrap、Chromium、Playwright Worker、真实 S1、超时进程组清理均已验证 |
| Windows | NOT_RUN | PowerShell 进程树终止路径与 `Scripts/python.exe` 路径已实现并有静态覆盖，但尚未在 Windows 真机完成依赖安装、浏览器启动、超时和残留进程验证 |

专用虚拟环境、环境白名单和进程树清理用于依赖复现、凭据隔离与故障收口，不是针对恶意 grader 的安全沙箱。运行时只允许执行版本化数据集中的冻结可信规则；不得传入任意第三方 Python 代码。
