# Preview 模式使用示例

## 场景

评测完成后需要快速查看各维度得分，决策下一步动作（是否补测/重跑、优先分析哪些单元），但根因分析非常耗时。Preview 模式跳过根因分析与有效性检查，快速生成含维度分析的报告。

## 完整流程示例

假设：
- round 目录：`eval_out/all_suite/round5_t3600`
- 参评模型：`xopglm51`, `xopglm52`, `xsparkx2agent`
- 参评 Harness：`astroncode`, `astronclaw`, `opencode`
- 目标：`xopglm52@astroncode`
- 定价日期：`2026-08-03`

### 1. 生成 Preview Excel（跳过根因分析）

```bash
python3 tools/report/scripts/generate_eval_report.py \
  --result-root eval_out/all_suite/round5_t3600 \
  --models xopglm51 xopglm52 xsparkx2agent \
  --harnesses astroncode astronclaw opencode \
  --target-model xopglm52 \
  --target-harness astroncode \
  --entities tools/report/data/entities.yaml \
  --pricing-date 2026-08-03
  # 不传 --analysis，评分详情表根因列为空
```

产物：`eval_out/all_suite/round5_t3600/report-workspace/output/report_7units_<timestamp>.xlsx`

**手动改名**（标识 preview）：
```bash
cd eval_out/all_suite/round5_t3600/report-workspace/output
mv report_7units_20260803_101530.xlsx report_7units_20260803_preview.xlsx
```

### 2. 提取 leader_data

```bash
python3 tools/report/skills/eval-report/scripts/extract_leader_report_data.py \
  --excel eval_out/all_suite/round5_t3600/report-workspace/output/report_7units_20260803_preview.xlsx \
  --output eval_out/all_suite/round5_t3600/report-workspace/output/report_7units_20260803_preview_leader_data.json
```

### 3. 生成领导版 Markdown（不含典型案例）

**手动编写**，按 `references/report_template.md` 结构，包含：
1. 总览表（从 Excel 复制）
2. 二～五、各维度分析（基于 leader_data.json 数值 + 控制变量表）
3. ~~六、典型低分案例~~（跳过）
4. 总结与改进建议（仅基于维度分差，改进方向更概括）

保存为 `eval_out/all_suite/round5_t3600/评测报告_GLM-5.2_AstronCode_round5_preview.md`

### 4. Preview 审计（跳过有效性门禁与根因覆盖率）

```bash
python3 tools/report/skills/audit-eval-report/scripts/audit_eval_report.py \
  --result-root eval_out/all_suite/round5_t3600 \
  --excel eval_out/all_suite/round5_t3600/report-workspace/output/report_7units_20260803_preview.xlsx \
  --models xopglm51 xopglm52 xsparkx2agent \
  --harnesses astroncode astronclaw opencode \
  --entities tools/report/data/entities.yaml \
  --pricing-date 2026-08-03 \
  --skip-checks validity_gate root_cause_coverage \
  --fail-on never
```

预期结果：`PASS | error=0 warning=0`（preview 只审计显示名反查、成本复算、表头完整性）

审计报告保存在 `eval_out/all_suite/round5_t3600/report-workspace/audit/`

### 5. 发布 Preview 报告

- Excel：`report_7units_20260803_preview.xlsx`
- Markdown：`评测报告_GLM-5.2_AstronCode_round5_preview.md`

对外说明：*"这是本轮评测的预览报告，包含各维度得分与对比分析。典型案例分析正在进行中，完整报告预计 X 日发布。"*

---

## 后续：Full 报告流程

根因分析完成后：

### 1. 重新生成 Excel（含根因）

