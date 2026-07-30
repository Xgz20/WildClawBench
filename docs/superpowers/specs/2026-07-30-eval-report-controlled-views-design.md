# WildClawBench 评测报告展示名与控制变量视图设计

## 决策摘要

本次改造同时调整 Excel 报告生成脚本和 `eval-report` Skill：

- 模型与 Harness 的内部 ID 保持不变，对外统一显示可维护的友好名称。
- Excel 原始全量表保持在各 Sheet 顶部，在维度 Sheet 下方追加两张带配色的控制变量表。
- 领导版 Markdown 的总览保留 Excel 总览的全部列；分类、Agent 能力、难度、模态只展示两张控制变量表，不再展示同时改变模型与 Harness 的全量矩阵。
- 目标模型和目标 Harness 通过参数传入，不绑定当前验证数据。
- L3 评测环境和 L4 评测系统问题保留在内部根因分析中，但作为有效性门禁处理，不进入已发布报告的能力结论或典型低分案例。

验证范围使用 `round3_t3600` 中的 3 个模型、2 个 Harness，目标组合为 `xsparkx2agent@astroncode`。验证只生成新产物，不覆盖已有 Excel 或 Markdown。

## 现状与问题

`tools/report/scripts/generate_eval_report.py` 以原始目录名构造 `UnitResult.unit`，并直接将模型 ID、Harness ID 和 `<model>@<harness>` 写入总览、矩阵、能力、分类、难度、模态、工具调用、分差和用例明细等 Sheet。当前报告中的 `xopglm52`、`xsparkx2agent`、`astroncode` 等标识不适合对外阅读。

现有领导版 Markdown 按全量 unit 矩阵展示维度数据。同一张表同时改变模型与 Harness，无法直接回答两个改进问题：

- 固定目标 Harness 后，目标模型在哪些能力上落后，模型侧应优先补什么。
- 固定目标模型后，目标 Harness 相比其他 Harness 在哪里增益或退化，Harness 侧应优先排查什么。

Markdown 表格复制到飞书后不带 Excel 条件配色。现有人工流程会用 Excel 表格替换 Markdown 表格，因此 Excel 必须提供与 Markdown 结构一致、可直接复制的成品视图。

现有根因分析允许 L3/L4 归因，但发布规则没有明确区分“内部诊断分类”和“对外能力结论”。如果把评测环境或评测系统缺陷作为典型低分案例，会把无效评测结果误写成模型或 Harness 的改进方向。

## 目标与非目标

### 目标

- 对外输出友好名称，内部分析、回填和审计继续使用原始 ID。
- 通过目标参数稳定生成两类控制变量视图。
- Excel 视图可直接复制到飞书，保留表头、目标行强调和红黄绿条件配色。
- 领导版结论简短、证据明确，并分别指向模型侧或 Harness 侧改进。
- 分类维度移动到总览之后、Agent 能力之前。
- 明确 L3/L4 的发布门禁与案例选取规则。

### 非目标

- 不改变任务得分、能力映射、异常分类和得分聚合公式。
- 不改变 analysis JSON 的 unit 主键和 Excel 根因回填匹配规则。
- 不删除或重排总览中的现有列。
- 不回写历史 `usage.json`，不修改各 Harness runner 的在线计费逻辑。
- 不覆盖验证目录中的历史报告。
- 不把领导版 Markdown 完全改造成固定模板生成器；需要判断的评语和建议仍由 Skill 基于数据与证据撰写。

## 实体元数据与展示名设计

新增版本化实体注册表 `tools/report/data/entities.yaml`。YAML 不是限制，注册表使用嵌套结构避免 `id -> name` 扁平映射在新增属性时发生破坏性升级：

