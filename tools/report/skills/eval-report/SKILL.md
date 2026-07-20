---
name: eval-report
description: End-to-end WildClawBench evaluation report pipeline for a target model - runs low-score root-cause analysis, generates the Excel report with analysis backfill, and produces a leader-facing 6-dimension Markdown report (总览/Agent能力/难度/分类/模态/典型案例). Triggers on "生成评测报告""评测报告生成""完整评测报告""领导版报告". Covers data extraction from Excel sheets, metric caveats (执行错误口径/llm_judge检查点/请求数信号), and business-report writing style rules.
---

# 评测报告生成 Skill（WildClawBench 端到端版）

针对一轮评测结果（round 目录）与一个目标模型，一条龙产出三件产物：

1. **根因分析 JSON**（`analysis_<model>@<harness>.json`，逐低分任务的结果分析+根因）
2. **Excel 评测报告**（多 Sheet 对比 + 根因回填到详情 Sheet）
3. **领导版 Markdown 评测报告**（六维度、评语+表格+备注版式，商务文风）

三步各自幂等，可单独重跑。分析单元命名 `<model>@<harness>`（如 `xsparkx2agent@astroncode`）。

## 输入

- **round 根目录**：如 `eval_out/all_suite/round5`（下辖 `<model>/<harness>/<套件>/<task>/<run>/`）
- **目标模型（1 个或多个）**：需要根因分析与领导版报告的模型列表（如 `xsparkx2flash xsparkx2agent`）；round 下未列入的其他模型自动作为 Excel/表格中的对比参照
- **样式参考**（领导版报告）：`references/report_template.md`

**多模型支持说明**：
- 第 1 步按 unit 独立执行，目标模型有几个就循环几次（互不依赖，Workflow 可并行发）；
- 第 2 步 Excel 天然覆盖 round 下全部模型，`--models` 可过滤参评子集，`--analysis` 接受任意多个 `UNIT=path` 同时回填；
- 第 3 步领导版报告为**单目标聚焦**版式（对比表含全部参评模型，评语/案例/结论围绕一个目标模型），多个目标模型时**每个模型各生成一份** `评测报告_<模型>_<round>.md`，共用同一份 Excel 数据源。

## 第 1 步：低分根因分析（每个需要回填的模型跑一次）

调用 `low-score-analysis` Skill 的流程，要点复述：

```bash
# 1a. 生成低分清单（阈值 60）
python3 tools/report/skills/low-score-analysis/scripts/generate_failed_tasks_manifest.py \
  --result-root <round>/<model>/<harness> --threshold 60
# 末行输出 MANIFEST_PATH
```

```python
# 1b. 精简分批（utils.simplify_task + split_into_batches，每批 10）
# 批次 JSON 落盘到 scratchpad，如 scratchpad/round5/<model>_batch_<i>.json
```

**1c. Workflow 逐任务分析（关键工程经验）**：
- **不要把任务数组内联进 Workflow args**（会触发参数体积限制/手工内联易错）。正确做法：workflow 脚本内先用一个 `effort:'low'` 的 Load 子代理按路径读批次 JSON（schema 强制返回 `{tasks:[...]}`），再对每个任务并发起分析子代理。参考脚本：`references/workflow_batch_loader.js`。
- 分析子代理 prompt 必带：失分检查点字典、双层错误（error_execution/error_grading）、超时标志、用量；要求**先读任务 .md 判分代码，再全量读 transcript 取证**，输出 `{task_id, result_analysis, root_cause_analysis}`，根因须标注 L1a/L1b/L3/L4 归属层。
- **后台任务 `.output` 文件是包装 dict**，真正结果在 `["result"]` 键。
- 每批返回即 `utils.save_batch_result(result, workspace, unit, batch_i)` 落盘；全部完成后 `merge_all_batches(workspace, unit)`（**返回的是合并文件路径**，不是 dict）。
- 合并后必须校验：任务数与清单 1:1 对齐、无缺失/多余、result_analysis/root_cause_analysis 均非空。

## 第 2 步：Excel 报告 + 根因回填

```bash
python3 tools/report/scripts/generate_eval_report.py \
  --result-root <round> \
  --analysis "<model1>@<harness>=<...>/analysis_<model1>@<harness>.json" \
             "<model2>@<harness>=<...>/analysis_<model2>@<harness>.json"
# 输出 <round>/report-workspace/output/report_<N>units_<ts>.xlsx
```

回填校验：打开生成的 xlsx，`评分详情_<unit>` Sheet 的「结果分析」「根因分析」列非空行数 == 分析 JSON 条数。

