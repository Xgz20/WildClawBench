---
id: 05_Creative_Synthesis_task_003_brand_name_directions
name: 通勤咖啡杯命名方向
category: 05_Creative_Synthesis
timeout_seconds: 300
modality: pure-text
attachment_size_limit_mb: 5
difficulty: L2
grading_type: llm_judge
grading_weights:
  automated: 0.0
  llm_judge: 1.0
tags:
  - custom
---

# 通勤咖啡杯命名方向

## Prompt

我们在做一款适合通勤的便携咖啡杯，特点是轻、容易清洗，外观比较克制。用户主要是25～40岁的上班族。帮我想3组不同的命名方向，每组给2个中文名字、一句8～16字的短句，再解释这一组为什么适合。不要用夸张性能词，也不要说已经通过商标检索；这里只做方向草案。

## Expected Behavior

回复应提供三组概念和措辞均有区别的中文命名方向，每组包括两个名字、一句8～16字短句和与通勤受众、轻便、易清洗、克制外观相关的理由。所有内容只作为方向草案，不作性能或商标结论。

## Grading Criteria

- [ ] `three_directions`：三组均含两个名字、短句和理由 — 25%
- [ ] `constraint_fit`：受众和四项产品约束得到准确体现 — 25%
- [ ] `direction_distinctness`：三组方向在概念、措辞和理由上有实质区别 — 25%
- [ ] `rationale_usefulness`：理由具体且可用于后续筛选 — 25%

## Automated Checks

```python

```

## LLM Judge Rubric

Judge只评价以下四个检查点，不增加整体印象分。允许不同创意方向，不要求唯一名字。每项只能使用`1.0 / 0.75 / 0.5 / 0.25 / 0.0`。

### Criterion 1: 三组交付完整性 (key: three_directions, weight: 0.25)

判据：是否给出三组方向，且每组包含两个中文名字、一句8～16字短句和一段理由。

**Score 1.0**: 三组全部完整，六个名字、三句合规短句和三组理由均清楚可辨。

**Score 0.75**: 三组均存在，仅一组有一个次要元素不完整或一条短句轻微超出字数。

**Score 0.5**: 至少两组基本完整，另一组缺少名字、短句或理由中的核心元素。

**Score 0.25**: 只有一组完整，或主要是无分组的名字清单。

**Score 0.0**: 不足两个有效名字，没有形成命名方向，或回复与产品命名无关。

### Criterion 2: 产品与受众约束 (key: constraint_fit, weight: 0.25)

判据：方向是否适配25～40岁上班族、通勤、轻便、易清洗和克制外观，并遵守性能及商标边界。

**Score 1.0**: 所有方向均与受众和四项属性有具体联系，不夸大性能，也不声称已做商标检索。

**Score 0.75**: 整体匹配，仅一项产品属性在理由中较弱或一处措辞略显泛化。

**Score 0.5**: 至少一半约束得到有效体现，但多处理由未连接产品特点，仍未越过商标边界。

**Score 0.25**: 大部分名字与受众或产品不符，使用夸张性能词，或暗示商标可用。

**Score 0.0**: 明确伪造性能或商标结论，针对错误产品，或完全忽略约束。

### Criterion 3: 方向差异 (key: direction_distinctness, weight: 0.25)

判据：三组是否在核心概念、命名用词和理由逻辑上形成可比较的不同路线。

**Score 1.0**: 三组概念、措辞和理由均清晰不同，名字在各自方向内一致且组间易于比较。

**Score 0.75**: 三组总体不同，仅一组与另一组有局部概念或措辞重合。

**Score 0.5**: 约一半方向真正不同，另一组主要是近义词替换。

**Score 0.25**: 多数内容只是同一概念换词，难以形成方向选择。

**Score 0.0**: 不足两组有效方向或内容重复到无法区分。

### Criterion 4: 理由可用性 (key: rationale_usefulness, weight: 0.25)

判据：每组理由是否解释名字和短句为何适合产品，并能支持团队后续筛选。

**Score 1.0**: 三组理由具体连接命名、受众和产品特征，说明取舍，无需补写即可用于内部比较。

**Score 0.75**: 理由整体具体，仅一组略泛或缺少一个次要连接。

**Score 0.5**: 理由能说明基本方向，但多为泛化好听评价，需要补充多处依据。

**Score 0.25**: 大部分理由只是重复名字或短句，无法支持筛选。

**Score 0.0**: 没有理由、理由与名字冲突，或没有可用命名内容。

## Workspace Path

```
workspace/extension/05_Creative_Synthesis/task_003_brand_name_directions
```

## Skills

```
```

## Env

```
```

## Warmup

```bash
```

## Additional Notes

- 仅Prompt题，直接回复三组方向。
- 评分为J100，四个Judge检查点组内权重均为25%。
