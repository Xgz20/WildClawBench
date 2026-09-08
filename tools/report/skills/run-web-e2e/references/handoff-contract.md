# Web E2E 离线交接契约

## 文件

每个完成评分的 Harness（模型）单元生成两个同级文件：

- `<batch_id>__<harness>__return.zip`：包含一个顶层 Harness 根目录，目录中恰好有一个根级 `submission.json`。
- `<batch_id>__<harness>__return-receipt.json`：位于 ZIP 外，避免循环哈希。

回执 schema 为 `wildclawbench.web-e2e-return-receipt/v1`，至少包含：ZIP 文件名、SHA-256 和大小，以及 submission 中的 `batch_id`、`source_revision`、`metric_profile`、`unit`、有序 `task_ids`。

管理员导入后在 `<batch-root>/.run-web-e2e/imports/<harness>.json` 保存 schema 为 `wildclawbench.web-e2e-import-receipt/v1` 的导入记录。真正供报告读取的目录是 `<batch-root>/returns/<harness>/`。

## 安全和一致性门禁

导出和导入都必须失败关闭：

1. `manifest.json`、`submission.json`、回执和批次 manifest 的身份必须一致。
2. task IDs 必须有序且完整，不能缺题、重复或重排。
3. ZIP 条目必须是相对 POSIX 路径，不能包含 `..`、绝对路径、反斜杠或符号链接。
4. ZIP 内必须只有一个顶层根目录和一个根级 submission；不能从深层搜索后猜测目标。
5. 导出目录不能包含 `.git`、`node_modules`、`.cache`、`.vite`、评分运行时副本或常见密钥文件。
6. 导入先解压到目标文件系统上的临时目录，校验成功后再用原子重命名发布。
7. 目标已存在时，只接受 ZIP SHA 与既有导入回执完全一致的幂等重试；其他情况拒绝覆盖。

## 候选不可变性

交接逻辑只读取 Harness 根目录并创建新的 ZIP、回执和管理员导入副本，不写 execution/score 的 `workspace/`。即使发现哈希漂移，也只能返回结构化错误，不能重算冻结哈希或修改候选来适配评分结果。
