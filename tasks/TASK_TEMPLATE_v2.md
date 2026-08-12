---
# ============================================================================
# WildClawBench Task Template v2 (规则 / LLM 分离格式)
# 适用：新自建评测集任务
# 兼容：与现存 v1 格式（LLM 内嵌 grade）同框架混跑，无冲突
# 参考：docs/local/design/混合评分拆分设计.md
# ============================================================================

# 字段与顺序对齐 WildClawBench 官方任务；category 实际以父目录名为准（frontmatter 仅说明）
id: 04_Search_Retrieval_task_101_example    # 任务标识；扩展集格式 <Category>_task_<N≥101>_<slug>
name: 示例混合任务                            # 任务名（报告展示）
category: 04_Search_Retrieval                # 所属大类（须与父目录名一致）
timeout_seconds: 180                         # 执行超时（秒）
modality: pure-text                          # 模态：pure-text | multimodal
difficulty: L2                               # 难度：L1 / L2 / L3 / L4
grading_type: hybrid                         # 必填：automated | llm_judge | hybrid
                                             #   automated：仅规则评分
                                             #   llm_judge：仅 LLM 评分（无规则检查）
                                             #   hybrid：规则 + LLM 混合（推荐）
grading_weights:                             # 仅 hybrid 生效；框架消费（不再埋在 grade 内）
  automated: 0.6                             # 规则权重（建议 0.5~0.7，视规则覆盖度）
  llm_judge: 0.4                             # LLM 权重（补充规则难量化的维度，与上者相加归一到 1.0）
tags:                                        # 可选：筛选标签（parser 会小写去重），官方任务多不填
  - custom
---

# 任务标题（与 name 一致或更详细）

## Prompt

请分析 `/workspace/sales_data.csv` 中的销售数据，找出 2024 年 Q1 销售额最高的前 3 个产品，
将结果保存到 `/workspace/top_products.md`，格式为：

```
# 2024 Q1 销售 Top 3
1. 产品名 - ¥金额
2. ...
3. ...
```

## Expected Behavior

Agent 应该：
1. 读取并解析 CSV 文件（需处理可能的编码/格式问题）
2. 筛选 2024 年 Q1 数据（1 月 1 日~3 月 31 日）
3. 按产品聚合销售额，排序取 Top 3
4. 生成符合格式的 Markdown 报告

## Grading Criteria

### 规则部分（可量化检查点）
- **文件生成**：`top_products.md` 存在且非空
- **格式正确**：含标题行 `# 2024 Q1 销售 Top 3`、3 个列表项
- **数据准确**：Top 3 产品 ID 与参考答案匹配（允许金额小数点误差 ±0.01）

### LLM 部分（主观质量维度）
- **筛选正确性**：是否正确识别并筛选 Q1 时间范围（可能有日期格式变体）
- **聚合准确性**：是否正确处理同产品多条记录的汇总
- **鲁棒性**：是否处理了 CSV 脏数据（缺失值、异常格式）

> **可选执行章节填写规则**
> - `## Automated Checks` 不涉及时必须保留标题并将正文置空；仅 `automated`、`hybrid` 任务填写可执行的 Python `grade()`。
> - `## Skills` 不涉及时必须保留标题并将正文置空；仅填写仓库中实际存在且任务确实需要预置的 Skill。
> - `## Warmup` 不涉及时必须保留标题并将正文置空；仅填写可直接成功执行的 shell 命令。
> - “正文置空”是指章节标题后直接出现下一个 `##` 标题；禁止填写 `无`、`N/A`、说明文字、注释或空代码块，否则这些内容仍会被解析为真实配置或可执行内容。

## Automated Checks

**约定**：
- 本段**只做规则检查**（文件存在性、字段值、关键词、mock audit），禁止 `import openai` 调用 LLM。
- 函数签名：`def grade(transcript: list, workspace_path: str) -> dict`
- 返回：`{stable_key: 0~1 浮点分}`，key 名稳定（任务内唯一），供能力映射引用。
- `transcript` 为 agent 执行记录列表（每项是 `{type, message, ...}`），可用于工具调用审计。
- 所有规则检查点**独立计分**，不在此段内做加权（权重由 `grading_weights.automated` 统一控制）。