```yaml
schema_version: 1

exchange_rates:
  CNY:
    - effective_from: 2026-07-30
      cny_per_usd: 6.77
      source: Morningstar via Google

models:
  gpt-5.5:
    display_name: GPT-5.5
    vendor: OpenAI
    aliases: []
    capabilities:
      supported_reasoning_efforts: []
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
    vendor: Zhipu AI
    aliases: []
    capabilities:
      supported_reasoning_efforts: []
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
    vendor: Spark
    aliases: []
    capabilities:
      supported_reasoning_efforts: []
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
    aliases: []
    capabilities: {}
  opencode:
    display_name: OpenCode
    family: OpenCode
    aliases: []
    capabilities: {}
```

本次报告脚本读取 `schema_version`、`display_name`、`pricing_profiles` 和 `exchange_rates`。其他字段允许缺省，不迁移各 Harness runner 的在线成本计算和思考强度逻辑。后续扩展遵循以下边界：

- `vendor`、别名、模型支持的思考强度等稳定描述可放实体注册表。
- 本轮实际使用的思考强度属于运行时事实，必须记录在 `execution_status.json` 或 run 元数据中，不能从静态注册表推断。
- Token 单价可能随供应商、路由和时间变化。每个定价档案必须包含稳定 ID、`effective_from`、`currency`、计价单位及输入、输出、缓存单价；已知供应商时补充 `provider`。禁止维护无生效时间的单一固定价格。
- Harness 的家族、别名和稳定能力可放注册表；Harness 版本仍以运行结果中的 `harness_version` 为准。

脚本启动时加载实体注册表。模型、Harness 和 unit 均提供原始标识与展示标识：

- `model`、`harness`、`unit`：内部主键，保持原值。
- `model_display`、`harness_display`、`unit_display`：写入对外单元格。
- Harness 版本继续追加在友好名称后，例如 `OpenCode (1.18.4)`。

实体缺失、实体没有 `display_name` 或注册表版本不受支持时执行明确校验。未知实体回退原始 ID 并打印警告，报告生成不中断；未知 ID 不允许被自动格式化或猜测名称。Schema 版本不受支持时直接报错，避免静默误读新结构。

### 本轮定价快照

本轮使用以下单价，单位均为每百万 tokens：

| 模型 | 币种 | 未缓存输入 | 缓存输入 | 输出 | 上下文档位 |
|---|---|---:|---:|---:|---|
| GPT-5.5 | USD | 5 | 0.5 | 30 | Short context，单请求输入不超过 272K |
| GPT-5.5 | USD | 10 | 1 | 45 | Long context，单请求输入超过 272K |
| GLM-5.2 | CNY | 8 | 2 | 28 | 单档 |
| Spark-X2-300B | CNY | 4 | 0.8 | 15 | 单档 |

人民币成本按 `1 USD = 6.77 CNY` 转换，汇率日期为 `2026-07-30`，来源为用户提供的 Morningstar/Google 汇率截图。换算结果保留完整精度参与汇总，只在 Excel 展示时四舍五入。

GPT-5.5 必须按请求选择上下文档位，不能根据单任务或整轮聚合 token 选择。验证数据中 AstronCode 单请求最大输入为 121,445 tokens，OpenCode 为 202,449 tokens，均使用 Short context 单价。

验证范围 360 份 `usage.json` 的 `cache_write_tokens` 均为 0。本轮定价没有缓存写入单价；未来出现非零缓存写入且配置未提供价格时，该 run 成本标记为不可计算并给出警告，不得按 0 处理。

新增隐藏 Sheet `_报告元数据`，记录类型、原始 ID、展示名称、unit 原始键和 unit 展示标签，供审计和问题追踪。Sheet 中的数据匹配、排序和 analysis 回填始终使用原始键，避免展示名变更破坏兼容性。

## 参数与范围

Excel 脚本新增：

```text
--target-model <raw-model-id>
--target-harness <raw-harness-id>
--entities <yaml-path>        # 可选，默认 tools/report/data/entities.yaml
--pricing-date <YYYY-MM-DD>   # 成本重算必填；本轮为 2026-07-30
```

