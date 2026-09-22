# General E2E 流程状态与离线回传

## 两级状态

`run_general_e2e.py` 不代替单阶段 Skill，而是锁定输入、阶段选择和已验证产物：

- batch 根目录必须含 prepare 生成的 `manifest.json`，允许 `prepare / import-return / report`。
- unit 根目录必须含 execution package 的 `manifest.json`，允许 `execute / collect-evidence / score / package`。
- 状态写入 `.general-e2e/run-general-e2e-state.json`。`init` 之后阶段选择、manifest 身份和 `--input` 内容不可漂移。
- 状态值固定为 `NOT_SELECTED / PENDING / RUNNING / NEEDS_HUMAN / NEEDS_ATTENTION / COMPLETED / FAILED`。

用以下命令查看恢复动作；它会重算 manifest、输入和已记录产物的哈希：

```bash
python scripts/run_general_e2e.py status --root /absolute/root
python scripts/run_general_e2e.py resume --root /absolute/root
```

`set-stage` 只允许进入运行、人工接管、需处理或失败状态，不能手工标记完成：

```bash
python scripts/run_general_e2e.py set-stage \
  --root /absolute/root --stage execute --status RUNNING
```

AstronStudio 执行阶段通过按 manifest 顺序提供全部终态 `automation-state.json` 收口；采集和报告阶段通过标准 receipt 收口，评分阶段通过标准 submission 收口：

```bash
python scripts/run_general_e2e.py record-execution \
  --root /absolute/unit-root \
  --state /absolute/unit-root/.general-e2e/execution/<task-id>/automation-state.json

python scripts/run_general_e2e.py record-receipt \
  --root /absolute/unit-root --stage collect-evidence \
  --receipt /absolute/unit-root/receipts/collect-evidence-receipt.json

python scripts/run_general_e2e.py record-submission \
  --root /absolute/unit-root \
  --submission /absolute/orchestration-root/submission.json
```

`record-execution` 校验 batch/unit/dataset/task/attempt 身份、终态 phase、业务终态、结束时间和最多一次 Prompt 发送；失败或取消也是可收集的执行终态，不等于能力零分。多题 unit 必须按 manifest 任务顺序重复提供 `--state`，不能遗漏或重复任务。

## 回传包

`package-return` 同时校验 execution manifest、collect receipt、submission 和 submission 引用的 score。资源字段缺失导致的合法 `partial` collect receipt 可以回传，但身份、范围、哈希和完整性仍须全部通过；报告端继续按字段披露覆盖率。ZIP 使用固定时间、权限、顺序和无压缩存储；相同冻结输入产生相同 package ID 和 archive SHA。包内含：

- `package-manifest.json`：身份、来源 SHA、成员类型/权限/SHA/大小。
- `receipts/package-receipt.json`：标准 `receipt-v1` package 回执。
- `unit/manifest.json`、`unit/receipts/`、`unit/evidence/`。
- `scoring/submission.json`、`scoring/execution-records/` 和 submission 引用的评分 attempt。

评分 attempt 中的 `runtime/` 是规则运行副本，不进入回传。ZIP 支持普通文件、目录和不越出包根的相对符号链接；常见凭据文件名、绝对链接、越界链接、设备文件及其他未知类型失败关闭。

## 导入、冲突和选择

管理员批次侧先初始化状态，再导入：

```bash
python scripts/run_general_e2e.py init \
  --scope batch --root /absolute/batch-root \
  --stage prepare,import-return,report

python scripts/run_general_e2e.py import-return \
  --batch-root /absolute/batch-root \
  --archive /absolute/return.zip \
  --receipt /absolute/package-receipt.json
```

导入器不使用 `extractall`，而是先验证完整成员集合、类型、路径、链接、SHA、package receipt、submission 及批次 unit scope，再写入暂存目录并原子发布。相同 archive SHA 再次导入返回 `idempotent=true`。

同一逻辑 unit 的新内容不会覆盖既有目录。它会形成新的 `returns/<unit-id>/<package-id>/`，导入索引把该 unit 标为冲突并清空选择，批次阶段进入 `NEEDS_ATTENTION`。审核两个 attempt 后显式选择：

```bash
python scripts/run_general_e2e.py select-import \
  --batch-root /absolute/batch-root \
  --unit-id astronstudio-macos \
  --package-id <full-package-id>
```

只有批次 manifest 中每个 unit 都有唯一显式选择时，`import-return` 才是 `COMPLETED`；report 必须消费选择结果，不能自行挑选最新目录。
