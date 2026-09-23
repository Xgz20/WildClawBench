# MAC-QWENWORK-GENERAL-002：P2 离线一次发送与恢复 Driver

> 历史档案：保留迁移前的日期、版本、结果和失败记录。“当前/下一步”、旧派发和桌面时段要求仅属当时快照。现行集成要求及各 Harness 进度只维护在[统一集成契约](../../../端到端自动化评测Harness接入契约.md)。

> 历史档案（2026-09-21 冻结）：仅供提交与证据追溯，旧派发、时段、负责人、下一项和跨平台并行安排均已退役。当前状态和操作以 [General E2E 接续入口](../../../端到端自动化评测Harness接入契约.md#integration-progress) 为准；本文件不再例行更新。

| 字段 | 值 |
| --- | --- |
| 交接 ID / 创建时间 | `MAC-QWENWORK-GENERAL-002` / 2026-09-19（Asia/Shanghai） |
| 来源任务 | `MAC-QWENWORK-GENERAL` |
| 目标任务 | COMMON / 控制任务 |
| 基线 / 实现 SHA | `dac06696142969195c2af93f7442cd39d5a279fb` / `0b732fb432674eb2c1fd388018b1e66ede790066` |
| 集成状态 | LOCAL_ONLY；未 push、未集成 |
| 修改范围 | QwenWork General execute Driver/journal/UI/native session；QwenWork adapter outcome；专属 tests |
| 关联验收 | MAC P2；C02/C04/C07/C09/C13–C16、CV02–CV04/CV07/CV11/CV12、G04/G05 |

## 已交付

- 新增客户端专属 `driver.mjs`、`journal.mjs`、`ui.mjs` 和 General 内自包含的 macOS 原生目录助手；不 import Web Skill。
- 冻结 canary 配置、`--validate-only`、首次执行和 `--resume --observe-once` CLI 已实现；Driver 不负责启动/重启/退出 QwenWork。
- 发送前持久化 Prompt/project/完整 cwd/模型/权限/baseline；dispatch 前固定 `count=1 + invoking + uncertain`。
- 新 session 绑定增加真实 sentAt、精确 local project、完整 cwd、baseline 新身份和 transcript Prompt SHA；相对 cwd、旧 session 更新时间变化、无/多/错 Prompt 均拒绝。
- completed/failed/interrupted/cancelled/timeout 全部需要停止确认、无 active stream、绑定一致和无观察冲突。
- attempt 锁覆盖读状态到发送/绑定；记录 host/PID/进程启动身份/owner，活 worker 拒绝接管；明确死亡的旧锁归档后才可恢复。
- journal leaf/既有祖先 symlink 均拒绝；atomic write 使用同目录临时文件和 rename。
- 工具结果映射修正：`completed/done` 只是完成信号，不直接等于成功；shell `exit_code=0` 或明确业务 success 才成功，冲突结果保留 `outcome_conflict`。

实现与 canary 前置条件见 [P2 离线证据](../../../../general-e2e/evidence/qwenwork-macos-p2-offline-20260919/README.md)。

## 验证

| 层级 | 结果 |
| --- | --- |
| QwenWork Node | 25/25 PASS |
| QwenWork Python | 3/3 PASS |
| COMMON public regression | 55/55 PASS |
| 语法 / diff | PASS |
| live QwenWork | NOT RUN；未分配桌面时段 |

公共回归使用主工程既有 `.venv`；系统 Python 缺 `python-dotenv` 的一次环境失败没有计作代码失败，改用规定环境后 55/55 通过。

## 接收动作

| 接收方 | 要求 | 通过条件 |
| --- | --- | --- |
| COMMON | 发布固定 CB-B/trace-index v2/cleanup hook SHA 后，给出准确 general-contracts、collect-general-e2e、desktop-app-discovery 组件版本；本分支再同步 `components.json/components.mjs` | 不伪造 thread/turn/lifecycle；多 raw + binding evidence 可正式归档；unsupported cleanup 在正式冻结前被阻断 |
| COMMON | 为 execute-general-e2e 发行闭包独立装配 `playwright-core` 或等价 CDP 依赖 | 仓库外运行不依赖 Web Skill 或仓库偶然 node_modules |
| 控制任务 | 分配 QwenWork 桌面独占时段和全新 General canary | fresh probe 无活动会话；一个 attempt 一次发送；同 attempt 恢复 dispatch 总数仍为 1 |
| 本任务 | 固定依赖后先跑 `--validate-only`，再在时段内执行 canary | 模型/权限保持当前值；session/cwd/Prompt 精确绑定；可信终态或失败关闭 |

## 未声明范围

没有声明 QwenWork live UI、一次真机发送、当前 1.0.6 Token Profile、正式 collect、cleanup、评分/回传/报告、并发补位或仓库外发行通过。P2 保持未完成，直到上述 canary 和正式证据接口闭环。
