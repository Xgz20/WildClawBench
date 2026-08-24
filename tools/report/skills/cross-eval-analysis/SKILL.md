---
name: cross-eval-analysis
description: 对 WildClawBench 中不同模型同一 Harness，或同一模型不同 Harness 做控制变量下的逐用例差异分析；读取 score.json、任务定义、execution_status、chat_openclaw.jsonl 以及 AstronCode 的 agent_interaction.jsonl，输出有完整用例 ID、用例名称、题目考察点、分差机制和原始证据的结构化分析与 Markdown 报告。用于回答“哪个模型/Harness在哪些任务上更好、差异为什么出现、给出典型案例”，不替代低分任务根因分析。
---

# WildClawBench 跨单元分析 Skill

## 适用范围

本 Skill 专门分析同一评测集中的**控制变量对比**：

- 固定 Harness，比较多个模型：`--axis model --fixed-harness <harness> --models <model...>`；
- 固定模型，比较多个 Harness：`--axis harness --fixed-model <model> --harnesses <harness...>`。

它回答的是“同一个任务换模型或 Harness 后，分数和执行行为哪里发生变化”。它不把单个单元的低分原因直接搬过来，也不把简单的平均分排名当成根因结论。单元必须来自同一个 round；跨 round 请使用现有跨轮比较脚本，避免评测集和配置差异混入结论。

## 输入与产物

必需输入：

- 一个 round 结果根目录；
- 对比轴、固定变量、参评对象列表和目标对象；
- 任务定义目录（推荐显式传入）；
- `tools/report/data/entities.yaml` 展示名注册表。

脚本先生成逐用例 manifest，再由 Workflow 结合原始轨迹生成结构化分析，最后校验并渲染：

```text
cross_eval_<axis>_manifest.json       # 确定性配对数据和原始文件路径
cross_eval_<axis>_analysis.json       # Workflow 产出的事实与证据分析
cross_eval_<axis>_analysis.quality.json
cross_eval_<axis>_report.md            # 可导入飞书的 Markdown
```

`manifest` 的比较范围默认是所有参评单元的**共同有效任务交集**。无有效分数、影响结果有效性的执行异常、被重跑替换的 run 不进入分差；这些排除信息保留在 manifest 的 `issues` 和每个任务的 `records` 中，不能默默当成 0 分。若异常分析明确标记结果为 `valid_capability_outcome`，例如模型在任务时限内未完成而被超时截断，则保留其分数参与能力比较，同时在 `issues` 中标记为 `CAPABILITY_TIMEOUT_INCLUDED`。

## 标准流程

### 1. 先做有效性检查

生成比较前先使用 `validate-eval-results` 检查结果范围、执行状态和跨单元可比性。若存在影响分数的 L3/L4 问题，先在报告中单列，不把它们写成模型或 Harness 能力差异。`cross-eval-analysis` 只比较共同有效任务，不负责替代评测结果有效性门禁。

### 2. 生成逐用例 manifest

固定 Harness 看模型：

```bash
uv run python tools/report/skills/cross-eval-analysis/scripts/build_cross_eval_manifest.py \
  --result-root <round-root> \
  --axis model \
  --fixed-harness <harness-id> \
  --models <target-model> <reference-model-1> <reference-model-2> \
  --target-model <target-model> \
  --tasks-dir <repo>/tasks \
  --entities tools/report/data/entities.yaml \
  --output <workspace>/cross_eval_model_manifest.json
```

固定模型看 Harness：

```bash
uv run python tools/report/skills/cross-eval-analysis/scripts/build_cross_eval_manifest.py \
  --result-root <round-root> \
  --axis harness \
  --fixed-model <model-id> \
  --harnesses <target-harness> <reference-harness-1> <reference-harness-2> \
  --target-harness <target-harness> \
  --tasks-dir <repo>/tasks \
  --entities tools/report/data/entities.yaml \
  --output <workspace>/cross_eval_harness_manifest.json
```

只分析指定任务时重复传 `--task-id`，或传 `--task-file`。除非用户明确要求，否则不要用非交集范围做能力排名。manifest 中每个任务必须保留完整 `task_id`，不得截断为任务序号或套件简称。

### 3. 逐用例取证

对每个任务先读取 manifest 中的任务定义、各单元 `score.json` 和 `execution_status.json`，再读取两侧对应 run 的完整轨迹：

- `chat_openclaw.jsonl` 或 `chat.jsonl`：模型实际输出、工具调用、工具返回和最终交付；
- AstronCode 存在 `agent_interaction.jsonl` 时：核对模型请求体、响应体、模型可见工具清单、实际 tool call 和协议错误；
- `agent.log`、判分代码和产物路径：只作为补充或判定检查点的证据。

分差分析必须先建立“同一任务、同一检查点、两侧实际行为”的对应关系，再写结论。已有 `low-score-analysis` JSON 可以作为线索，但不能替代本次跨单元对两侧原始轨迹的核对。

