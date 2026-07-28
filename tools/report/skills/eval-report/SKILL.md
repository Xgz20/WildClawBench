---
name: eval-report
description: End-to-end WildClawBench evaluation report pipeline for a target model - validates raw results, runs scoped root-cause analysis, generates Excel with analysis backfill, produces a leader-facing Markdown report, and audits metrics and conclusions before publication. Triggers on "生成评测报告""评测报告生成""完整评测报告""领导版报告". Covers validity and publication gates, Excel extraction, metric caveats, and business-report writing rules.
---

# 评测报告生成 Skill（WildClawBench 端到端版）

针对一轮评测结果（round 目录）与一个目标模型，一条龙产出三件报告产物，并执行前后两道质量门禁：

1. **根因分析 JSON**（默认 `analysis_<model>@<harness>__lt60.json`，逐低分任务的结果分析+根因）
2. **Excel 评测报告**（多 Sheet 对比 + 根因回填到详情 Sheet）
3. **领导版 Markdown 评测报告**（六维度、评语+表格+备注版式，商务文风）

前置门禁调用 `validate-eval-results`，发布前门禁调用 `audit-eval-report`。两个检查 Skill 均可独立运行；`eval-report` 只编排依赖顺序。各步幂等，可单独重跑。分析单元命名 `<model>@<harness>`（如 `xsparkx2agent@astroncode`）。

## 输入

- **round 根目录**：如 `eval_out/all_suite/round5`（下辖 `<model>/<harness>/<套件>/<task>/<run>/`）
- **目标模型（1 个或多个）**：需要根因分析与领导版报告的模型列表（如 `xsparkx2flash xsparkx2agent`）；round 下未列入的其他模型自动作为 Excel/表格中的对比参照
- **样式参考**（领导版报告）：`references/report_template.md`

**多模型支持说明**：
- 第 1 步按 unit 独立执行，目标模型有几个就循环几次（互不依赖，Workflow 可并行发）；
- 第 2 步 Excel 天然覆盖 round 下全部模型，`--models` 可过滤参评子集，`--analysis` 接受任意多个 `UNIT=path` 同时回填；
- 第 3 步领导版报告为**单目标聚焦**版式（对比表含全部参评模型，评语/案例/结论围绕一个目标模型），多个目标模型时**每个模型各生成一份** `评测报告_<模型>_<round>.md`，共用同一份 Excel 数据源。

## 第 0 步：评测结果有效性门禁

先调用 `validate-eval-results`，对原始结果的完整性、环境故障、指标完整性和跨 unit 可比性做检查：

```bash
python3 tools/report/skills/validate-eval-results/scripts/validate_eval_results.py \
  --result-root <round> --fail-on never
```

- `PASS`：继续生成报告。
- `REVIEW`：逐项完成人工归因并在最终报告披露；未闭环前不发布。
- `FAIL`：默认阻断。修复环境/数据并补跑后重新检查；只有用户明确接受风险时才可继续，且报告首页必须披露无效范围和影响。

## 第 1 步：低分根因分析（每个需要回填的模型跑一次）

调用 `low-score-analysis` Skill 的流程，要点复述：

```bash
# 1a. 生成低分清单（阈值 60）
python3 tools/report/skills/low-score-analysis/scripts/generate_failed_tasks_manifest.py \
  --result-root <round>/<model>/<harness> --threshold 60
# 记录 WORKSPACE_DIR、SELECTION_SCOPE=lt60、ANALYSIS_PATH、MANIFEST_PATH
```

```python
# 1b. 精简分批（utils.simplify_task + split_into_batches，每批 10）
# 批次 JSON 落盘到 scratchpad，如 scratchpad/round5/<model>_batch_<i>.json
```

