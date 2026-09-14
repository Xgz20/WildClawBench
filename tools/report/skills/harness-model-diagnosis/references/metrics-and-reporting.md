# 统计与报告脚本

以下命令在仓库根目录执行；用项目现有 Python 环境，替换示例中的路径和目标。只分析一个目标时省略另一目标参数。

## 建立 profile

```bash
.venv/bin/python tools/report/skills/harness-model-diagnosis/scripts/build_diagnosis_profile.py \
  --result-root <round> --target-harness <harness> --target-model <model> \
  --output <output-dir>/diagnosis_profile.json
```

默认 OR 证据面。要扫描选定全矩阵，追加：

```text
--evidence-scope selected-matrix --models model-a model-b model-c --harnesses harness-a harness-b harness-c
```

`--task-ids` 限制任务范围。`--source-dir` 可选，记录只读源码快照。不同 Harness 版本分组保留；缺少的矩阵格、无效评分和 discovery issues 均披露，不虚构齐全覆盖。输入若没有匹配 run，CLI 失败。

有效 run 选择沿用共享发现逻辑，旧异常快照按当前规则在内存复核；不改写原始日志或历史异常文件。本脚本的全量表示**所选当前有效 run**，不代表目录物理上的每个历史 run。

## 指标口径与缺失处理

- 分数先在任务内平均可用 run，再对任务等权；资源总量按选中 run 求和。报告给出两种分母及执行/有效性状态，不能以不同评分覆盖的均分直接排名。
- `usable`/评分可统计性不等于无异常；同时披露执行状态和 `PASS/REVIEW/FAIL` 异常判定，`capability_outcome` 与框架无效结果分开。旧 profile 缺少异常判定字段时显示 unknown，不反推 PASS。
- 输入可能含缓存或不含缓存：仅算术自洽时使用 `total - output` 作为含缓存输入。总 token = 含缓存输入 + 输出；reasoning 已包含在输出时不重复相加；缓存率 = 总 cache read / 总含缓存输入，不平均单任务比例。
- 缺失、负数、非有限数、bool、计数非整数、token 算术不一致均不是 0。完整总量为 null；`known_subtotal` 与覆盖分母单列，不能拿已知小计计算完整样本的增幅。非有限原值在 JSON 中写 null，原始文件保留并有指纹。实际记录的全零值仍是 0；分母为零时增幅不可算。
- 请求数是 Harness 的记录口径，不是思考轮数；工具数也不是请求数，日志事件数更不能跨 Harness 当轮数排名。
- `elapsed_time` 汇总是累计任务耗时，不是并发批次墙钟，也不等于模型推理时间。token 不等于费用，缓存、价格和生成耗时不同，零费用还可能是没配置定价。
- token/请求增加可能来自上下文增长、重试、探索、工具回包、压缩、任务复杂度等。先用调用轨迹拆解候选原因，不把全量差额归给少量工具失败。精确试错开销需要请求级 usage/时间戳；缺失则只报错误/恢复调用数和任务总量，不能补造精度。

## 通用配对与敏感性分析

```bash
.venv/bin/python tools/report/skills/harness-model-diagnosis/scripts/analyze_diagnosis.py \
  --profile <output-dir>/diagnosis_profile.json \
  --output <output-dir>/diagnosis_analysis.json
```

生成固定模型跨 Harness、固定 Harness 跨模型的对照，方向指向指定目标；`--target-unit 'model@harness[version]'` 可限制到某个实际 unit key。脚本不会自动生成双方模型和 Harness 都变化的对照。

按共同任务配对，记录两侧完整 run_id。同一单元/任务仍有多 run 时不任意挑一个：全量资源保留，配对切片排除并披露。缺少对侧任务也显式列出。

| 切片 | 含义 |
| --- | --- |
| all_paired | 所有可一对一匹配任务，包含异常执行；不自动剔除低分 |
| same_contract | 双方所有必要契约指纹完整且相同 |
| equal_score / both_perfect | 双方有效同分 / 同满分，用作资源观察与成功反例 |
| paired_finished | 双方状态均为 finished；不等于语义完成或评分有效 |
| without_explicit_tasks | `--exclude-task-ids` 指定任务同时从两侧排除 |
| without_elapsed_tails | 每一对按目标较高的耗时差选择前 N 个任务，同时排除；`--tail-count` 默认 3，设 0 可关闭 |

所有后验切片都只能说明关联。同分不代表全部产物质量等价；剔除长尾不是修复模拟；不能用某一个切片代替全样本。报告必须并列全量、配对覆盖和敏感性结果，注明输出上限/API/日期等混杂因素。不同版本即使在同 Harness 下也不能称严格控制变量。

## Markdown 交付

按证据规则人工填写 `diagnosis_findings.json` 后：

```bash
.venv/bin/python tools/report/skills/harness-model-diagnosis/scripts/render_diagnosis_report.py \
  --profile <output-dir>/diagnosis_profile.json \
  --analysis <output-dir>/diagnosis_analysis.json \
  --findings <output-dir>/diagnosis_findings.json \
  --output <output-dir>/diagnosis_report.md
```

研发交接改用 `--audience rd --output <output-dir>/rd_report.md`。省略 `--findings` 只生成明确标注的统计报告，不能称根因诊断已经完成。用户只关心特定问题时，账本与报告聚焦该范围，不强迫扩成全矩阵研究。

分析和渲染前重新验证 profile 的原始文件指纹；分析文件绑定 profile 哈希，避免套用另一次库存。账本校验来源存在、run 归属和文本行号，不自动证明摘录真实性与因果关系。交付前复核关键数、摘录、有效性警告和链接，按目标归组，并将统计结论/证据/待验证项分开。

所有脚本默认拒绝覆盖已有输出；仅用户指定更新时使用 `--overwrite`。不要移动历史 `entity-diagnosis` 报告。验证要区分：Skill 结构检查、脚本单测、真实数据只读复算，以及真正的修复实验。
