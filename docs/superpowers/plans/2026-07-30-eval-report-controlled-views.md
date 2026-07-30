# WildClawBench Evaluation Report Controlled Views Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 WildClawBench Excel 和领导版 Markdown 使用可维护的实体展示名、可复算成本和双控制变量视图，并用指定 round3 数据生成新的 6-unit 报告。

**Architecture:** 新建独立的 `report_entities.py` 负责版本化实体注册表、定价档案选择、token 语义规范化和 run 成本估算；`generate_eval_report.py` 保留 raw ID 作为内部主键，只在输出层使用展示标签。各维度原始全量表保持第 1 行表头不变，在下方追加两张复制视图；审核脚本通过隐藏元数据还原 raw ID 并独立复算成本。

**Tech Stack:** Python 3.9+、PyYAML、openpyxl 3.1+、sqlite3、unittest、Markdown。

---

## File Map

- Create `tools/report/data/entities.yaml`: 模型、Harness、定价档案和人民币汇率的版本化注册表。
- Create `tools/report/scripts/report_entities.py`: 注册表加载、日期选择、token 规范化、逐请求上下文读取和成本估算。
- Modify `tools/report/scripts/generate_eval_report.py`: CLI、展示标签、成本汇总、元数据 Sheet、控制变量视图和 Sheet 顺序。
- Create `tools/report/skills/eval-report/scripts/extract_leader_report_data.py`: 从最新 Excel 按表头与视图标题提取领导版 JSON。
- Modify `tools/report/skills/audit-eval-report/scripts/audit_eval_report.py`: 展示名还原、范围过滤和成本独立复算。
- Modify `tools/report/skills/validate-eval-results/scripts/validate_eval_results.py`: 支持与报告一致的模型/Harness 范围过滤。
- Modify `tools/report/skills/eval-report/SKILL.md`: 目标参数、章节顺序、双视图、成本和 L3/L4 发布规则。
- Modify `tools/report/skills/eval-report/references/report_template.md`: 领导版章节与短结论模板。
- Modify `tools/report/README.md`: 新 CLI、实体配置和成本口径。
- Modify `tools/report/tests/test_analysis_pipeline.py`: 注册表、成本、Excel、审核、提取器和 Skill 契约测试。

### Task 1: Versioned Entity Registry

**Files:**
- Create: `tools/report/data/entities.yaml`
- Create: `tools/report/scripts/report_entities.py`
- Test: `tools/report/tests/test_analysis_pipeline.py`

- [ ] **Step 1: Write failing registry tests**

Add tests that load a temporary registry and verify display names, dated profiles, exchange rates, fallback behavior and schema rejection:

```python
def test_entity_registry_loads_names_and_dated_pricing(self) -> None:
    registry = report_entities.load_registry(REPORT_DIR / "data/entities.yaml")
    self.assertEqual(registry.model_display("xopglm52"), "GLM-5.2")
    self.assertEqual(registry.harness_display("astroncode"), "AstronCode")
    self.assertEqual(
        registry.pricing_profile("gpt-5.5", date(2026, 7, 30)).profile_id,
        "2026-07-30-openai",
    )
    self.assertAlmostEqual(registry.cny_per_usd(date(2026, 7, 30)), 6.77)

def test_entity_registry_unknown_id_falls_back_with_warning(self) -> None:
    registry = report_entities.load_registry(REPORT_DIR / "data/entities.yaml")
    with self.assertLogs(level="WARNING"):
        self.assertEqual(registry.model_display("model-new"), "model-new")

def test_entity_registry_rejects_unknown_schema_version(self) -> None:
    path = Path(self.temp_dir.name) / "entities.yaml"
    path.write_text("schema_version: 99\nmodels: {}\nharnesses: {}\n", encoding="utf-8")
    with self.assertRaisesRegex(ValueError, "schema_version"):
        report_entities.load_registry(path)
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
python3 -m unittest \
  tools.report.tests.test_analysis_pipeline.AnalysisPipelineTest.test_entity_registry_loads_names_and_dated_pricing \
  tools.report.tests.test_analysis_pipeline.AnalysisPipelineTest.test_entity_registry_unknown_id_falls_back_with_warning \
  tools.report.tests.test_analysis_pipeline.AnalysisPipelineTest.test_entity_registry_rejects_unknown_schema_version -v
```

