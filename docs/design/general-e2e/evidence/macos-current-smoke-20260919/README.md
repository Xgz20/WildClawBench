# AstronStudio macOS 当前版本双题生产准入 smoke 证据

## 结论

2026-09-19，在源码 revision `457e35560ea5cd090db1ce8b68c747de95ae3622` 上完成 AstronStudio macOS 当前版本双题真实闭环。文件型自动规则任务和纯回复语义任务均只发送一次 Prompt，取得唯一原生会话身份和 `completed` 终态；原始 rollout、标准 transcript、资源指标、候选冻结、规则评分、Codex 语义评分、submission、回传导入及 JSON/Markdown/Excel 报告全部有效。

本轮结论是：当前 macOS x86_64、AStudio 3.3.1、Spark X2.5/High/完全访问和本轮 General E2E Skill 组合达到**受控生产可用**。生产使用必须保留版本与哈希校验、执行前只读 probe、单次 Prompt、冻结候选、独立评分 attempt 和异常不补零等门禁。

这不是新的五题准入，也不替代 [G4-03 五题三槽证据](../g4-03/README.md)。G4-03 证明三种评分类型、五题与三槽编排；本轮在共享桌面应用发现、当前评分 Prompt/Skill 和最新源码上回归一题 `automated` 与一题 `llm_judge`。两轮证据合并支持当前版本的受控生产结论，但不外推到 Apple Silicon、Windows、60 题全量、未知交互或 timeout 故障注入。

## 工作目录与版本

- 调试与真机运行根目录：`/Users/gzx/debug-workspace/e2e-evaluate/general-e2e/macos-current-smoke-20260919-141301`。
- 正式生产发行目录：`/Users/gzx/Project/GitHub/xgz/ai/evaluate/WildClawBench/WildClawBench/report-workspace/general-e2e/releases/general-macos-production-20260919-141301`。
- batch：`general-macos-current-smoke-20260919-141301`；unit：`astronstudio-macos-x86-64`。
- 被测环境：macOS `26.6.2/x86_64`、AStudio `3.3.1`、`/Applications/AStudio.app`、Spark X2.5、High、完全访问。
- 共享发现组件：`desktop-app-discovery 1.1.0`。
- Skill：prepare `0.2.0`、execute `0.6.0`、collect `0.4.0`、orchestrate `0.8.0`、score `0.8.0`、report `0.2.1`、run `0.3.0`，均为 `operational`。

调试制品没有写入仓库 `report-workspace`；只有重建并验包的正式发行进入生产目录。

## 探针与执行

首次只读 probe 因 AStudio 未开启 CDP 而按预期失败关闭，且 `prompt_send_attempted=false`。随后使用共享动态发现脚本安全重启 AStudio 并开启 loopback CDP 9240；重启后的 probe 为 `PASS`，端口归属当前主进程，状态库、Node、Python、SQLite 和 Codex 条件可用，活动或待处理会话为 0。

执行 queue 为 `macos-current-two-task-smoke`，`ui_slots=1`、`run_slots=3`，终态 `COMPLETED`；完整性检查 `all_tasks_terminal`、`attempts_explicit_and_unique`、`no_duplicate_dispatch` 和 `valid` 均为 true。

| task ID | 类型 | execution attempt | Prompt 次数 | 终态 | 分数 |
| --- | --- | --- | ---: | --- | ---: |
| `02_Code_Intelligence_task_001_temperature_cli_fix` | automated | `6cd1ec82-03ea-4dfb-ac92-9f6f52c06212` | 1 | completed | 1.0000 |
| `03_Social_Interaction_task_003_colleague_leave_reply` | llm_judge | `5a3ca9f8-8470-4fb6-8b08-0de8312b32fc` | 1 | completed | 0.8250 |

两题的 thread、turn、provider session 和 cwd 均唯一。collect receipt 状态为 `completed`，范围、身份和产物哈希全部通过；receipt SHA 为 `6f1902bd7733d3917fb937e7803b7cd162fccf642e88d673a74dfe6fad4cb060`。

## Rollout 与资源指标

| task ID | 原生事件 | 标准事件 | 输入/输出/总 Token | 缓存读取 | 推理输出 | 模型请求 | 工具调用 | 流程耗时 | Agent 耗时 |
| --- | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `02_Code_Intelligence_task_001_temperature_cli_fix` | 298 | 24 | 173577 / 1931 / 175508 | 150336 | 458 | 7 | 4 | 89.070s | 73.912s |
| `03_Social_Interaction_task_003_colleague_leave_reply` | 1563 | 5 | 22941 / 3251 / 26192 | 22528 | 3178 | 1 | 0 | 82.841s | 73.660s |

