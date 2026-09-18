# Submission 与重评分编排

## 生成 submission

只有冻结范围中的所有任务进入终态后才运行：

```bash
python scripts/orchestrate_general_e2e.py build-submission \
  --orchestration-root <orchestration-root>
```

编排器按冻结顺序再次验证每个 `score.json`：有效总分记为 `valid`，合法的 `total_score=null` 记为 `evaluation_error`，执行不可信、证据不完整或评分线程失败记为 `unscored`。后两类不得补零。`submission.json` 枚举全部冻结任务，校验身份、路径和 SHA；重复调用在内容未漂移时幂等。

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