Expected: import or attribute failures because `report_entities.py` and `entities.yaml` do not exist.

- [ ] **Step 3: Add the registry data file**

Create the exact `schema_version: 1` structure from the approved design, including:

```yaml
exchange_rates:
  CNY:
    - effective_from: 2026-07-30
      cny_per_usd: 6.77
      source: Morningstar via Google
models:
  gpt-5.5:
    display_name: GPT-5.5
    pricing_profiles:
      - id: 2026-07-30-openai
        effective_from: 2026-07-30
        currency: USD
        unit_tokens: 1000000
        tiers:
          - id: short-context
            max_input_tokens_per_request: 272000
            input_uncached: 5
            input_cached: 0.5
            output: 30
          - id: long-context
            min_input_tokens_per_request: 272001
            input_uncached: 10
            input_cached: 1
            output: 45
  xopglm52:
    display_name: GLM-5.2
    pricing_profiles:
      - id: 2026-07-30-default
        effective_from: 2026-07-30
        currency: CNY
        unit_tokens: 1000000
        tiers:
          - id: default
            input_uncached: 8
            input_cached: 2
            output: 28
  xsparkx2agent:
    display_name: Spark-X2-300B
    pricing_profiles:
      - id: 2026-07-30-default
        effective_from: 2026-07-30
        currency: CNY
        unit_tokens: 1000000
        tiers:
          - id: default
            input_uncached: 4
            input_cached: 0.8
            output: 15
harnesses:
  astroncode:
    display_name: AstronCode
    family: Codex
  opencode:
    display_name: OpenCode
    family: OpenCode
```

- [ ] **Step 4: Implement the registry loader**

Implement immutable records and date selection in `report_entities.py`:

```python
@dataclass(frozen=True)
class PricingTier:
    tier_id: str
    input_uncached: Decimal
    input_cached: Decimal
    output: Decimal
    min_input_tokens_per_request: int | None = None
    max_input_tokens_per_request: int | None = None

@dataclass(frozen=True)
class PricingProfile:
    profile_id: str
    effective_from: date
    currency: str
    unit_tokens: int
    tiers: tuple[PricingTier, ...]

@dataclass(frozen=True)
class EntityRegistry:
    models: Mapping[str, Mapping[str, Any]]
    harnesses: Mapping[str, Mapping[str, Any]]
    exchange_rates: Mapping[str, tuple[Mapping[str, Any], ...]]

    def model_display(self, model_id: str) -> str:
        return self._display(self.models, "model", model_id)

    def harness_display(self, harness_id: str) -> str:
        return self._display(self.harnesses, "harness", harness_id)

    def _display(self, entities, entity_type: str, entity_id: str) -> str:
        item = entities.get(entity_id) or {}
        value = str(item.get("display_name") or "").strip()
        if value:
            return value
        LOGGER.warning("%s %s 缺少 display_name，回退原始 ID", entity_type, entity_id)
        return entity_id

def load_registry(path: Path) -> EntityRegistry:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if data.get("schema_version") != 1:
        raise ValueError(f"不支持的 entities schema_version: {data.get('schema_version')}")
    return EntityRegistry(
        models=data.get("models") or {},
        harnesses=data.get("harnesses") or {},
        exchange_rates={
            currency: tuple(records) for currency, records in
            (data.get("exchange_rates") or {}).items()
        },
    )
```

Add `pricing_profile(model_id, pricing_date)` and `cny_per_usd(pricing_date)` methods that parse ISO dates, select the single latest `effective_from <= pricing_date`, and reject duplicate same-day records or missing applicable profiles. Parse every price with `Decimal(str(value))`.

- [ ] **Step 5: Run registry tests and commit**

Run the three tests from Step 2, then:

```bash
git add tools/report/data/entities.yaml tools/report/scripts/report_entities.py tools/report/tests/test_analysis_pipeline.py
git commit -m "feat(report): 增加评测实体注册表"
```

### Task 2: Cost Normalization and Estimation

