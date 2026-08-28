---
id: 07_Website_Generation_task_ab1479_tcm_prescription_table
name: 中药方剂数据表格
category: 07_Website_Generation
sub_category: 学习与知识
task_type: Management Systems-File Management
timeout_seconds: 900
modality: pure-text
difficulty: L2
grading_type: llm_judge
grading_weights:
  automated: 0.0
  llm_judge: 1.0
tags:
  - artifactsbench
  - web-site-gen
source:
  benchmark: ArtifactsBench
  index: 1479
---

# 中药方剂数据表格

## Prompt

请在 /tmp_workspace 下创建项目。如果启动网站时遇到端口冲突，请自行选择其他可用端口。

我想做一个和下面这张表一样的表格：

Prescription | Introduction | Formula | Preparation Method | Functions and Indications | Usage and Dosage | Reference
--- | --- | --- | --- | --- | --- | ---
Ai'ai Pill | [Formula] White ginger (stir-fried with salt, wine or rice vinegar) 8 qian, Cyperus rotundus (soaked in urine, fried) 1 liang, Corydalis yanhusuo (fried) 8 qian, genuine Donkey-hide gelatin (fried into pearls) 1... | White ginger (stir-fried with salt, wine or rice vinegar) 8 qian, Cyperus rotundus (soaked in urine, fried) 1 liang, Corydalis yanhusuo (fried) 8 qian, genuine Donkey-hide gelatin (fried into pearls) 1... | Grind into powder, mix with wine paste to form pills the size of Chinese parasol tree seeds. | Metrorrhagia, especially effective for elderly women. | 30 pills per dose, taken on empty stomach with salted wine or salt water. | "Yi Tong" Volume 84
Asafoetida and Galangal Pill | [Formula] Green tangerine peel 3 liang, Aged tangerine peel 2 liang, Galangal 2 liang, Red beans 2 liang, Cinnamon (coarse skin removed) 1 liang, Amomum (peel removed) 2 liang, Eupatorium (roasted) 2... | Green tangerine peel 3 liang, Aged tangerine peel 2 liang, Galangal 2 liang, Red beans 2 liang, Cinnamon (coarse skin removed) 1 liang, Amomum (peel removed) 2 liang, Eupatorium (roasted) 2... | Grind into fine powder and mix evenly, form pills with flour paste the size of mung beans. | Long-term use greatly nourishes spleen and stomach, clears stomach emptiness, improves appetite, eliminates cold dampness, strengthens and warms the body. Treats weakness in the three abdominal regions, accumulated cold in middle energizer, weak spleen digestion, slow digestion of food and drinks... | 50 pills per dose, taken with mild ginger soup, anytime, twice daily. | "Hong's Collected Verified Prescriptions" quoted from Shangguan Zhubo's prescription
Asafoetida Pill | Index "Asafoetida Pill" in "Revised Yan's Life-saving Formulas", "Asafoetida Pill" in "Danxi's Methods of Mental Cultivation" Volume 3, "Asafoetida Pill" in "Danxi's Methods of Mental Cultivation" Volume 3... | Costus root (uncooked) and Areca nut 15g each, Pepper and Asafoetida (dissolved in vinegar, added gradually) 7.5g each | Grind into fine powder, mix with Asafoetida paste and glutinous rice to form pills the size of Chinese parasol tree seeds. | Qi accumulation, meat accumulation, abdominal distention with lumps and pain. May cause pain in the sides and ribs, or pain extending to the back, and loss of appetite. | 40 pills per dose, anytime, taken with fresh ginger and tangerine peel soup. | "Revised Yan's Life-saving Formulas"

请保证代码能跑起来，可以直接演示效果。

## Expected Behavior

Agent 应生成可运行的方剂表格页面：表头包含题面给出的 Prescription、Introduction、Formula、Preparation Method、Functions and Indications、Usage and Dosage、Reference 这七列，并填入示例数据。表格结构语义清晰、排版整齐，长文本能正常换行，页面在不同宽度下都可读。表格具备排序、检索和分页一类的数据浏览能力，操作后有即时反馈。

## Grading Criteria

本题仅使用 LLM Judge 评分，10 个 Criterion 权重均为 10%。每个 Criterion 按 ArtifactsBench 原始锚点以 0-10 整数评分，入库时折算为 0.0-1.0（criterion 分 × 0.1）。

## Automated Checks

```python

```

## LLM Judge Rubric

说明：

- 每个 Criterion 只能使用 `0.0-1.0`、步长 `0.1`（对应原 checklist 的 0-10 分，下文锚点以 0-10 分表述）。
- 锚点中的"扣 N 分"从 10 分起扣，扣完为止；"加 N 分"从 0 分起加，上限 10 分。
- 每个 Criterion 标注 `采证方式`，如适用附 `采证动作`；评分必须引用证据（截图文件名／代码位置／观察记录）。
- 采证动作执行失败时，先在代码中确认该功能是否实现；若代码已实现而操作未生效，记录采证失败及原因（原生弹窗、拖拽模拟失效等），按代码实现情况给分，不因采证失败直接扣分。
- 满分锚点是质量天花板而非需求底线（如 Criterion 4 的虚拟滚动），Prompt 未明示的能力做不到时表现为得分低，不判零。

