# Web E2E 评分 JSON 契约

## 指标 Profile 与兼容性

`task_contract.json` v3 显式声明 `metric_profile`；旧 v2 契约缺失该字段时按 `web-e2e-detailed-v1` 兼容。

- `web-e2e-detailed-v1`：`score_input.criteria[].score` 为 0–1，生成一级/二级维度和独立美观度。
- `artifactsbench-web-v1`：`score_input.criteria[].raw_score` 必须是 0–10 整数；脚本输出时确定性增加 `score=raw_score/10`。不接受小数原始分，也不初始化 `aesthetic`。

ArtifactsBench 输入示例：

```json
{
  "metric_profile": "artifactsbench-web-v1",
  "evaluation_status": "completed",
  "criteria": [
    {
      "key": "c01_core_function",
      "raw_score": 7,
      "reason": "实现达到 7 分锚点，但缺少满分要求的进阶能力。",
      "actions": ["完成核心流程并检查代码"],
      "evidence": [{"type": "observation", "path": "evidence/c01.md", "description": "操作和代码观察"}]
    }
  ]
}
```

若 Criterion 的 contract `evidence_policy.required_types` 包含 `screenshot`，必须提供 `type=screenshot` 的证据。该要求只服务原始 Criterion，不启用独立美观度指标。

## `score_input.json`

评分 Agent 只填写判断和证据。文件位于当前单题工作空间的 `private-scoring/score_input.json`：

```json
{
  "evaluation_status": "completed",
  "evaluation_error": null,
  "site_url": "http://127.0.0.1:4173",
  "browser": {"name": "Codex Browser", "viewport": "1440x900"},
  "criteria": [
    {
      "key": "header_daily_overview",
      "score": 1.0,
      "reason": "页面展示指定标题和今日概览。",
      "actions": ["打开首页", "检查顶部区域"],
      "evidence": [
        {"type": "screenshot", "path": "evidence/header.png", "description": "顶部区域"}
      ]
    }
  ],
  "aesthetic": {
    "status": "completed",
    "error": null,
    "screenshots": [
      {
        "label": "desktop-main",
        "path": "evidence/aesthetic-desktop-main.png",
        "viewport": {"width": 1440, "height": 900},
        "state": "首页初始状态",
        "description": "桌面首屏和主要操作"
      },
      {
        "label": "desktop-state",
        "path": "evidence/aesthetic-desktop-state.png",
        "viewport": {"width": 1440, "height": 900},
        "state": "代表性交互状态",
        "description": "桌面端状态变化"
      },
      {
        "label": "mobile-main",
        "path": "evidence/aesthetic-mobile-main.png",
        "viewport": {"width": 390, "height": 844},
        "state": "窄屏首页",
        "description": "移动端重排和可读性"
      }
    ],
    "dimensions": [],
    "checklist": [],
    "strengths": [],
    "defects": []
  },
  "scorer": {"agent": "Codex", "model": "", "session_id": ""}
}
```

`evaluation_status` 只允许 `completed` 或 `evaluation_error`。每个 task contract criterion 必须恰好出现一次，不能增加、删除或改名。

功能检查点的交互与证据要求见 [浏览器交互评分与误判防护](browser-interaction-scoring.md)。0 分理由必须描述按正确控件方式复核后，候选页面仍与 Rubric 不符的可观察事实；“浏览器工具无法输入、拖动、捕获或验证”属于评测异常，不是候选失败。原生对话框、下载事件、瞬时状态和控件回读等非截图事实可以写入 `evidence/` 下的 Markdown 或 JSON 观察记录并由 criterion 引用。

仅详细 Profile 中，`init_score.mjs` 会按内置标准自动生成全部 6 个 `aesthetic.dimensions` 和 32 个 `aesthetic.checklist` 项，不得调整 ID 或顺序。评分 Agent 填写检查点状态、理由和证据，以及一级维度的汇总理由和证据；`aesthetic.dimensions[].score` 必须保持 `null`，由脚本推导。`aesthetic.status` 允许 `completed` 或 `evaluation_error`：

- `completed`：硬门禁仍是至少 2 张桌面截图和 1 张不大于 480px 的窄屏截图；每张填写唯一标签、`evidence/` 相对路径、数值视口、状态和说明。常规推荐 4–6 张不重复截图，覆盖桌面主状态、桌面交互状态、适用的空/错误/加载/选中/禁用状态、窄屏主状态和窄屏交互状态；简单页面可只满足最低 3 张，复杂页面按需增加。每个维度与检查项必须引用已有截图标签。
- `evaluation_error`：填写 `error`，美观度总分和维度保持空；不影响功能总分。

