# General E2E API Judge 编排

## 初始化

`report-config.json` 的 `judge.protocol` 必须显式设为 `api-judge-v1`，并冻结 model 和 reasoning effort。API runtime 使用单独的私有 JSON 文件传入：

```bash
python <skill-dir>/scripts/orchestrate_general_e2e.py init \
  --unit-root /absolute/execution-unit \
  --scoring-package /absolute/unit-scoring.zip \
  --report-config /absolute/report-config.json \
  --score-skill-dir /absolute/score-general-e2e \
  --api-runtime-config /private/api-runtime.json \
  --output-root /absolute/private-orchestrations \
  --orchestration-id ORCHESTRATION_ID \
  --score-slots 3
```

初始化把 runtime 的 provider、endpoint 身份、预算、timeout、重试和凭据环境变量名冻结进每题 attempt 与队列；不复制凭据值。语义评分默认 3 槽、可配置 1–8。API 任务没有 Codex Prompt、project 或 thread，活动槽位的动作固定为 `RUN_API_SCORE`。

## 执行和恢复

只执行 `status` 或 `resume` 返回的当前动作：

```bash
python <skill-dir>/scripts/orchestrate_general_e2e.py run-api-score \
  --orchestration-root /absolute/orchestration \
  --task-id TASK_ID \
  --runtime-python /absolute/general-e2e-runtime/bin/python
```

纯 `llm_judge` 任务可省略 `--runtime-python`；`hybrid` 任务必须提供规则运行时。控制器在外部调用前先持久化 `API_RUNNING`。进程中断后重新执行 `resume` 并继续相同命令；score Skill 会复用已完成终态，或在请求结果不确定时拒绝重复调用。

命令完成后，控制器仍独立运行 `verify-score` 并锁定 score SHA。有效能力分和合法的 `evaluation_error / total_score=null` 都会进入 `SCORE_RECORDED` 并释放当前槽位，随后按冻结顺序补位。API transport、结构校验或凭据缺失不会创建 Codex task 兜底；如需更换后端，必须新建评分配置和评分 attempt。