`--models` 和 `--harnesses` 继续限定参评范围；目标参数只决定目标组合与控制变量视图。

定价档案选择 `effective_from <= pricing_date` 的最新版本；汇率同样选择不晚于 `pricing_date` 的最新版本。新增未来价格后，使用相同 `--pricing-date` 重生成历史报告仍应得到相同成本。存在多个同日档案、没有可用档案或日期格式非法时直接报错，不静默选择。

生成前执行以下校验：

- 目标模型、目标 Harness 及目标 unit 必须存在于过滤后的 unit 集合中，否则报错退出。
- 固定目标 Harness 的模型参照少于 2 个时给出警告，不生成模型对比结论。
- 固定目标模型的 Harness 参照少于 2 个时给出警告，不生成 Harness 对比结论。
- 目标参数缺失时保留现有 Excel 全量表生成能力，但不追加控制变量视图；`eval-report` Skill 生成领导版报告时必须传入目标参数。

## Excel 布局

### 总览

`总览` Sheet 保持现有全部列、列顺序、表头位置和指标口径。仅做以下调整：

- 模型和 Harness 改用友好名称。
- 目标组合所在行使用一致的强调样式。
- `总成本(USD)` 使用报告侧重算结果；原始 `usage.json.cost_usd` 为 0 时不再直接汇总为 0。
- 领导版 Markdown 总览逐列复制该表，不删减列。

总览不追加控制变量表，避免与现有全量总览重复。

### 成本计算

报告侧成本计算不修改原始结果文件。每个有效 run 先规范化为 `input_uncached_tokens`、`input_cached_tokens`、`cache_write_tokens` 和 `output_tokens`，再按模型定价档案计算：

```text
原币成本 = 未缓存输入 / 1M × 未缓存输入价
         + 缓存输入 / 1M × 缓存输入价
         + 输出 / 1M × 输出价
美元成本 = 原币成本 / cny_per_usd  # 仅 CNY
```

现有 Harness 的 `usage.json` 语义不同：AstronCode 的 `input_tokens` 包含缓存读取，OpenCode 的 `input_tokens` 不包含缓存读取。规范化逻辑必须依据总 token 恒等式和 Harness 原始逐请求数据校验，禁止对两个 Harness 直接套同一减法公式。

GPT-5.5 的上下文档位使用逐请求数据判定：AstronCode 读取 `chat.jsonl` 中的 `last_token_usage`，OpenCode 读取数据库 `part` 表中的 `step-finish.tokens`。如果 tiered pricing 模型缺少逐请求数据，成本显示 `-` 并警告，不能用聚合 token 猜测档位。

隐藏 `_报告元数据` Sheet 增加本次使用的定价档案 ID、汇率、汇率日期和成本计算状态，确保 Excel 中的美元金额可复算。Markdown 总览备注说明成本为按配置快照重算的估算值，不代表供应商最终账单。

### 维度 Sheet

以下 Sheet 保留顶部原始全量表，并在原表结束后空两行追加视图：

- `分类对比`
- `Agent能力对比`
- `Agent能力对比·去污染`
- `难度对比`
- `模态对比`

追加区域固定为：

1. `固定 <目标 Harness 展示名>：模型对比`
2. 对应模型控制变量表
3. 空两行
4. `固定 <目标模型展示名>：Harness 对比`
5. 对应 Harness 控制变量表

控制变量表复用原表的维度列、百分数格式和红黄绿条件色阶。第一列只展示发生变化的变量：模型对比表第一列为“模型”，Harness 对比表第一列为“Harness”。目标模型或目标 Harness 行使用粗体和浅色底纹，但不覆盖数值色阶。

原始全量表的第 1 行表头、筛选、冻结窗格和已有条件格式保持不变。追加表不改变审计脚本按第 1 行读取原始表的契约。