**1c. Workflow 逐任务分析（关键工程经验）**：
- **不要把任务数组内联进 Workflow args**（会触发参数体积限制/手工内联易错）。正确做法：workflow 脚本内先用一个 `effort:'low'` 的 Load 子代理按路径读批次 JSON（schema 强制返回 `{tasks:[...]}`），再对每个任务并发起分析子代理。参考脚本：`references/workflow_batch_loader.js`。
- 分析子代理 prompt 必带：失分检查点字典、双层错误（error_execution/error_grading）、超时标志、用量；要求**先读任务 .md 判分代码，再全量读 transcript 取证**，输出 `{task_id, result_analysis, root_cause_analysis}`，根因须标注 L1a/L1b/L3/L4 归属层。
- **后台任务 `.output` 文件是包装 dict**，真正结果在 `["result"]` 键。
- 每批返回即 `utils.save_batch_result(result, workspace, unit, batch_i, "lt60")` 落盘；全部完成后 `merge_all_batches(workspace, unit, "lt60")`（**返回的是合并文件路径**，不是 dict）。
- 合并后必须校验：任务数与清单 1:1 对齐、无缺失/多余、result_analysis/root_cause_analysis 均非空。
- 所有分析文件统一落在 `<round>/report-workspace`。即使第 1 步传入 unit 目录，也禁止改用 `<unit>/report-workspace`。

## 第 2 步：Excel 报告 + 根因回填

```bash
python3 tools/report/scripts/generate_eval_report.py \
  --result-root <round> \
  --analysis "<model1>@<harness>=<round>/report-workspace/analysis_<model1>@<harness>__lt60.json" \
             "<model2>@<harness>=<round>/report-workspace/analysis_<model2>@<harness>__lt60.json"
# 输出 <round>/report-workspace/output/report_<N>units_<ts>.xlsx
```

回填校验：打开生成的 xlsx，`评分详情_<unit>` Sheet 的「结果分析」「根因分析」列非空行数 == 分析 JSON 条数。

生成 Excel 后立即运行 `audit-eval-report` 的自动对账。发现 `FAIL` 时先修复生成脚本或原始数据并重新生成，不要继续基于错误 Excel 写 Markdown。

## 第 3 步：领导版 Markdown 评测报告（本 Skill 核心增量）

**版式**：每个维度 = 一段**评语**（结论前置）+ 一张**数据表** + 一条 **`> 备注`**（口径/读数说明）。骨架见 `references/report_template.md`。

**六个固定维度**（数据全部从第 2 步 Excel 的对应 Sheet 提取，用 openpyxl 读，禁止手抄）：

> ⚠️ **取数纪律（最容易出错、必须遵守）**：报告里每一个数字都必须来自 Excel 单元格，禁止凭 skill 示例、记忆或"大致印象"填数。正确做法见下方 **§3.1 取数纪律**——先跑提取脚本落 JSON，再逐格引用；出稿后逐格 diff 最新 Excel。skill 正文里出现的任何具体数字（如"L1=15 题""请求数 106"）都是**历史轮次的示例**，不是本轮真值，绝不可照抄进报告。

| 章节 | 数据来源 Sheet | 必含要素 |
|---|---|---|
| 报告头 | - | 评测配置（测评集/任务数/harness/模型/轮次/超时）+ 结论（3 条以内，含最关键量化证据） |
| 一、总览 | 「总览」 | 逐 unit：总平均分/用例数/正常完成数/执行错误数/超时数/完成率/**总请求数**/工具调用数。**六场景分不在总览、在「分类对比」**，如需在总览引用须显式跨表取。备注写字段口径 |
| 二、Agent能力 | 「Agent能力对比」+「Agent能力对比·去污染」 | **分两段**：第 1 段 7 维原始能力表（列名严格取自 Sheet：代码生成/工具调用/数据处理/检索验证/推理规划/内容生成/验证交付）+ 强项/短板评语（Sheet 末两列已算好）；第 2 段 3 项去污染表（数据处理·去落盘污染/推理规划·去落盘污染/内容生成·去落盘污染）+ 口径备注。两段各一张表，中间用一段评语衔接 |
| 三、难度等级 | 「难度对比」 | **表格朝向照抄 Excel：模型@Harness 第 1 列、总平均分第 2 列、各难度档平铺成后续列**（转置版，勿把难度放第 1 列）。**每档用例数写在 Sheet 列名里**（如 `L3平均分(27例)`），照抄列名的括号数字，不要自造 |
| 四、分类维度 | 「分类对比」 | **表格朝向照抄 Excel：模型@Harness 第 1 列、总平均分第 2 列、各分类平铺成后续列**（转置版，与难度/模态相同）。每分类列头含用例数（如 `01_生产力工作流平均分(10例)`） |
| 五、模态对比 | 「模态对比」（主表）+「用例对比明细」（示例表逐格取分） | **四段顺序**：结论 → 模态对比表（**朝向同难度/分类：模型@Harness 第 1 列、纯文本/多模态平铺成列**，用例数在列名里）→ 视觉 401 环境描述 → 具体示例表。示例表每格填真实得分数字（如 0/48.0），禁止"见明细""见下表"等占位词；若涉及视觉 401 须做"共担因素"分析（见下） |
| 六、典型低分案例 | analysis JSON（或「评分详情_<unit>」的结果分析/根因分析列） | 5–6 个案例表格，覆盖不同失分机制 |

