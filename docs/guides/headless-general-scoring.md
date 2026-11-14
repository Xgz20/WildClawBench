# General E2E 无头评分

执行与评分分开绑定。`headless-score` 仅消费已有、已封存且通过 execution-ready 校验的 General 执行结果，不调用被测 Harness 或 AgentCube，不修改执行 manifest、原始产物或旧评分。

评分上下文由原批次冻结的 Skill、scoring ZIP、原始/标准轨迹、原生终稿和候选工作区组成。每题独立私有 attempt，GT 在执行结束后才进入评分副本。规则仍由原 score Skill 的 Python 3.11 受管 Worker 执行；语义部分通过 Codex CLI 或 DeepSeek Harness CLI 的文件、终端工具完成证据分页查询和结构化判定。两者复用冻结的 `codex-agent-judge-v1` 证据协议，实际 Harness、CLI 版本、镜像、模型与推理强度在外层 job 单独记录；不冒充对方客户端，不切换为直接 API Judge。

## 运行时

`tools/e2e-build/build_headless_scorer.py` 构建独立评分镜像，Codex/DSH 版本与现有 CLI 镜像定义对齐。可传 `--eval-base-image` 复用现有评测底座；默认 Python 官方多架构底座适用于 ARM64 公司 Mac。生成的 Skill 自包含、依赖按 SHA 锁定，bootstrap 必须通过 Chromium 实际启动自检。既有 CLI 镜像标签不覆盖。

```bash
python tools/e2e-build/build_headless_scorer.py \
  --context /absolute/tool/scoring-image-build \
  --tag astudio-e2e-scorer:release-id \
  --docker-context colima
```

必要的代理仅通过本次构建参数注入。API Key 不进入构建上下文或镜像。

## 单批次评分

非敏感配置示例：

```json
{"harness":"codex","model":"requested-model","reasoning_effort":"high","base_url":"https://gateway.example/v1","image":"astudio-e2e-scorer:release-id","docker_context":"colima","concurrency":3,"timeout_seconds":3600}
```

DSH 使用 `harness=deepseek-harness`，优先 OpenAI Chat 端点。凭据只从 `E2E_SCORER_API_KEY` 注入，不接受配置 JSON 中的真实 Key。

```bash
python eval/run_e2e.py --api-version 1 headless-score \
  --workspace-root /absolute/evaluation/tenant-1 \
  --batch-id original-batch-id --scorer-config /absolute/private/profile.json \
  --output-root /absolute/evaluation/scoring-operation
```

- 评分并发独立于执行并发，范围 1–8；控制超时不进入能力 Rubric。
- 同一路径恢复复用原请求、Docker 容器名和私有 attempt。配置或来源发生变化时拒绝继续；独立重评使用新的 operation/output-root，保留旧产物。
- 仅按任务容器 ID 和所有权标签清理，共享同一镜像的其他运行不受影响。
- 评分 Agent 退出不能代替完成证明。必须有标准 score.json，经冻结 Skill `verify-score`、输入 SHA 及另一个无凭据、无网络容器的独立复验通过后接纳。
- 合法零分保持 0；评测异常和未评分保持 null。原执行未达到评分准入或运行时不支持的专用规则保留明确错误，不补零、不改变规则或切模型。
- 需要独立规则语义复核、原生 Office 特殊环境等任务，必须满足原 Skill 的额外门禁；本入口不绕过它们。Web 使用独立契约，后续接入。

Codex 调用遵循 [OpenAI 官方非交互执行](https://developers.openai.com/codex/noninteractive)；DSH 使用其[官方 headless profile](https://github.com/deepseek-ai/deepseek-harness/tree/master/packages/bundle/headless)。以实际镜像内版本和帮助输出作为发行依据。