**Files:**
- Modify: `tools/report/scripts/report_entities.py`
- Modify: `tools/report/tests/test_analysis_pipeline.py`

- [ ] **Step 1: Write failing cost tests**

Add exact arithmetic tests for both usage schemas, CNY conversion, GPT tiers and missing cache-write pricing:

```python
def test_cost_normalizes_astroncode_and_opencode_usage(self) -> None:
    astron = report_entities.normalize_billable_usage({
        "input_tokens": 1000, "cache_read_tokens": 600,
        "cache_write_tokens": 0, "output_tokens": 100, "total_tokens": 1100,
    })
    opencode = report_entities.normalize_billable_usage({
        "input_tokens": 400, "cache_read_tokens": 600,
        "cache_write_tokens": 0, "output_tokens": 100, "total_tokens": 1100,
    })
    self.assertEqual(astron, report_entities.BillableUsage(400, 600, 0, 100))
    self.assertEqual(opencode, report_entities.BillableUsage(400, 600, 0, 100))

def test_cost_converts_glm_and_spark_from_cny(self) -> None:
    registry = report_entities.load_registry(REPORT_DIR / "data/entities.yaml")
    usage = report_entities.BillableUsage(400, 600, 0, 100)
    glm = report_entities.estimate_cost_usd(
        registry, "xopglm52", date(2026, 7, 30), usage, request_input_tokens=None
    )
    spark = report_entities.estimate_cost_usd(
        registry, "xsparkx2agent", date(2026, 7, 30), usage, request_input_tokens=None
    )
    self.assertAlmostEqual(float(glm.usd), 0.0072 / 6.77, places=10)
    self.assertAlmostEqual(float(spark.usd), 0.00358 / 6.77, places=10)

def test_gpt_cost_uses_each_request_context_tier(self) -> None:
    registry = report_entities.load_registry(REPORT_DIR / "data/entities.yaml")
    requests = [
        report_entities.RequestUsage(200000, 100000, 1000),
        report_entities.RequestUsage(300000, 100000, 1000),
    ]
    result = report_entities.estimate_request_costs_usd(
        registry, "gpt-5.5", date(2026, 7, 30), requests
    )
    expected = (100000 * 5 + 100000 * 0.5 + 1000 * 30
                + 200000 * 10 + 100000 * 1 + 1000 * 45) / 1_000_000
    self.assertAlmostEqual(float(result.usd), expected)
```

- [ ] **Step 2: Run cost tests and verify RED**

Run:

```bash
python3 -m unittest \
  tools.report.tests.test_analysis_pipeline.AnalysisPipelineTest.test_cost_normalizes_astroncode_and_opencode_usage \
  tools.report.tests.test_analysis_pipeline.AnalysisPipelineTest.test_cost_converts_glm_and_spark_from_cny \
  tools.report.tests.test_analysis_pipeline.AnalysisPipelineTest.test_gpt_cost_uses_each_request_context_tier -v
```

Expected: missing `BillableUsage`, `RequestUsage`, normalization and estimation symbols.

- [ ] **Step 3: Implement normalization and estimators**

Use `Decimal(str(value))` for prices and FX. Detect usage semantics using total-token invariants:

```python
@dataclass(frozen=True)
class BillableUsage:
    input_uncached_tokens: int
    input_cached_tokens: int
    cache_write_tokens: int
    output_tokens: int

@dataclass(frozen=True)
class RequestUsage:
    input_uncached_tokens: int
    input_cached_tokens: int
    output_tokens: int
    cache_write_tokens: int = 0

@dataclass(frozen=True)
class CostEstimate:
    usd: Decimal | None
    profile_id: str | None
    status: str
    reason: str = ""

def normalize_billable_usage(usage: Mapping[str, Any]) -> BillableUsage:
    input_tokens = int(usage.get("input_tokens") or 0)
    cached = int(usage.get("cache_read_tokens") or 0)
    cache_write = int(usage.get("cache_write_tokens") or 0)
    output = int(usage.get("output_tokens") or 0)
    total = int(usage.get("total_tokens") or 0)
    if total == input_tokens + output:
        uncached = input_tokens - cached - cache_write
    elif total == input_tokens + cached + cache_write + output:
        uncached = input_tokens
    else:
        raise ValueError("无法判断 usage.json 的 input_tokens 缓存语义")
    if uncached < 0:
        raise ValueError("缓存 token 超过输入 token")
    return BillableUsage(uncached, cached, cache_write, output)
```

