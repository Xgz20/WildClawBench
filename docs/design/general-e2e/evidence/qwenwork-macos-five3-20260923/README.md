# QwenWork macOS General 五题并发开发证据

日期：2026-09-23（Asia/Shanghai）。当前安装 QwenWorkCN 1.2.0、macOS x86_64，原生 Token/cache profile 未验证。本目录记录固定五题的开发批次，不能作为三路原生并发或 1.2.0 正式发行准入结论。旧 execution/scoring 包的 Harness 版本字段为 1.0.6，实际运行版本以当次 probe 为准；正式发行须用 1.2.0 重新准备。

- r13：`/Users/gzx/debug-workspace/e2e-evaluate/qwenwork-macos-general-20260922-five3-queue-r13` 为调试运行根。五题各发送一次，原 attempt 恢复后 5/5 completed；collector/finalizer 与 verify-only、5/5 valid score、return/import、10 Sheet 报告均通过。得分依次为 `0.55 / 1.0 / 1.0 / 0.9375 / 1.0`，均分 `0.8975`，评测异常 0。正式回传 package ID `49cef9fead07b2b4726e17fd75ed225d0fc154991b79cf49b7e28d6956abc363`，archive SHA-256 `75c10b9759d8b4d40b857cc84edd4e22b02f24f061deacc563919a82141bccbd`。三个语义评分原 thread 的记录区间在 13:48:05–13:48:48 UTC 同时重叠；两个 automated 任务未占语义槽。
- r18：`/Users/gzx/debug-workspace/e2e-evaluate/qwenwork-macos-general-20260923-five3-queue-r18` 为并发调试根。五题各发送一次、原 attempt 恢复后 5/5 completed；队列 `run_slots=3`、发送占槽峰值 3、动态补位 2 次。原生 segment 的五个唯一主 turn 均有 `turn.started`/`turn.finished` 时间戳，逐区间重算的原生峰值为 **2**，所以不能把占槽峰值 3 写成原生三路通过。原始队列 receipt 对 native timing 仍是 `0/5` coverage；原生重叠结论以这些 segment 的逐行时间戳为依据，后续要接入可复算的正式回执。
- r15/r16：临时 conversation/sub-chat/project/cwd 绑定让前两题进入后台槽，第三题在高频 WAL 写入时因 `QWENWORK_DB_SNAPSHOT_SOURCE_CHANGED` 停止，未发送。随后的 SQLite 在线备份替换了放宽文件漂移门禁的开发尝试；真实 WAL 写者保持连接的 focused test 验证已提交的行可被一致读取。r18 在原生终态观察短暂冲突时保留 `NEEDS_ATTENTION`，同 attempt resume 后收口，未重发。

当前代码已增加 `--preprepare-projects`：发送前逐题创建并验证项目、草稿及冻结 journal，再单槽连续发送，目标是让固定五题的三个主 turn 真正重叠。其离线回归通过，**真机五题三路及动态补位仍需在当前源码的独立发行包上重验**。后续还需补发送临界中断、客户端重启/重连、未知授权/追问安全暂停、残留进程与无关进程保护；Codex Desktop 重启暂缓。
