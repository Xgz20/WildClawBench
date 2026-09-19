# MAC-DOUBAOWORK-WEB-003：等价绑定与候选清理加固接收

| 字段 | 值 |
| --- | --- |
| 交接 ID / 日期 | `MAC-DOUBAOWORK-WEB-003` / 2026-09-19 |
| 来源任务 / worktree | `MAC-DOUBAOWORK-WEB` / `.agents/doubaowork-macos-web-e2e` |
| 来源提交 | `40c2f71ad06903967344fe9d4ef951fc7c57ecd0`、`2e21a54d6fa4a8d4c2d4005a2d31df77f927677d`、`5d7b6d911d4619fa0b388d551fbe17104b5562db` |
| 集成提交 | `11d0182`、`b57b03e`、`0424174`（集成分支 `feat/e2e-harness-contract`） |
| 集成状态 | ADOPTED；仅离线代码与 fixture，未操作 DoubaoWork 客户端或历史 canary |

## 本轮内容

- 候选进程清理冻结 workspace canonical path/device/inode，按 PID 启动身份、PGID、可执行文件和 cwd/父链做 fail-closed 归属核验；已跟踪目标在父进程退出、子进程重挂或同身份 cwd 变化时继续收口。PID 复用、workspace 实体变化、归属缺失、残留和安静窗口不足均保持失败关闭。
- `readMacProcessInventory` 的 `ps → lsof → ps` 夹取不再因 `parent_pid` 重挂变化丢弃同一 PID；新增可变进程表 fixture。
- UI 等价绑定门禁在每次观察核验 conversation → project → 完整 tooltip workspace，并用规范化 Prompt 的 SHA-256/字节数回读绑定 conversation 的最新 user message；正向完成标识仍只属于 UI 等价候选。
- 恢复路径在 Prompt 回读通过但状态尚未确认时补写 `session.prompt_readback`，避免崩溃恢复留下未确认状态。

## 验证与边界

集成树中 DoubaoWork 专属 `npm test` 为 54/54，包含真实自建临时父子进程 fixture、PID 复用、父进程重挂、cwd 变化、workspace inode 变化和 Prompt 恢复反例；相关 MJS `node --check` 与 `git diff --check` 通过。

本交接没有把 cleanup 接入 Driver 的公共 finalizer，也没有生成正式 `execution_record`/receipt、可信 native terminal/cwd、评分或报告。`validateObservationBinding` 的 `verified` 只表示 UI 等价证据完整，不表示 native/trusted 终态；现有历史 canary 的残留进程未被触碰。

## 后续门禁

先完成 Web 公共 finalizer/receipt、可信 native terminal/cwd 和 cleanup hook 接线；再次申请真机 slot 前须重新生成 release、复跑 prepare/batch verify，并以全新 attempt 进行验证，不重发历史 canary。