```bash
python3 tools/report/scripts/generate_eval_report.py \
  --result-root eval_out/all_suite/round5_t3600 \
  --models xopglm51 xopglm52 xsparkx2agent \
  --harnesses astroncode astronclaw opencode \
  --target-model xopglm52 \
  --target-harness astroncode \
  --entities tools/report/data/entities.yaml \
  --pricing-date 2026-08-03 \
  --analysis "xopglm51@astroncode=eval_out/.../analysis_xopglm51@astroncode__all.json" \
             "xopglm52@astroncode=eval_out/.../analysis_xopglm52@astroncode__all.json" \
             "xsparkx2agent@astroncode=eval_out/.../analysis_xsparkx2agent@astroncode__all.json"
  # 传入所有目标 unit 的根因分析 JSON
```

产物：`report_7units_<timestamp>.xlsx`（不带 _preview 后缀）

### 2. 有效性检查

```bash
python3 tools/report/skills/validate-eval-results/scripts/scan_batch.py \
  --result-root eval_out/all_suite/round5_t3600 \
  --models xopglm51 xopglm52 xsparkx2agent \
  --harnesses astroncode astronclaw opencode
```

产物：`eval_out/all_suite/round5_t3600/report-workspace/validity/eval_result_validity.json`

### 3. 重新提取 leader_data（含根因）

```bash
python3 tools/report/skills/eval-report/scripts/extract_leader_report_data.py \
  --excel eval_out/.../report_7units_<timestamp>.xlsx \
  --output eval_out/.../report_7units_<timestamp>_leader_data.json
```

### 4. 生成完整领导版 Markdown（含典型案例）

包含七节：总览 + 五维度 + 典型案例 + 总结

保存为 `评测报告_GLM-5.2_AstronCode_round5.md`（不带 _preview）

### 5. Full 审计

```bash
python3 tools/report/skills/audit-eval-report/scripts/audit_eval_report.py \
  --result-root eval_out/all_suite/round5_t3600 \
  --excel eval_out/.../report_7units_<timestamp>.xlsx \
  --models xopglm51 xopglm52 xsparkx2agent \
  --harnesses astroncode astronclaw opencode \
  --entities tools/report/data/entities.yaml \
  --pricing-date 2026-08-03 \
  --validity eval_out/all_suite/round5_t3600/report-workspace/validity/eval_result_validity.json \
  --fail-on never
  # 不传 --skip-checks，执行完整审计
```

预期：`PASS` / `REVIEW` / `FAIL`（根据实际有效性门禁结果）

### 6. 发布 Full 报告

- Excel：`report_7units_<timestamp>.xlsx`
- Markdown：`评测报告_GLM-5.2_AstronCode_round5.md`

对外说明：*"附件是本轮评测的完整报告，已补充低分任务根因分析与改进建议。此前发布的预览报告中的数据维度部分保持不变。"*

---

## Preview vs Full 对比

| | Preview | Full |
|---|---|---|
| **生成时机** | 评测完成后立即 | 根因分析完成后 |
| **根因分析** | 跳过 | 必需 |
| **有效性检查** | 跳过 | 必需 |
| **Excel 根因列** | 空 | 回填 |
| **领导报告章节** | 6 节（无典型案例） | 7 节（含典型案例） |
| **审计范围** | 显示名 + 成本 + 表头 | 全部（含有效性门禁） |
| **产物后缀** | `_preview` | 无后缀 |
| **对外定位** | "预览报告，完整版随后" | "正式报告" |
| **改进建议粒度** | 基于分差，较概括 | 基于案例，可执行 |

---

## 注意事项

1. **Preview 的维度数据与 Full 完全一致**（同样的总览、五个维度 Sheet、控制变量表），差异仅在根因列与典型案例节的有无。

2. **手动改名产物文件加 `_preview` 后缀**，避免与 full 报告混淆。`generate_eval_report.py` 当前不自动加后缀。

3. **Preview 报告不能声称"可发布"**——审计跳过了有效性门禁，无法确认评测结果是否存在 L3/L4 问题。仅用于内部快速决策。

4. **Full 报告的 Excel 需重新生成**（不能在 preview Excel 上手动补根因列），因为 `--analysis` 参数会影响评分详情表的数据加载与校验逻辑。