Implement `estimate_cost_usd(registry, model_id, pricing_date, usage, request_input_tokens) -> CostEstimate` for single-tier aggregate usage and `estimate_request_costs_usd(registry, model_id, pricing_date, requests) -> CostEstimate` for tiered request usage. For tiered GPT pricing, require request-level input/cache/output and select exactly one tier for every request. If cache-write tokens are nonzero and the tier has no cache-write price, return `CostEstimate(None, profile_id, "unavailable", "缺少缓存写入单价")` rather than zero.

- [ ] **Step 4: Implement request-level readers**

Add `extract_astroncode_requests(run_dir: Path) -> list[RequestUsage]` and `extract_opencode_requests(run_dir: Path) -> list[RequestUsage]`. The AstronCode reader must parse each JSONL object, select `payload.type == "token_count"`, take `payload.info.last_token_usage`, de-duplicate identical cumulative events, and compute uncached input as `input_tokens - cached_input_tokens`. The OpenCode reader must query `part.data` rows with JSON type `step-finish`, treat `tokens.input` as uncached, `tokens.cache.read` as cached, and add `tokens.reasoning` to `tokens.output`. Both readers return records in event order and raise a descriptive error when a token count is negative.

- [ ] **Step 5: Add raw-reader fixtures and pass tests**

Create one temporary AstronCode JSONL with two `token_count` events and one SQLite OpenCode `part` table with two `step-finish` rows. Verify both readers produce identical normalized requests. Run all Task 2 tests.

- [ ] **Step 6: Commit the cost engine**

```bash
git add tools/report/scripts/report_entities.py tools/report/tests/test_analysis_pipeline.py
git commit -m "feat(report): 增加评测成本重算"
```

### Task 3: Integrate Display Names, Pricing and Metadata

**Files:**
- Modify: `tools/report/scripts/generate_eval_report.py`
- Modify: `tools/report/tests/test_analysis_pipeline.py`

- [ ] **Step 1: Write failing CLI and workbook tests**

Add a helper that creates a 2-model × 2-Harness fixture, then test:

```python
def test_excel_uses_display_names_and_preserves_raw_identity(self) -> None:
    excel_path = self.generate_comparison_excel()
    wb = load_workbook(excel_path, data_only=True)
    overview = wb["总览"]
    headers = [cell.value for cell in overview[1]]
    models = {overview.cell(row, headers.index("模型") + 1).value
              for row in range(2, overview.max_row + 1)}
    self.assertIn("GPT-5.5", models)
    self.assertIn("Spark-X2-300B", models)
    self.assertEqual(wb["_报告元数据"].sheet_state, "hidden")
    self.assertIn("xsparkx2agent@astroncode", {
        wb["_报告元数据"].cell(row, 2).value
        for row in range(2, wb["_报告元数据"].max_row + 1)
    })

def test_excel_recomputes_nonzero_costs(self) -> None:
    excel_path = self.generate_comparison_excel()
    wb = load_workbook(excel_path, data_only=True)
    overview = wb["总览"]
    headers = [cell.value for cell in overview[1]]
    cost_col = headers.index("总成本(USD)") + 1
    self.assertTrue(all(overview.cell(row, cost_col).value > 0
                        for row in range(2, overview.max_row + 1)))
```

The test command must pass `--entities`, `--pricing-date 2026-07-30`, `--target-model` and `--target-harness`.

- [ ] **Step 2: Run integration tests and verify RED**

Expected: CLI rejects new arguments and workbook contains raw labels/zero costs/no metadata Sheet.

- [ ] **Step 3: Add CLI validation and raw/display properties**

Add arguments:

```python
ap.add_argument("--target-model")
ap.add_argument("--target-harness")
ap.add_argument("--entities", default=str(DEFAULT_ENTITIES_PATH))
ap.add_argument("--pricing-date", type=date.fromisoformat)
```