其他含模型或 Harness 的 Sheet 使用友好名称展示，但不改变结构。`评分详情_<unit>` 的 Sheet 名继续使用稳定的原始 unit 形式，避免 31 字符限制和重复名称；隐藏元数据提供展示名对应关系。

## 领导版 Markdown 结构

章节顺序固定为：

1. 总览
2. 分类维度分析
3. Agent 能力维度分析
4. 难度等级维度分析
5. 模态对比
6. 典型低分案例
7. 总结与改进建议

总览表保留 Excel 总览的全部列。分类、Agent 能力、难度、模态章节不再展示全量 unit 矩阵，每个维度按以下顺序输出：

1. 维度总判断。
2. 固定目标 Harness 的模型侧总结。
3. 模型控制变量表。
4. 固定目标模型的 Harness 侧总结。
5. Harness 控制变量表。
6. 必要的口径备注。

Agent 能力的原始 7 维表必须展示。去污染 3 维表在 Excel 中始终生成；只有去污染前后会改变强弱判断或改进优先级时，才进入领导版 Markdown，并紧邻对应控制变量表说明变化。

## 结论与文风规则

每个控制变量表上方的总结最多 2 句话、3 个关键数字，第一句直接给判断，第二句给改进方向或必要边界。

模型侧总结固定目标 Harness，回答目标模型的相对强项、主要短板和优先提升方向。必须区分：

- 目标模型内部得分最高的“相对强项”。
- 相比参照模型仍有明显差距、尚未形成竞争力的能力。

Harness 侧总结固定目标模型，使用跨 Harness 分差定位增益和损失。只有根因分析有直接证据时才能作确定性归因；仅凭分数相关性时使用“优先排查”，不能写成已确认原因。

分类和难度总结优先选择用例量大、分差大、对总分影响大的项目，不逐项复述整张表。改进建议应落到工具参数生成、工具结果解析、错误恢复、长程收敛、产物落盘和校验等可执行方向。

禁用空泛表达和机械套话，包括“持续优化”“进一步提升”“全面加强”“值得注意的是”“综上所述”等。禁用反问句、排比式总结和无证据的因果判断。

## L3/L4 与发布规则

L3（评测环境/共享基础设施）和 L4（任务、Grader、统计或评测框架）保留在内部逐用例根因分析中，用于发现评测有效性问题。它们不是模型或 Harness 的能力改进分类。

发布处理规则：

- 确认影响得分的 L3/L4 问题必须先修复并重跑或重新判分；旧 run 通过 `supersedes_run` 退出正式统计。
- 未闭环的 L3/L4 问题阻断报告 `PASS`。用户明确接受风险时，只能进入独立的“评测有效性与剔除说明”，并标注不计入模型/Harness能力判断。
- 典型低分案例默认只选模型能力、长程执行和 Harness 责任问题，不选择 L3/L4。
- 已修复的 L3/L4 可在有效性说明中简要记录处置，不占用典型低分案例名额。
- 模型专属视觉通道、模型 API、Harness 工具协议或 Harness 进程异常按实际责任归属，不因表面上表现为“环境/系统错误”而自动归入 L3/L4。

## Skill 调整

`tools/report/skills/eval-report/SKILL.md` 和 `references/report_template.md` 需要同步：

- 输入增加目标模型、目标 Harness 和实体注册表说明。
- Excel 命令示例必须传目标参数。
- 总览取数规则增加报告侧成本重算、定价快照和汇率备注。
- Sheet 列名权威表说明原始表仍在第 1 行，控制变量视图位于下方。
- Markdown 章节顺序改为总览、分类、Agent 能力、难度、模态。
- 各维度只提取两张控制变量表；总览保留全部列。
- 增加简短结论模板、模型侧/Harness 侧判断边界和禁用空话规则。
- 增加 L3/L4 发布门禁与典型案例排除规则。
- 发布前逐表核对 Markdown 与 Excel 控制变量视图，校验显示名、目标范围、数字和表格朝向。

