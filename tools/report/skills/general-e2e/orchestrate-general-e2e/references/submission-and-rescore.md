# Submission 与重评分编排

## 生成 submission

只有冻结范围中的所有任务进入终态后才运行：

```bash
python scripts/orchestrate_general_e2e.py build-submission \
  --orchestration-root <orchestration-root>
```

编排器按冻结顺序再次验证每个 `score.json`：有效总分记为 `valid`，合法的 `total_score=null` 记为 `evaluation_error`，执行不可信、证据不完整或评分线程失败记为 `unscored`。后两类不得补零。`submission.json` 枚举全部冻结任务，校验身份、路径和 SHA；重复调用在内容未漂移时幂等。

若用户已显式授权迟到完成恢复，而且 `record-score --allow-late-completion` 在旧 submission 生成后写入了合法评分，常规 `status` 和 `build-submission` 会继续以 `SUBMISSION_CONTENT_MISMATCH` 失败关闭。此时只能运行：

```bash
python scripts/orchestrate_general_e2e.py build-submission \
  --orchestration-root <orchestration-root> \
  --replace-after-late-completion
```

该入口只接受能从当前 state 严格复算为恢复前 `unscored` 内容的旧 submission，并要求迟到事件、线程 deadline/终态和锁定 score 完全一致。旧文件归档为 `submission-history/<原 sha256>.json`，新 submission 原子替换到原路径；state 的 `submission_replacements` 记录恢复题目、新旧创建时间、路径和 SHA。手工修改、删题、非迟到评分变化或审计归档漂移仍失败关闭。

## 创建独立重评分编排

源 orchestration 必须已终态且锁定 `submission.json`。只能选择具有合法终态 `score.json` 的任务：

```bash
python scripts/orchestrate_general_e2e.py init-rescore \
  --source-orchestration-root <source-root> \
  --report-config <new-report-config.json> \
  --score-skill-dir <score-general-e2e> \
  --output-root <output-root> \
  --orchestration-id <new-id> \
  --task-id <task-id>
```

新 report config 显式指定 Judge protocol、model 和 reasoning effort；API 后端还需 `--api-runtime-config`。新编排冻结源 state、submission、attempt manifest 和 score 哈希，使用新的 attempt ID 和独立路径。源编排、分数与 submission 不会被覆盖；目标已存在或源未锁定时失败关闭。