Load the registry before creating `UnitResult`. Keep `UnitResult.unit` raw and add `model_display`, `harness_display`, `unit_display`. Fail if only one target argument is supplied, if the target unit is absent after filtering, or if pricing is requested without a date.

- [ ] **Step 4: Integrate estimated cost**

Pass `model` and pricing context to `TaskRecord`. Store `estimated_cost_usd` and `cost_status` without changing `self.usage`. Add `UnitResult.estimated_cost_total()` that returns `None` when any nonzero-usage task is unpriced. In `write_overview_sheet`, replace `u.usage_total("cost_usd")` with the estimated total; write `"-"` for unavailable cost.

- [ ] **Step 5: Replace outward labels without changing raw keys**

Update all outward cells in overview, matrix, tool comparison, case comparison, capability, dimension, diff, stability and emitted summary to use display labels. Continue to use raw `u.unit` for dictionaries, analysis lookup and detail Sheet names. Add explicit `unit_id` fields beside display `run_label` in emitted summary JSON.

- [ ] **Step 6: Write hidden metadata Sheet**

Add `write_report_metadata_sheet` with rows for model, Harness, unit, target, pricing profile, FX rate/date and cost status. Keep stable columns:

```text
类型 | 原始ID | 展示名称 | 属性 | 值
```

Set `ws.sheet_state = "hidden"` after writing. Use this Sheet as the machine-readable bridge for the audit and extractor.

- [ ] **Step 7: Run focused and existing tests**

Run Task 3 tests, then:

```bash
python3 -m unittest tools.report.tests.test_analysis_pipeline -v
```

Expected: existing raw-ID detail backfill tests still pass; unknown fixture IDs fall back with warnings.

- [ ] **Step 8: Commit integration**

```bash
git add tools/report/scripts/generate_eval_report.py tools/report/tests/test_analysis_pipeline.py
git commit -m "feat(report): 集成展示名与成本元数据"
```

### Task 4: Add Copy-Ready Controlled Views

**Files:**
- Modify: `tools/report/scripts/generate_eval_report.py`
- Modify: `tools/report/tests/test_analysis_pipeline.py`

- [ ] **Step 1: Write failing controlled-view tests**

For the 2×2 fixture, assert each of the five dimension Sheets contains both titles below the original table and exact row scopes:

```python
def test_dimension_sheets_append_two_controlled_views(self) -> None:
    wb = load_workbook(self.generate_comparison_excel(), data_only=True)
    for title in ("分类对比", "Agent能力对比", "Agent能力对比·去污染", "难度对比", "模态对比"):
        ws = wb[title]
        values = [ws.cell(row, 1).value for row in range(1, ws.max_row + 1)]
        self.assertIn("固定 AstronCode：模型对比", values)
        self.assertIn("固定 Spark-X2-300B：Harness 对比", values)

def test_overview_keeps_all_existing_columns(self) -> None:
    wb = load_workbook(self.generate_comparison_excel(), data_only=True)
    self.assertEqual(
        [cell.value for cell in wb["总览"][1]],
        ["模型", "Harness", "总平均分", "用例数", "正常完成数", "执行错误数",
         "超时数", "评测异常数", "完成率", "总tokens", "总请求数", "总耗时(s)",
         "总成本(USD)"],
    )
```

Account for optional multirun/tool columns by deriving the expected existing header in the fixture; do not hard-code removal of optional columns.

- [ ] **Step 2: Run view tests and verify RED**

Expected: controlled-view titles are absent.

- [ ] **Step 3: Implement a generic append helper**

Add the exact helper signature `append_controlled_views(ws, units, value_headers, values_by_raw_unit, target_model, target_harness) -> None`.

The helper must:

- leave rows 1 through the original table end untouched;
- add two blank rows before each section;
- write model view rows where `u.harness == target_harness`;
- write Harness view rows where `u.model == target_model`;
- use first-column headers `模型` and `Harness`;
- apply the existing header style, percentage format and red-yellow-green color scale;
- bold the target row and shade only its first cell so numeric conditional colors remain visible;
- emit a warning and omit a view with fewer than two comparison rows.

- [ ] **Step 4: Integrate all five dimension Sheets**

