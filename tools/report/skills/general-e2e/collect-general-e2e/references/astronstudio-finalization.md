# AstronStudio 正式收口

## 前置条件

正式收口只接受 `execute-general-e2e` 生成的终态 `automation-state.json`，并重新校验 execution package manifest、dataset digest、task/attempt identity、Prompt SHA、发送次数、thread/turn/provider session/cwd 和终态。`completed` 必须同时提供已校验的 trace index 与 resource metrics；`timeout`、`candidate_error`、`infrastructure_error` 或 `cancelled` 只归档实际取得的证据，不补造缺失内容。`timeout/cancelled` 还必须满足 `cancellation_confirmed=true`。

当前正式进程收口只支持 macOS。Windows 和其他平台会返回不支持，不能用空进程列表伪装成功。

## 任务进程边界

收口器通过两类精确 seed 识别候选 Workspace 的任务进程：

- 命令行包含有路径边界的 Workspace 绝对路径；
- `lsof` 报告 cwd 位于 Workspace 内。

命中的 seed 后代也纳入收口。collector 本身、父进程和系统根进程被排除。每次发信号前重新核验 PID、进程启动时间和命令行 SHA，避免 PID 复用。先发 `SIGTERM`，宽限后仍为同一进程才发 `SIGKILL`；安静窗口中出现迟到进程时再次精确收口。只有目标进程为零且完整达到安静窗口才继续冻结。

## Workspace 静默和目录策略

进程收口后先计算源 Workspace 快照，等待默认 5 秒，再次计算；SHA 不一致即以 `WORKSPACE_NOT_STABLE` 失败。复制到 staging 后还会同时比较：

1. 静默前和静默后源 Workspace；
2. 静默后源 Workspace 和冻结副本；
3. 冻结完成后的源 Workspace 与静默快照。

三者必须相同。默认策略为 exact-all，保留所有普通文件、目录、权限和根目录内相对 symlink，不沿用 Web E2E 对 `.git` 或 `node_modules` 的过滤。绝对 symlink、越界相对 symlink和特殊文件失败关闭。

如果任务契约明确允许运行时目录，可通过 `--candidate-policy` 传入：

```json
{
  "schema_version": "wildclawbench.general-e2e-candidate-policy/v1",
  "ignored_directories": [
    {"name": "cache-dir", "reason": "评分不读取且由运行时重建"}
  ],
  "forbidden_directories": [
    {"name": "secret-dir", "reason": "不得进入候选和评分包"}
  ]
}
```

名称只允许单个 basename，同一名称不能同时 ignored 和 forbidden，reason 不能为空。

## 发布与不可变校验

正式 evidence 先在同一父目录 staging，完成全部复制、哈希和清单后再原子 rename。收口开始前检查目标 evidence、unit receipt 和同题其他 attempt；任一已存在即失败，不覆盖历史结果。receipt 使用同目录临时文件和原子硬链接发布，同样不会替换已有文件。

`--verify-only` 会执行以下检查：

- receipt、evidence manifest、execution record 和 candidate artifact 身份一致；
- completed receipt 中每个 task 都为 completed；
- manifest 和 receipt 的 artifact 范围与实际目录严格相等，且每项 size/SHA 与磁盘一致；
- execution record 中 stable candidate 的 path/SHA/frozen_at 完整，候选 entries 的类型、权限、链接目标和内容与冻结声明一致；
- 冻结候选和原始执行 Workspace 按同一目录策略重算后均无漂移。

验证失败时不得修补原有正式产物，也不得进入评分；应保留失败证据并以新的 attempt 重新执行。

## 多题与多 attempt 边界

unit receipt 只有在 manifest 的所有 task 都已各自完成正式收口时生成。当前 `0.4.0` 要求每个 task 恰好一个正式 attempt；多 attempt 的选择、废弃和优胜规则属于后续编排阶段，不在 collect 内隐式决定。