**未进报告但可辅助核对的 Sheet**：「模型×Harness矩阵」（总均分交叉表）、「工具调用对比」（分 harness 逐工具 成功率/格式准确率，分节表头在第 2 行）、「分差矩阵」（unit×unit 分差）、「用例对比明细」（每题各 unit 得分+检查点，模态示例表的取分来源）。

### 3.0 Excel Sheet → 列名权威对照（`generate_eval_report.py` 输出，改脚本须同步本表）

以下列名与 `generate_eval_report.py` 各 `write_*_sheet` 函数一一对应。提取时**按列名匹配、不按列号**（脚本可能增删列导致列号漂移）。

| Sheet | 表头行 | 列（按序） |
|---|---|---|
| 总览 | 第 1 行 | 模型 / Harness / 总平均分 / 用例数 / 正常完成数 / 执行错误数 / 超时数 / 完成率 / 总tokens / 总请求数 / 总耗时(s) / 总成本(USD) / 工具调用数 / 格式准确率 / 执行成功率 / 不确定占比。（多轮时在「完成率」后插「平均轮数」；工具四列仅在有已注册 harness 指标时出现） |
| Agent能力对比 | 第 1 行 | 模型@Harness / 总平均分 / 代码生成 / 工具调用 / 数据处理 / 检索验证 / 推理规划 / 内容生成 / 验证交付 / 模型强项 / 模型短板 |
| Agent能力对比·去污染 | 第 1 行 | 模型@Harness / 总平均分 / 数据处理·去落盘污染 / 推理规划·去落盘污染 / 内容生成·去落盘污染 |
| 难度对比 | 第 1 行 | 模型@Harness / 总平均分 / `L?平均分(N例)`（档位与 N 均动态，照抄列名） |
| 模态对比 | 第 1 行 | 模型@Harness / 总平均分 / `纯文本平均分(N例)` / `多模态平均分(N例)` |
| 分类对比 | 第 1 行 | 模型@Harness / 总平均分 / `<分类>平均分(N例)`（每分类一列，如 `01_生产力工作流平均分(10例)` / `02_代码智能平均分(12例)` …） |
| 用例对比明细 | 第 1 行 | 分类 / 用例ID / 用例名称 / 难度 / 模态 / 输入(Prompt) / 预期行为 / 评分标准 / 检查点 / `<unit> 得分`（每 unit 一列，格内「总分+检查点」）/ 最优单元 / 最大分差 |
| 评分详情_<unit> | 第 1 行 | …/ 总得分 / 检查点得分明细 / 失分点 / 裁判判词 / 执行错误 / 总tokens / 请求数 / 耗时(s) / 执行记录(jsonl) / **结果分析** / **根因分析** / 工具调用数 / 格式准确率 / 执行成功率 / 不确定占比 |
| 模型×Harness矩阵 | 第 1 行 | 模型 \ Harness / `<harness>`（每 harness 一列，格=总均分） |
| 工具调用对比 | **第 2 行**（第 1 行是 `【Harness: x】` 分节标题） | 模型 / 工具 / 调用数 / 成功 / 失败 / 不确定 / 格式错误 / 成功率 / 格式准确率 |
| 分差矩阵 | 第 1 行 | 行单元 - 列单元 / `<unit>`（每 unit 一列） |

> **数值口径**：Excel 里的百分比列（总平均分、各能力分、各难度/分类/模态分、完成率、成功率）单元格值**已是百分数**（如 `34.3` 表示 34.3%），写报告时直接加 `%`，不要再 ×100；「总得分」「用例对比明细」格内是 0~1 原始分（如 `0.343`）。