Refactor `write_capability_sheet` and `write_dimension_sheet_transposed` to retain `values_by_raw_unit`, then call `append_controlled_views` for raw Agent dimensions, decontaminated Agent dimensions, category, difficulty and modality.

- [ ] **Step 5: Align workbook order with the leader report**

After all Sheets are created, reorder only the report-facing prefix to:

```python
REPORT_SHEET_ORDER = [
    "总览", "分类对比", "Agent能力对比", "Agent能力对比·去污染",
    "难度对比", "模态对比",
]
```

Append all diagnostic/detail Sheets afterward without changing their names.

- [ ] **Step 6: Verify styles and commit**

Load the workbook without `read_only`, assert conditional formatting ranges cover both appended tables, target first cells are filled, and original `A1` headers remain unchanged. Run the full report test module, then commit:

```bash
git add tools/report/scripts/generate_eval_report.py tools/report/tests/test_analysis_pipeline.py
git commit -m "feat(report): 增加控制变量复制视图"
```

### Task 5: Scope-Aware Validation, Audit and Leader Data Extraction

**Files:**
- Modify: `tools/report/skills/validate-eval-results/scripts/validate_eval_results.py`
- Modify: `tools/report/skills/audit-eval-report/scripts/audit_eval_report.py`
- Create: `tools/report/skills/eval-report/scripts/extract_leader_report_data.py`
- Modify: `tools/report/tests/test_analysis_pipeline.py`

- [ ] **Step 1: Write failing scope and audit tests**

Add tests that validate/audit only selected models and Harnesses from a three-level fixture. Add an audit test where Excel uses display labels and raw results use IDs; expect no unit-set mismatch. Add a cost tampering test that changes `总成本(USD)` and expects `OVERVIEW_COST_MISMATCH`.

- [ ] **Step 2: Add `--models` and `--harnesses` to validity and audit**

Filter discovered specs immediately after discovery, using the same raw-ID semantics as the Excel script. Include selected models/Harnesses in validity/audit output metadata. Fail when the filter yields no units.

- [ ] **Step 3: Teach audit to resolve display labels**

Read `_报告元数据` into three maps: model display → raw ID, Harness display → raw ID, unit display → raw unit. Apply these maps in overview, matrix, case comparison, capability, dimension and diff audits. Keep detail Sheet lookup raw because detail names remain unchanged.

- [ ] **Step 4: Independently audit costs**

Use the shared registry parser and raw request readers, but independently sum each unit in `audit_eval_report.py`; do not call `generate_eval_report.py` aggregation functions. Compare with `总成本(USD)` using a `0.0001` absolute tolerance. Record profile ID, FX and recomputed amount in evidence.

- [ ] **Step 5: Write failing extractor test**

The extractor test should call:

```python
payload = leader_extract.extract_workbook(excel_path)
self.assertEqual(payload["target"]["unit_display"], "Spark-X2-300B@AstronCode")
self.assertEqual(payload["overview"][0]["模型"], "GPT-5.5")
self.assertEqual(
    {row["模型"] for row in payload["dimensions"]["分类对比"]["model_view"]},
    {"GPT-5.5", "Spark-X2-300B"},
)
```

- [ ] **Step 6: Implement the openpyxl extractor**

Read headers by name, not column number. Read the original total overview from row 1. Locate controlled views by exact title cells, read the next row as headers and stop at the first blank row. Output UTF-8 JSON containing target metadata, pricing snapshot, overview, category, Agent raw/decontaminated, difficulty and modality.

CLI:

```bash
EXCEL_PATH=$(find /Users/gzx/Project/GitHub/xgz/ai/evaluate/WildClawBench/eval_out/all_suite/round3_t3600/report-workspace/output \
  -maxdepth 1 -type f -name 'report_6units_*.xlsx' | sort | tail -1)
LEADER_DATA_PATH="${EXCEL_PATH%.xlsx}_leader_data.json"
python3 tools/report/skills/eval-report/scripts/extract_leader_report_data.py \
  --excel "$EXCEL_PATH" --output "$LEADER_DATA_PATH"
```

- [ ] **Step 7: Run tests and commit**

