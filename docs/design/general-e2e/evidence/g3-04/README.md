# G3-04 Codex 语义评分实现证据

2026-09-18 在 macOS 开发机完成 `codex-agent-judge-v1` 的协议实现和 fixture 验证。`score-general-e2e` 升级为 `0.4.0/interface_only`，`orchestrate-general-e2e` 升级为 `0.3.0/interface_only`。

本项没有创建真实 Codex Judge task。O-01 的评分模型与推理强度尚未冻结，测试中的模型名、语义分和证据结论均为 fixture；它们证明契约、分页取证、失败关闭和合分代码，不证明裁判准确性或真实生产准入。Windows 真机同样为 NOT_RUN。

## 已实现边界

- 评分 attempt 冻结 `protocol / model / reasoning_effort / judge_attempt_id`，配置缺失、占位值和回传漂移失败关闭。
- 60 题 contract 全量核验：19 题 automated、35 题 hybrid、6 题 llm_judge；41 个语义任务共 106 个 criterion，key/weight 均可确定性解析，分值锚点均为 `0 / 0.25 / 0.5 / 0.75 / 1.0`。
- evidence index 覆盖任务、评分 contract、execution record、候选 manifest、候选文件、私有参考、规则组件/审计和逐个 transcript event；每个引用带可定位 path/event ID 和 SHA。
- `query-evidence` 支持 catalog、transcript 与 UTF-8 文件分页，按 event ID、call ID、路径和文本过滤，并把 query ID、范围、返回 evidence/event ID 与结果 digest 写入查询日志。
- judged criterion 必须引用由其 query ID 实际返回的 evidence ID，并声明已检查支持证据和反例。未发生类结论必须用无过滤分页覆盖完整 transcript；关键词无命中不算完整证明。
- 未判定 criterion 保持 `unresolved`；自动规则或语义评测异常生成 `valid=false / total_score=null`，不会补零。真实零分仍可生成有效 `0.0`。
- `finalize` 支持 automated、hybrid 和 llm_judge，生成标准 `score.json` 与不可覆盖审计；多文件终态发布失败会回滚已写文件，不保留正常部分写入。
- `verify-score` 校验 schema、来源 SHA、语义查询日志和审计锁，并从冻结规则/语义组件重算完整 `score.json`；仅同步改写结果哈希不能通过准入。
- 编排线程完成后进入 `SCORE_VERIFICATION_PENDING`；`record-score` 只有在冻结 score Skill 的 `verify-score` 通过后才记录结果并释放单槽。
- 规则、语义、合分和验证均在本机工作空间运行；审计固定 `docker_used=false`，没有 Docker 前提。

## 证据范围

| 检查 | 结论 | 证据边界 |
| --- | --- | --- |
| 60 题语义 rubric 解析 | PASS | dataset bundle 静态 contract；41 题、106 criterion |
| hybrid 正常合分 | PASS | fixture 规则分 0.8、语义分 0.8、总分 0.8；标准 score validator 通过 |
| automated 真实零分 | PASS | fixture 规则分 0.0，语义 not-required，总分保持有效 0.0 |
| llm_judge 未判定 | PASS | unresolved 形成 evaluation_error，total_score 为 null |
| 未知引用/未查引用/反例检查缺失 | PASS | 结构化失败审计，attempt 不生成有效 semantic component |
| 未发生类轨迹覆盖 | PASS | 过滤查询不能冒充完整覆盖；无过滤分页范围才可通过 |
| Judge/请求/证据漂移 | PASS | model 或 catalog digest 改变即失败关闭 |
| 终态重算 | PASS | 同时改写 `score.json` 与其审计哈希仍被 `SCORE_RECOMPUTE_MISMATCH` 拒绝 |
| 失败回传收口 | PASS | 非法语义引用产生失败审计，后续标准分保持 `valid=false / total_score=null` |
| 编排 score 准入 | PASS | 线程完成后先返回 VERIFY_SCORE；record-score 后才进入下一题 |
| 真实 Codex Judge task | NOT_RUN | O-01 未配置，不使用 fixture 冒充真机评分 |
| Windows 本机 | NOT_RUN | 仅有共享 Python/PowerShell 路径，尚无目标机证据 |

## 复核入口

- 实现：`tools/report/skills/general-e2e/score-general-e2e/scripts/score_general_e2e.py`
- 协议说明：`tools/report/skills/general-e2e/score-general-e2e/references/codex-agent-judge.md`
- 编排准入：`tools/report/skills/general-e2e/orchestrate-general-e2e/scripts/orchestrate_general_e2e.py`
- 聚焦测试：`tests/general_e2e/test_general_semantic_scoring.py`、`tests/general_e2e/test_general_scoring_orchestration.py`、`tests/general_e2e/test_local_scoring_runtime.py`

提交前门禁：General E2E 95/95、旧 `eval_e2e` 60/60、13 个 Skill `quick_validate.py`、layout（7 Skills/5 components/0 errors）、独立 General release build、release-root verify、suite verify 和脱仓 score Skill 新命令入口均 PASS。这些是当前 macOS 开发机的代码、fixture 和发行证据，不是真实 Judge 或 Windows 准入证据。

正式真实评分前必须先解决 O-01，并使用新的 scoring attempt；不能把本页 fixture 分数回填为生产结果。