### 4. 生成结构化分析

使用 `references/workflow_template.js`。Workflow 输出必须符合 `references/output_schema.md`，重点包括：

- 总结：先说总体趋势，再说差异集中在哪些任务或能力，不逐项堆分数；
- 每个目标/参照配对：目标侧强项、弱项、共同表现和差异机制；
- 典型案例：至少包含完整用例 ID、用例名称、题目简述/考察点、两侧得分、问题点和原始证据；
- 每条发现和每个案例都带 `evidence_refs`，至少写 `source`、`locator`、`excerpt`；
- 证据不足时写 `unconfirmed`，不能把“分数更低”直接写成“某侧导致”。
- 正文对异常和不可比结果只作一句提示；详细排除口径、均分变化和逐项证据写入 `comparability_analysis`、`unconfirmed_items`，由渲染器放到“附录：异常与不可比结果”。

### 5. 校验与渲染

```bash
uv run python tools/report/skills/cross-eval-analysis/scripts/validate_cross_eval.py \
  --manifest <cross_eval_manifest.json> \
  --analysis <cross_eval_analysis.json> \
  --output <cross_eval_analysis.quality.json>

uv run python tools/report/skills/cross-eval-analysis/scripts/render_cross_eval_report.py \
  --manifest <cross_eval_manifest.json> \
  --analysis <cross_eval_analysis.json> \
  --output <cross_eval_report.md>
```

`FAIL` 禁止渲染正式报告；`REVIEW` 可以作为内部分析，但必须在报告中保留未闭环项。渲染脚本只接受结构化分析，不接受手工拼接的分数表。

## 对比口径

- **模型对比**：Harness 固定，目标模型与参照模型使用共同任务逐题对齐；不能把不同 Harness 的结果混进来。
- **Harness 对比**：模型固定，目标 Harness 与参照 Harness 使用共同任务逐题对齐；不能把不同模型的结果混进来。
- **多 run**：同一单元同一任务的有效 run 取算术平均，并在 manifest 中保留 run 数和路径；若两侧 run 数明显不同，要在结论中提示稳定性限制。
- **强弱判断**：先看目标与各参照的逐任务分差，再看差异覆盖率和任务类型；总均分只作背景，不作为唯一依据。
- **共同低分**：多个单元在同一任务都低分，优先写“共同困难/可能存在任务或环境因素”，不能用来证明目标模型或 Harness 的特有短板。
- **只在一侧缺失**：没有共同有效结果的任务不进入主分差；如必须说明，列为“不可比/覆盖缺口”，不能填 0 分。
- **L3/L4**：外部模型服务、网络、流控等 L3，以及 Runner、容器、Workspace、Grader 等 L4，不能直接归入模型或 Harness 优劣；影响结果有效性时排除并单列。任务时限内模型未完成，若异常报告确认是 `valid_capability_outcome`，按模型/Harness 能力结果保留，不归为 L3。
- **排除可审计**：正文中的排除后均分必须能由附录复算；附录逐步列出排除项、剩余样本数、两侧均分和分差，每个异常都要有完整任务 ID、明确处理结论和原始证据。
- **unsupported call**：只有 AstronCode 原始请求/响应、可见工具清单和 Harness 调度证据齐全时，才讨论模型侧或 Harness 侧责任；缺材料就标 `unconfirmed`。

## 文风与证据红线

- 先摆事实，再给判断；避免“明显、显著领先、能力很差、模型不行”等没有范围和证据的评价。
- 用“在 X 类任务中差异集中”“与参照模型接近”“在 Y 类任务上仍有差距”替代绝对贬低。
- 每个典型案例必须写完整任务 ID，不允许写成 `task_007`、`Safety 任务` 等无法反查的简称。
- 证据定位必须可复核：写文件名、JSON 字段、JSONL 行号或命令/产物路径；原始片段只摘与结论直接相关的内容，并注意脱敏。
- 结论只能说明观察到的差异及证据支持的机制；没有排除主要替代解释时使用 `probable` 或 `unconfirmed`。
- 典型案例不使用低分任务报告的固定模板；这里核心是“两侧同题行为差异”，不是单侧失分根因统计。
- `task_name` 沿用 manifest 中的完整任务名称；如果任务定义没有名称，用完整 `task_id` 作占位，不得自行缩写或改名。

## 相关资源

- `scripts/cross_eval_utils.py`：共同有效任务配对、任务元数据、run 聚合、分析校验和 Markdown 渲染。
- `scripts/build_cross_eval_manifest.py`：生成确定性输入 manifest。
- `scripts/validate_cross_eval.py`：校验 Workflow 输出覆盖和证据字段。
- `scripts/render_cross_eval_report.py`：渲染结构化分析 Markdown。
- `references/workflow_template.js`：跨单元分析 Workflow 模板。
- `references/output_schema.md`：分析 JSON 字段和典型案例契约。