汇总输入/输出/总 Token 为 `196518 / 5182 / 201700`，缓存读取 `172864`、推理输出 `3636`、模型请求 `8`、工具调用 `4`；任务流程耗时之和 `171.911s`、Agent 耗时 `147.572s`、批次壁钟 `94.203s`。cache creation 和 HTTP attempt 在原生来源中不可见，保持 `null/unavailable`，没有补零。

原始 rollout 位于各任务证据目录的 `trace/raw/astronstudio-provider-events.jsonl`，标准轨迹位于 `trace/transcript.jsonl`；冻结候选与原 Workspace 的哈希重验均通过。

## 评分、证据和回传

评分 orchestration 为 `macos-current-gpt6-astra-high-20260919-141301`，固定 `gpt-6-astra/high` 和 `general-e2e-codex-scoring-prompt/v4`，`score_slots=3`，终态 `COMPLETED`。自动规则题在调试目录内的独立 Python 3.11 受管运行时执行，未使用 Docker，四个规则检查点均记录中文得分理由及规则、候选、轨迹和 Worker 原始值证据。

语义题使用独立 Codex 项目 `884913a4-44e7-49b9-b789-65a7cc28e0b3` 和线程 `01a0b87b-5a74-7e10-ba06-5e5efbc1eece`。四项 Rubric 得分为 `0.75 / 0.75 / 1.0 / 0.75`；每项都记录中文理由、支持证据和反例检查，`verify-score` 通过。submission SHA 为 `0a2066a3f134b3d8876179ace914a8d616681c34b30b5d41be36dac522cae116`，两题均为有效分，`evaluation_error=0`、`unscored=0`、有效均分 `0.9125`。

return package ID 为 `f2452af6329073c77050ba8c59e22894f3c9ab2a29d4847d8c7870bcc4f91535`，ZIP SHA 为 `c05252a5beb471c8ac99d8aceaab32bf8a32d139ee73635f5b2cb69bc93f9137`；导入无冲突并完成唯一选择。

## 报告与生产发行

报告 JSON、Markdown、Excel SHA 分别为：

- `50f32cb46378019034a4374a3f5ed49da04b7890fac0e70356116b47d3bae856`
- `1b637ef31df80104e0829378ed9f6434731cae61300849bdd53956ab92a08b58`
- `c663cb618b097c0fac96fbc6b8d67e65e34ed2059c261b0de7b1b12009c7c4ae`

Excel 含“总览”“分类与难度”“用例明细”“资源覆盖与异常”四个 Sheet。关键范围检查通过、公式错误为 0；2026-09-19 对四张 PNG 预览逐张检查，未发现乱码、空白 Sheet、公式错误提示或内容溢出。“用例明细”按字段数量横向展开，列头和两条数据完整。

正式发行 ID 为 `general-macos-production-20260919-141301`，见[生产发行清单](../../../../../report-workspace/general-e2e/releases/general-macos-production-20260919-141301/general-e2e-release-manifest.json)：

- source revision：`457e35560ea5cd090db1ce8b68c747de95ae3622`
- suite SHA：`64208e9828cf32457938abb616bd522a914aaeda3828735d9169236f575059ec`
- catalog SHA：`757ac5e7f1132a0dd8ee381d63e2edd8e35858d03188783788437ddc137e4495`
- catalog digest：`2b1bad1ab1f5853d1470a54e8278be5dc0bd02cdf820647268d765e714e2490b`

release-root、suite 和 7 个单 Skill ZIP 均通过 verifier。正式生产包与 smoke 包的 7 个 Skill 版本、内容 SHA 和 ZIP SHA 一致；release ID 导致 catalog 与 suite SHA 不同，这是预期身份差异。

## 支持边界与下一步

当前允许声明“macOS x86_64 当前版本受控生产可用”，不允许声明“全面生产就绪”或“无人值守大规模准入”。以下项目仍未完成：

- Apple Silicon 真机验证。
- 固定 60 题全量运行与报告分母验收。
- 未知授权/用户问题和 timeout 的完整故障注入。
- 语义裁判人工校准与重复稳定性对照。
- Windows 原生 launcher/probe、执行、评分、回传和恢复。

下一项保持为 G5-01：在 Windows 真机验证共享应用发现、原生 launcher 和只读 probe，不能继承本轮 macOS PASS。