```bash
python3 -m unittest tools.report.tests.test_analysis_pipeline -v
git add tools/report/skills/validate-eval-results/scripts/validate_eval_results.py \
        tools/report/skills/audit-eval-report/scripts/audit_eval_report.py \
        tools/report/skills/eval-report/scripts/extract_leader_report_data.py \
        tools/report/tests/test_analysis_pipeline.py
git commit -m "feat(report): 增加报告范围审核与数据提取"
```

### Task 6: Update the Eval Report Skill and Template

**Files:**
- Modify: `tools/report/skills/eval-report/SKILL.md`
- Modify: `tools/report/skills/eval-report/references/report_template.md`
- Modify: `tools/report/README.md`
- Modify: `tools/report/tests/test_analysis_pipeline.py`

- [ ] **Step 1: Run a baseline pressure scenario before editing the Skill**

Using a fresh subagent without the modified Skill body, provide a six-unit summary and ask for a leader report. Record whether it emits a full model×Harness matrix, includes an L3/L4 typical case, omits pricing disclosure or writes generic recommendations. Save the observed failures in the working notes; do not add generated notes to the repository.

- [ ] **Step 2: Write failing Skill contract tests**

Add deterministic assertions that the Skill and template contain and order the required rules:

```python
def test_eval_report_skill_contract_for_controlled_views(self) -> None:
    skill = (REPORT_DIR / "skills/eval-report/SKILL.md").read_text(encoding="utf-8")
    self.assertLess(skill.index("分类维度"), skill.index("Agent能力"))
    self.assertIn("固定目标 Harness", skill)
    self.assertIn("固定目标模型", skill)
    self.assertIn("总览保留全部列", skill)
    self.assertIn("典型低分案例", skill)
    self.assertIn("L3/L4", skill)
    self.assertIn("不得进入典型低分案例", skill)
```

- [ ] **Step 3: Update `SKILL.md`**

Make these rules explicit and remove contradictory old text:

- required inputs: target model, target Harness, selected comparison scope, entities path and pricing date;
- Excel command includes all new arguments;
- leader data must come from `extract_leader_report_data.py` output;
- overview keeps every Excel overview column;
- chapter order is 总览 → 分类 → Agent → 难度 → 模态 → 典型案例 → 建议;
- each analysis dimension uses model view then Harness view and omits the full mixed matrix;
- each pre-table summary is at most two sentences/three key numbers and ends with an actionable direction;
- distinguish internal relative strength from industry competitiveness;
- correlation uses “优先排查”; confirmed causality requires transcript/root-cause evidence;
- pricing and FX are estimates with snapshot disclosure;
- L3/L4 remain internal validity categories, block PASS until closed, and never occupy typical low-score cases.

- [ ] **Step 4: Update the Markdown template and README**

The template must show both controlled-view subheadings in category, Agent, difficulty and modality. The overview table placeholder must say “全部 Excel 总览列”. Put classification immediately after overview. Add a short “成本口径” note and an optional “评测有效性与剔除说明” outside typical cases.

README examples must include `--target-model`, `--target-harness`, `--models`, `--harnesses`, `--entities` and `--pricing-date`.

- [ ] **Step 5: Re-run pressure scenario and contract tests**

Use a fresh subagent with the edited Skill. Expected behavior: two controlled views per dimension, no mixed matrix outside overview, no L3/L4 typical case, short evidence-led summaries and explicit cost caveat. Run the full unittest module.

- [ ] **Step 6: Commit Skill and documentation changes**

```bash
git add tools/report/skills/eval-report/SKILL.md \
        tools/report/skills/eval-report/references/report_template.md \
        tools/report/README.md tools/report/tests/test_analysis_pipeline.py
git commit -m "docs(report): 优化领导版报告生成规则"
```

### Task 7: End-to-End Verification and New Reports

**Files:**
- Generate: `eval_out/all_suite/round3_t3600/report-workspace/output/report_6units_*.xlsx`
- Generate: `eval_out/all_suite/round3_t3600/report-workspace/output/report_6units_*_leader_data.json`
- Generate: `eval_out/all_suite/round3_t3600/评测报告_Spark-X2-300B_AstronCode_round3_t3600_*.md`

- [ ] **Step 1: Run the full automated suite**