## 第 3 步：领导版 Markdown 评测报告（本 Skill 核心增量）

**版式**：每个维度 = 一段**评语**（结论前置）+ 一张**数据表** + 一条 **`> 备注`**（口径/读数说明）。骨架见 `references/report_template.md`。

**六个固定维度**（数据全部从第 2 步 Excel 的对应 Sheet 提取，用 openpyxl 读，禁止手抄）：

| 章节 | 数据来源 Sheet | 必含要素 |
|---|---|---|
| 报告头 | - | 评测配置（测评集/任务数/harness/模型/轮次/超时）+ 结论（3 条以内，含最关键量化证据） |
| 一、总览 | 总览 | 总均分/用例数/执行错误/超时/六场景分/**总请求数**；备注写字段口径 |
| 二、Agent能力 | Agent能力对比 + Agent能力对比·去污染 | **分两段**：第 1 段 7 维原始能力表（不去污染）+ 强项/短板评语；第 2 段 3 项去落盘污染表 + 去污染口径备注。两段各一张表，中间用一段评语衔接（"去污染后回升至 X/Y/Z…"） |
| 三、难度等级 | 难度对比 | L1–L4 各档（标注每档用例数） |
| 四、分类维度 | 分类对比 | 六场景 + 目标模型与最佳的分差列 |
| 五、模态对比 | 模态对比 | **四段顺序**：结论 → 模态对比表（纯文本/多模态）→ 视觉 401 环境描述 → 具体示例表。示例表每格填真实得分数字（如 0/48.0），禁止"见明细""见下表"等占位词；若涉及视觉 401 须做"共担因素"分析（见下） |
| 六、典型低分案例 | analysis JSON | 5–6 个案例表格，覆盖不同失分机制 |

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

1. **执行错误 = 超时/跑挂的任务数**（execution_status 带 error 或非正常结束），**≠ 一定 0 分**——超时前已落盘部分产物的检查点仍计分（实例：task_10_pdf_digest 超时仍得 28.1）。**也 ≠ 0 分的唯一来源**——大量 0 分来自"正常退出但未落盘"（过早结束）。报告总览备注必须写清这三层关系。
2. **llm_judge / hybrid 任务的 score.json 只有 overall_score，没有分项检查点**——用例对比明细里"有总分无检查点"属正常设计，不是数据缺失；automated 任务偶有"门控短路"（前置门槛失败即 `return {overall_score:0}`）也只有总分。被问到时先按 grading_type 分类核实再回答。
3. **总请求数是长程执行续航的最强量化信号**（本次案例：X2-300B 60 题仅 106 次请求 vs GLM5.2 1665 次），总览必引。
4. **视觉 401 先判"模型侧还是环境侧"再下结论**：官方图像助手 `.wildclaw_image.py` 用**被测模型自身**做视觉理解，因此 401 通常与模型强绑定而非共担环境噪声。核实方法：grep 各模型该任务 transcript，看助手返回 `{"ok": true}`（视觉可用）还是「无效的令牌」401（视觉不通）。若某些模型 ok:true、另一些 401（本轮实况：gpt-5.5 全程 ok，spark 系/GLM 多为 401），则 401 是**模型侧视觉通道短板**，部分解释多模态差距，不可当作应剥离的共担因素。仅当全部模型都 401 时才按共担处理。示例表每格填真实得分（如 artwork：gpt 100 / spark 0），不写"见明细"。
5. **判分误判要点名**（把没执行的命令当成已执行、把无害模板文本当成恶意实现等，如 exec_command heredoc 写文件时正文引用恶意串被正则当作执行），归 L4 并建议评测方修复，不计入模型短板。措辞用"判分误判"，避免"假阳性"这类术语。
6. 报告落盘后**逐数自检**：所有表格数值 diff 一遍最新 Excel（尤其换过脚本重新生成后，旧文件仍在 output/ 目录，认准最新时间戳）。

## 产物落位

```
<round>/
├── <model>/<harness>/report-workspace/
│   ├── _failed_tasks_<unit>.json
│   └── analysis_<unit>.json
├── <model>/<harness>/低分任务根因分析报告_<unit>.md   # 可选（low-score-report skill）
├── report-workspace/output/report_<N>units_<ts>.xlsx
└── 评测报告_<目标模型>_<round>.md                      # 领导版
```

## 安装

```bash
ln -snf ../../tools/report/skills/eval-report .claude/skills/eval-report
```