### 3.1 取数纪律（硬规则，违反即返工）

1. **一律脚本提取、禁止手填**：写报告前必须先跑一个 openpyxl 提取脚本，把上述 Sheet 逐格读进一个 JSON（键=列名，值=单元格），报告里的每个数字都从该 JSON 取。禁止凭 skill 示例、记忆、"和上一轮差不多"填任何数字。
2. **按列名取、不按列号取**：脚本改动会让列号漂移（如总览新增了「正常完成数/完成率」列）。提取代码用 `dict(zip(headers, row))` 按列名索引，杜绝错位。
3. **区分数据源，勿张冠李戴**：常见错误——把「总览」的工具四列（工具调用数/格式准确率/执行成功率/不确定占比）当成「Agent能力对比」的 7 维能力。二者是不同 Sheet、不同含义：前者是工具调用统计，后者是 cap7 能力分。7 维能力**只**来自「Agent能力对比」Sheet 的 7 个中文能力列。
4. **用例数照抄列名括号**：难度/模态的每档用例数写在列名 `(N例)` 里，直接抄，不要自己数或套用历史值（历史轮次 L1 有 15 题，本轮可能只有 1 题）。
5. **场景强弱看数不靠印象**：某场景是目标模型的强项还是短板，以「分类对比」该行数值为准（含「最佳单元」列）。曾出现把目标模型四模型最高分的场景误写成短板的严重错误，务必逐格核对。
6. **表格朝向照抄 Excel、勿自行转置**：Markdown 表的行列方向必须与来源 Sheet 一致。难度对比、模态对比、分类对比三张表**统一用转置版**：`write_dimension_sheet_transposed` 生成,「模型@Harness 第 1 列 + 总平均分第 2 列 + 维度档平铺成列」,每列列头含用例数(如 `L3平均分(27例)` 或 `01_生产力工作流平均分(10例)`)。写报告时对着 Sheet 表头照搬,不要凭习惯把维度当第 1 列。曾出现难度/模态表被写反(难度放第 1 列)的错误。
7. **出稿后逐格自检**：报告落盘后，把每张表的每个数字与最新 Excel（认准最新时间戳，旧文件仍在 output/）diff 一遍，行列朝向也要对齐，不一致立即改。

**案例表格式**（每案例一张四行表）：

```
| 项目 | 内容 |
| 任务 | 一句话任务描述 |
| 执行情况 | 模型实际做了什么（从 result_analysis 摘证据，含关键数字/引语） |
| 失分原因 | 判分为何归零/扣分 |
| 定性 | 归属层 + 根因类别（L1a/L1b/L3/L4） |
```

案例选取原则：**每个案例代表一类不同机制**（过早结束 / 循环不收敛 / 环境断网 / 工具协议 / 判分误判 / 底层能力），从 analysis JSON 里挑证据最完整的。

### 文风红线（面向领导汇报，最容易返工的一环）

报告读者是领导：**通俗易懂、给结论、摆事实**。两个方向的坑都要避开：

1. **禁 AI 味**：不用"值得注意的是/总而言之/综上所述/深入剖析/赋能/抓手"等套话；不堆排比句；不滥用加粗（每段最多突出 1–2 处关键数字/结论）；不用 emoji；不写"首先/其次/再次/最后"式的机械展开。
2. **禁过度口语**：不用"干到一半就不干了/挡箭牌/两头夹击/救回/一枝独秀/戛然而止"等表达 → 改为"任务中途中止/不构成差距来源/双重叠加/回收/唯一领先/随即终止"。
3. **禁反问句和设问句**："为什么 X 能领先？因为…" → "X 领先的原因在于…"；"能不能排除环境因素？答案是…" → "结论为：…"。
4. **结论前置**：每章第一句就是该维度的判断，数据表只做支撑；不铺垫、不卖关子。
5. **通俗**：专业术语首次出现给一句白话解释（如"落盘 = 把结果写入指定文件"、"L1b 长程执行 = 会做但没做完的执行链路问题"）。
6. 说明性文字统一用 `> **备注**`，不用"读法"。
7. 环境/判分问题必须与模型能力剥离表述，显式标注"非模型能力问题"。