```bash
python3 -m unittest tools.report.tests.test_analysis_pipeline -v
```

Expected: all tests pass.

- [ ] **Step 2: Validate only the six requested units**

```bash
python3 tools/report/skills/validate-eval-results/scripts/validate_eval_results.py \
  --result-root /Users/gzx/Project/GitHub/xgz/ai/evaluate/WildClawBench/eval_out/all_suite/round3_t3600 \
  --models xsparkx2agent xopglm52 gpt-5.5 \
  --harnesses astroncode opencode \
  --fail-on never
```

Resolve every REVIEW item before publication; any confirmed L3/L4 score distortion requires rerun/regrade or explicit publication blocking.

- [ ] **Step 3: Generate a new Excel without overwriting old files**

```bash
python3 tools/report/scripts/generate_eval_report.py \
  --result-root /Users/gzx/Project/GitHub/xgz/ai/evaluate/WildClawBench/eval_out/all_suite/round3_t3600 \
  --models xsparkx2agent xopglm52 gpt-5.5 \
  --harnesses astroncode opencode \
  --target-model xsparkx2agent \
  --target-harness astroncode \
  --entities tools/report/data/entities.yaml \
  --pricing-date 2026-07-30 \
  --analysis \
    "xsparkx2agent@astroncode=/Users/gzx/Project/GitHub/xgz/ai/evaluate/WildClawBench/eval_out/all_suite/round3_t3600/astroncode/report-workspace/analysis_xsparkx2agent@astroncode.json" \
    "xsparkx2agent@opencode=/Users/gzx/Project/GitHub/xgz/ai/evaluate/WildClawBench/eval_out/all_suite/round3_t3600/opencode/report-workspace/analysis_xsparkx2agent@opencode__all.json"
```

Expected: a new `report_6units_*.xlsx` under the round workspace. Record the exact path printed by the command.

- [ ] **Step 4: Extract leader data and inspect workbook structure**

Run the extractor against the exact new workbook. Verify:

- overview headers and values include every original column;
- all visible names are friendly names;
- every unit cost is nonzero and metadata records the profile/FX;
- five dimension Sheets each contain two colored controlled views;
- raw table `A1` headers remain unchanged;
- target first cells are emphasized and conditional color scales cover numeric ranges.

- [ ] **Step 5: Generate the leader Markdown from extracted JSON**

Follow the edited `eval-report` Skill. Use Spark-X2-300B@AstronCode as target, preserve all overview columns, and write category before Agent. Each dimension must contain model-side and Harness-side conclusions and tables. Select 5–6 L1a/L1b/Harness cases only; put any unresolved validity issue in a separate disclosure or block publication.

- [ ] **Step 6: Run independent audit with the same scope**

```bash
python3 tools/report/skills/audit-eval-report/scripts/audit_eval_report.py \
  --result-root /Users/gzx/Project/GitHub/xgz/ai/evaluate/WildClawBench/eval_out/all_suite/round3_t3600 \
  --excel "$EXCEL_PATH" \
  --models xsparkx2agent xopglm52 gpt-5.5 \
  --harnesses astroncode opencode \
  --entities tools/report/data/entities.yaml \
  --pricing-date 2026-07-30 \
  --validity /Users/gzx/Project/GitHub/xgz/ai/evaluate/WildClawBench/eval_out/all_suite/round3_t3600/report-workspace/validity/eval_result_validity.json \
  --fail-on never
```

Expected: no automatic `FAIL`; all REVIEW items have recorded conclusions.

- [ ] **Step 7: Verify the spreadsheet visually**

Use the `spreadsheets:Spreadsheets` render/verify workflow to inspect all five dimension Sheets at practical zoom. Confirm no clipped headers, broken color scales, overlapping tables or hidden target rows. Manually copy one controlled view into a temporary Feishu document if available and verify colors/borders survive.

- [ ] **Step 8: Run completion verification and report status**

Invoke `superpowers:verification-before-completion`. Re-run the full tests, inspect `git status --short`, list the exact generated artifact paths, and do not claim PASS if validity/audit remains REVIEW or FAIL.

Do not commit generated `eval_out` artifacts unless the user explicitly requests it.