美观度对整个截图集合统一判断，不对单张截图分别计算总分。检查点状态为 `MET/PARTIAL/UNMET/NA`，脚本分别固化为 `100/50/0/null`。`NA` 不参与分子和分母；护栏项与加分项等权进入所属一级维度，一级维度分数允许两位小数并由脚本自动计算。`defects.severity` 为 `blocking/major/minor`，`where` 必须是截图标签。正式标准见 [aesthetic-scoring.md](aesthetic-scoring.md) 和 [aesthetic-rubric.json](aesthetic-rubric.json)。

若站点无法启动、浏览器不可用或评分流程异常，将 `evaluation_status` 设为 `evaluation_error` 并填写 `evaluation_error`。此时允许保留初始化后的 `score: null`、空动作和空证据；`finalize_score.mjs` 会保留“未判断”事实，并将总分及维度强制记为 0。若异常前已填写某个 criterion 分数，该项仍必须带理由、动作和证据。

功能评分与美观度结果相互独立：功能评分异常但已经取得完整美观度证据时，仍保留正式美观度结果；完全没有完成美观度取证时自动记录为 `aesthetic.status=evaluation_error`。反过来，美观度自身异常也不改变已经完成的功能总分。

`execution_record.json` 是可选输入，默认批次不生成。缺失时 `finalize_score.mjs` 将 `execution.status` 写为 `not_recorded`，Token、请求数、耗时、成本、工具调用数和格式准确率均为 `null`；这不影响正常浏览器评分和总分。受管评分仍必须从 `candidate_artifact.json.model` 读取由执行回执冻结的实际模型，并写入 `task_score.identity.model`；该身份不能依赖报告配置事后补全。`candidate_artifact.json.model_selection.mode` 为 `explicit` 时请求模型必须等于实际模型；为 `current` 时 `requested_model` 必须为空，但 `actual_model` 仍必须非空。缺少 `mode` 的旧回执按是否存在请求模型推断，以兼容旧批次。若管理员显式启用执行记录，`tools.format_accuracy` 使用 0–1 比例，不确定字段仍填 `null`，不能凭印象填写。

## `task_score.json`

`finalize_score.mjs` 生成以下稳定结构，保存为 `private-scoring/task_score.json`：

- `identity`：批次、题目、实际回读模型、Harness；受管评分的 `model.id` 不得为空；
- `execution`：执行状态和资源数据；
- `evaluation`：评分状态、浏览器、逐检查点分数与证据；
- `metric_profile`：本题采用的稳定指标 Profile；
- `metrics.total_score`：0–100，全部题目总平均分的输入；
- `evaluation.criteria[].raw_score`：仅 ArtifactsBench Profile 存在，保留 0–10 原始整数；同一项 `score` 为 0–1 归一化值；
- `metrics.primary_dimensions`、`metrics.secondary_dimensions`：详细 Profile 为 0–100；ArtifactsBench Profile 为空对象；
- `evaluation.aesthetic`、`metrics.aesthetic`：详细 Profile 保存美观度明细与汇总；ArtifactsBench Profile 只标记 `not_applicable`；
- `provenance`：题目与 Workspace 哈希、Skill 版本和评分时间。

执行错误、超时和评测异常仍应生成 `task_score.json`。它们的 `metrics.total_score` 为 0，状态字段保留异常类型；汇总报告才能同时计算完成率和全量平均分。`not_recorded + evaluation.completed` 视为正常完成，只表示本批次没有采集执行资源数据。

## 运行时端口冲突审计

execution/score 两份 `workspace/` 始终是冻结候选原件。端口冲突也不能修改原件；优先使用启动参数或环境变量换端口。仅当端口硬编码且不能外部覆盖、受管启动以 `START_FAILED_STOPPED` 结束、受管 stderr 同时包含原端口和明确占用错误时，`managed_runtime.mjs port-override` 才允许在 `private-scoring/runtime-workspace/` 内把唯一一处数字端口替换为另一合法端口。

发生替换时生成 `private-scoring/runtime-port-override.json`，schema 为 `wildclawbench.web-e2e-runtime-port-override/v1`。每条 `overrides[]` 保存：

- `runtime_created_at` 和记录时间；
- 冲突时的回环 URL、启动命令、受管日志路径及不可变证据快照 SHA-256；
- 运行时副本内的相对文件路径、原/新端口、唯一匹配数、替换方式及文件前后 SHA-256。

`build_submission.mjs` 要求审计文件与 `runtime-state.json.port_overrides` 完全一致，证据快照仍存在且哈希、冲突文本和端口均匹配。最终 `submission.json.candidate_artifacts[].runtime_port_overrides` 记录审计次数、文件和 SHA-256；无替换时次数为 0。运行时副本在提交前仍必须清理，候选双副本仍必须等于冻结 SHA。