正反例：
- ❌ "最扎眼的不是分数，是请求数……差距一目了然" → ✅ "请求数差异是本轮最突出的特征：X2-300B 106 次、GLM5.2 1665 次，相差逾十倍"
- ❌ "别拿 401 当挡箭牌" → ✅ "视觉 401 是 spark 系模型侧的视觉通道短板，部分解释多模态差距"（先核实 401 是否共担，见下）

### 数据口径与常见坑（写报告前必读）

1. **执行错误数 = 非超时的运行中断任务数**（execution_status 带 error 但非超时，如容器/依赖异常、被测进程 rc≠0）。**与「超时数」互斥**——超时任务同时写了 error 字段，但只计入「超时数」，不重复计入「执行错误数」。**≠ 一定 0 分**——超时前已落盘部分产物的检查点仍计分（实例：task_10_pdf_digest 超时仍得 28.1）。**也 ≠ 0 分的唯一来源**——大量 0 分来自"正常退出但未落盘"（过早结束）。报告总览备注必须写清这几层关系。
2. **llm_judge / hybrid 任务的 score.json 只有 overall_score，没有分项检查点**——用例对比明细里"有总分无检查点"属正常设计，不是数据缺失；automated 任务偶有"门控短路"（前置门槛失败即 `return {overall_score:0}`）也只有总分。被问到时先按 grading_type 分类核实再回答。
3. **总请求数是长程执行续航的最强量化信号**（本次案例：X2-300B 60 题仅 106 次请求 vs GLM5.2 1665 次），总览必引。
4. **视觉 401 先判"模型侧还是环境侧"再下结论**：官方图像助手 `.wildclaw_image.py` 用**被测模型自身**做视觉理解，因此 401 通常与模型强绑定而非共担环境噪声。核实方法：grep 各模型该任务 transcript，看助手返回 `{"ok": true}`（视觉可用）还是「无效的令牌」401（视觉不通）。若某些模型 ok:true、另一些 401（本轮实况：gpt-5.5 全程 ok，spark 系/GLM 多为 401），则 401 是**模型侧视觉通道短板**，部分解释多模态差距，不可当作应剥离的共担因素。仅当全部模型都 401 时才按共担处理。示例表每格填真实得分（如 artwork：gpt 100 / spark 0），不写"见明细"。
5. **判分误判要点名**（把没执行的命令当成已执行、把无害模板文本当成恶意实现等，如 exec_command heredoc 写文件时正文引用恶意串被正则当作执行），归 L4 并建议评测方修复，不计入模型短板。措辞用"判分误判"，避免"假阳性"这类术语。
6. 报告落盘后**逐数自检**：所有表格数值 diff 一遍最新 Excel（尤其换过脚本重新生成后，旧文件仍在 output/ 目录，认准最新时间戳）。

## 第 4 步：发布前报告审核门禁

调用 `audit-eval-report` 对 Excel 做独立复算，并按其 checklist 审核 Markdown 的数字、排序、强弱判断、因果表述和案例证据：

```bash
python3 tools/report/skills/audit-eval-report/scripts/audit_eval_report.py \
  --result-root <round> \
  --excel <round>/report-workspace/output/report_<N>units_<ts>.xlsx \
  --validity <round>/report-workspace/validity/eval_result_validity.json \
  --fail-on never
```

只有审核结论为 `PASS` 且 Markdown 人工检查项全部闭环才可发布。`REVIEW` 必须记录解释、证据和接受风险的人；`FAIL` 必须修复并重生成。

## 产物落位

```
<round>/
├── report-workspace/
│   ├── _failed_tasks_<unit>__lt60.json
│   ├── analysis_<unit>__lt60.json
│   ├── validity/eval_result_validity.{json,md}
│   ├── audit/report_audit_<xlsx-stem>.{json,md}
│   └── output/report_<N>units_<ts>.xlsx
├── <model>/<harness>/低分任务根因分析报告_<unit>.md   # 可选（low-score-report skill）
└── 评测报告_<目标模型>_<round>.md                      # 领导版
```

需要回填其它范围时，显式把相应 scoped JSON 传给 `--analysis`。同一个 unit 一次只传一个最终范围文件；若传入多个重叠文件，后加载的任务会覆盖先加载值并产生警告。

## 安装

```bash
ln -snf ../../tools/report/skills/eval-report .claude/skills/eval-report
```