```python
def grade(transcript: list, workspace_path: str) -> dict:
    """规则检查点：文件、格式、数据准确性。"""
    from pathlib import Path
    import re
    
    scores = {}
    workspace = Path(workspace_path)
    output_file = workspace / "top_products.md"
    
    # 检查点 1：文件生成
    if not output_file.exists():
        return {
            "file_created": 0.0,
            "format_valid": 0.0,
            "data_accuracy": 0.0,
        }
    scores["file_created"] = 1.0
    
    content = output_file.read_text(encoding="utf-8", errors="ignore")
    
    # 检查点 2：格式正确性
    has_title = "# 2024 Q1 销售 Top 3" in content or "2024 Q1" in content
    list_items = re.findall(r"^\d+\.\s+", content, re.MULTILINE)
    scores["format_valid"] = 1.0 if has_title and len(list_items) >= 3 else 0.5 if has_title or list_items else 0.0
    
    # 检查点 3：数据准确性（Top 3 产品 ID 匹配参考答案）
    # 参考答案（由任务作者预先计算或标注）：P_001, P_042, P_018
    expected = ["P_001", "P_042", "P_018"]
    found = [pid for pid in expected if pid in content]
    scores["data_accuracy"] = len(found) / 3.0  # 匹配 3 个得满分，2 个得 0.67，依此类推
    
    return scores
```

## LLM Judge Rubric

**约定**：
- 本段**纯声明式 Markdown**，无 Python 代码；judge 调用由框架统一负责。
- 每个 criterion **必须显式声明 `key` 和 `weight`**（标题格式：`### Criterion N: 名称 (key: stable_key, weight: 0.X)`）。
- `key` 任务内唯一（kebab-case 或 snake_case），供能力映射与 breakdown 稳定引用。
- `weight` 在 rubric 内归一（如 3 个 criterion 权重 0.5/0.3/0.2，相加为 1.0），
  rubric 段整体权重由 frontmatter `grading_weights.llm_judge` 决定。
- 每个 criterion 提供**离散档位**（推荐 1.0 / 0.75 / 0.5 / 0.25 / 0.0，或 1.0 / 0.5 / 0.0），
  档位描述需**具体可判**（avoid "大致正确"等模糊表述）。

### Criterion 1: 时间筛选正确性 (key: time_filtering, weight: 0.4)

判据：agent 是否正确识别并筛选 2024 年 Q1（1 月 1 日~3 月 31 日）数据，包括处理日期格式变体。

**Score 1.0**: 明确筛选了 Q1 时间范围，transcript 或输出中体现日期条件（如 `date >= 2024-01-01 AND date <= 2024-03-31`）。

**Score 0.75**: 筛选了大致正确的时间范围，但边界有小偏差（如漏掉 3 月 31 日或多算了 4 月 1 日）。

**Score 0.5**: 筛选了"2024 年"数据但未明确 Q1，或用"前 3 个月"但未锚定起点。

**Score 0.25**: 尝试筛选时间但逻辑错误（如用月份名而非数值、年份错误）。

**Score 0.0**: 未做时间筛选，直接对全量数据排序。

### Criterion 2: 聚合准确性 (key: aggregation_accuracy, weight: 0.35)

判据：agent 是否正确处理同产品多条记录的汇总（groupby + sum），避免重复计数或遗漏。

**Score 1.0**: 明确对产品 ID 做聚合（transcript 中有 `groupby`、`sum` 或等价操作），逻辑正确。

**Score 0.75**: 聚合逻辑基本正确但有瑕疵（如先排序再去重，可能漏掉部分记录）。

**Score 0.5**: 尝试聚合但方法不当（如只取每个产品的第一条记录）。

**Score 0.0**: 未做聚合，直接按单条记录排序（数据准确性必然错误）。

### Criterion 3: 鲁棒性 (key: robustness, weight: 0.25)

判据：agent 是否处理了 CSV 脏数据（缺失值、格式异常、编码问题），避免执行中断。

**Score 1.0**: 明确处理了至少 2 种异常（如 `dropna()`、`try-except`、编码声明），transcript 或代码中可见。

**Score 0.5**: 处理了部分异常（如只处理缺失值，未处理编码），或异常处理覆盖不全。

**Score 0.0**: 未做任何异常处理，遇到脏数据时执行报错或结果异常。

## Workspace Path

```
workspace/extension/04_Search_Retrieval/task_101_example
```

## Skills

## Env

```
# 可选：任务所需环境变量（agent 执行时可见）
# 示例：
# OPENROUTER_API_KEY
# REFERENCE_DATA_PATH=/tmp/reference.json
```

## Warmup

## Additional Notes

- 选择混合评分的理由：规则可精确验证数据准确性（Top 3 产品 ID），LLM 补充评估过程质量（筛选/聚合逻辑、鲁棒性）。
- 参考答案生成方式：用 pandas 预处理 `sales_data.csv` 得到 ground truth Top 3。
- 常见失败模式：agent 未正确解析 CSV 列名、日期格式识别错误、聚合时漏掉部分记录。
- `Skills` 示例（仅在对应 Skill 已存在时填写）：`data_analysis`、`csv_processing`。
- `Warmup` 示例（仅在任务确实需要预热时填写）：`python3 /tmp_workspace/setup_mock_db.py`。