## 测试与验收

### 自动测试

- 实体注册表加载：Schema 版本、已知实体、缺失 `display_name`、未知 ID 回退、警告和自定义配置路径。
- 定价配置：计价日期、档案选择、生效日期、币种、上下文档位、汇率和缺失缓存写入价格的失败路径。
- 成本规范化：AstronCode 输入包含缓存、OpenCode 输入不含缓存，两种语义均不重复计费。
- 成本计算：GPT-5.5 逐请求档位、GLM/Spark 人民币换算、任务到 unit 汇总和 Excel 四舍五入。
- 成本缺失：无价格、无逐请求 tier 证据或未知 token 语义时显示 `-` 而不是 0。
- 身份隔离：内部 `unit` 仍使用原始 ID，展示标签使用友好名称。
- 参数校验：目标 unit 缺失、模型参照不足、Harness 参照不足。
- 总览兼容：表头仍位于第 1 行，列名、顺序和数值与改造前一致。
- 控制变量视图：五个维度 Sheet 均生成两张表，行集分别满足固定目标 Harness 和固定目标模型。
- 样式：控制变量表存在百分比格式、条件色阶、目标行强调和可复制的连续区域。
- 元数据：隐藏 Sheet 可从展示标签追溯原始模型、Harness 和 unit。
- 审计兼容：原始 Sheet 的自动对账继续通过。

### 验证数据

使用：

```text
/Users/gzx/Project/GitHub/xgz/ai/evaluate/WildClawBench/eval_out/all_suite/round3_t3600
```

限定：

```text
models: xsparkx2agent, xopglm52, gpt-5.5
harnesses: astroncode, opencode
target: xsparkx2agent@astroncode
```

验收产物：

- 新时间戳 Excel，包含 6 个 unit，不覆盖已有文件。
- 新领导版 Markdown，以 `Spark-X2-300B@AstronCode` 为目标组合。
- Markdown 总览包含 Excel 总览全部列。
- 6 个 unit 的 `总成本(USD)` 为非零可复算值，人民币模型按 6.77 汇率转换；GPT-5.5 本轮全部使用 Short context 单价。
- 分类位于总览之后、Agent 能力之前。
- 四个分析维度均包含模型侧和 Harness 侧控制变量总结与表格。
- 典型低分案例不包含 L3/L4；有效性问题按门禁规则处理。
- 自动审计通过，Markdown 数字与最新 Excel 逐表一致。

## 关键取舍

采用“原表下方追加视图”，而不是新增多个视图 Sheet。这样人工复制时可以在对应维度 Sheet 内完成，同时保留原始全量矩阵。代价是 Sheet 纵向长度增加，但不会改变原始表头契约。

领导版分析维度不再放全量矩阵。完整数据仍在 Excel 顶部，领导版只保留能直接回答模型侧和 Harness 侧改进问题的控制变量表，减少重复和归因歧义。

L3/L4 不从内部分类中删除，因为删除会掩盖无效评测；它们通过有效性门禁从发布能力结论中隔离。

## 风险与回退

- 展示名遗漏会回退原始 ID 并告警，不影响数据生成；补充 YAML 后可重新生成。
- 定价或汇率缺失时成本显示 `-` 并阻止报告将其描述为零成本；补充实体注册表后可重新生成。
- 事后估算成本依赖价格快照，不等于供应商结算金额；Excel 元数据和 Markdown 备注必须披露单价、汇率与日期。
- 控制变量表追加逻辑若影响原始表读取，可临时关闭目标参数，恢复只生成全量表的兼容模式。
- Excel 条件格式复制到飞书的实际效果依赖飞书导入行为，验收时需人工复制至少一张宽表确认颜色和边框保留。
- 如果目标筛选后缺少完整的模型或 Harness 参照，不生成误导性结论，并在报告中说明对比范围不足。

当前没有待确认的设计问题。