### Criterion 1: 表格结构实现 (key: c01_table_structure, weight: 0.1)

采证方式：页面观察 + 代码。

采证动作：打开页面查看表格是否正常渲染，把窗口宽度切到 375px 观察移动端表现；结合代码确认是否使用了 thead／tbody 等语义标签。

评分锚点：审查 HTML 代码是否正确实现了响应式数据表格，结构是否规范（thead、tbody）、列对齐是否正确、是否兼容移动端。检查表头是否定义清楚、数据行格式是否统一。完全没有实现表格计 0 分；有基础结构但布局问题明显计 5 分；表格结构完整、语义标记规范计 10 分。

### Criterion 2: 数据组织与展示完整性 (key: c02_data_completeness, weight: 0.1)

采证方式：页面观察 + 代码。

采证动作：逐列核对表头是否齐全，并检查每列是否都有示例数据、长文本是否正常换行而不是溢出或被截断。

评分锚点：评估 Prescription、Introduction、Formula、Preparation Method、Functions and Indications、Usage and Dosage、Reference 这七列是否都已实现并填入了示例数据。每一列都应格式合适、文本可正常换行。每缺一列或每有一列格式严重错乱扣 2 分。满分 10 分。

### Criterion 3: 排序与筛选能力 (key: c03_sort_filter, weight: 0.1)

采证方式：页面操作为主，代码为辅。

采证动作：点击表头按方剂名排序并记录排序前后顺序；在搜索框输入某味药材或某个主治关键词，记录筛选后的行数与内容是否匹配。

评分锚点：检查是否实现了按不同列排序（如按方剂名称排序）以及内容筛选（如搜索特定药材或主治）的功能。缺少排序扣 5 分；缺少筛选／搜索扣 5 分；这些功能虽有但表现很差扣 3 分。满分 10 分。

### Criterion 4: 分页或大数据量处理 (key: c04_pagination, weight: 0.1)

采证方式：页面操作 + 代码。

采证动作：翻到第 2 页并切换每页条数，记录分页控件是否好用；结合代码确认是否有分页、虚拟滚动或懒加载机制。

评分锚点：评估代码是否具备应对大数据量的机制，如分页、虚拟滚动或懒加载，在有几百条方剂数据时仍能保持流畅。没有分页／虚拟滚动扣 5 分；有但在大数据量下有性能问题扣 3 分；分页控件不直观扣 2 分。满分 10 分。

### Criterion 5: 代码鲁棒性 (key: c05_robustness, weight: 0.1)

采证方式：代码为主。

采证动作（辅助）：在搜索框输入特殊字符和超长字符串，观察页面是否报错或布局崩坏。

评分锚点：评估代码能否处理常见异常（字段缺失、文本极长、方剂名中含特殊字符等）并提供兜底或错误处理。鲁棒性强计 10 分，一般计 5 分，完全未处理异常计 0 分。

### Criterion 6: 创新功能 (key: c06_innovation, weight: 0.1)

采证方式：页面操作 + 代码。

评分锚点：检查是否包含提升体验的惊喜功能（如：1. 行可展开查看详情 2. 药材词条悬浮提示 3. 传统计量单位换算）。每实现一项实用创新加 3 分，上限 10 分。

### Criterion 7: 冗余功能检查 (key: c07_redundancy, weight: 0.1)

采证方式：代码为主。

评分锚点：严查三类冗余：1. 同类功能重复实现（如多套排序机制并存）2. 与方剂表格无关的功能模块（如无关的小挂件）3. 影响性能的花哨特效（如不必要的动画）。每处冗余扣 3 分；核心功能被冗余代码干扰直接计 0 分。

### Criterion 8: 工程质量 (key: c08_engineering, weight: 0.1)

采证方式：代码。

评分锚点：审查模块化设计（数据／视图／控制层是否分离）、代码复用性以及库或框架的使用是否得当。存在全局变量污染或未使用设计模式扣 5 分；代码重复率过高（超过 30%）扣 5 分；完全没有考虑大数据量下的性能优化扣 5 分。满分 10 分。

### Criterion 9: 界面视觉专业性 (key: c09_visual_design, weight: 0.1)

采证方式：截图。

采证动作：桌面 1440×900 截取整页图，覆盖表头与至少 3 行数据。

评分锚点：评估整体设计是否符合现代表格设计原则：1）边框、分隔线与留白使用得当 2）字号统一且正文可读（正文不小于 14px）3）表头与数据在视觉层级上区分清楚。单元格排版杂乱扣 3 分；对比度差导致文字难读扣 5 分；列宽不一致或内容对齐混乱扣 5 分。满分 10 分。

### Criterion 10: 动态交互流畅性 (key: c10_interaction_fluency, weight: 0.1)

采证方式：页面操作。

采证动作：连续执行排序、搜索、展开／收起各 2 次，记录反馈延迟、过渡效果与悬浮态表现。

评分锚点：判断交互是否符合用户预期：1）排序／筛选响应及时，视觉反馈不超过 200ms 2）内容展开收起时过渡自然 3）有悬浮态，可点击元素一眼能辨认。每处操作无反馈扣 5 分；大数据量下交互卡顿扣 3 分；交互方式不直观扣 5 分。满分 10 分。

## Workspace Path

```
workspace/07_Website_Generation/task_ab1479_tcm_prescription_table
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
