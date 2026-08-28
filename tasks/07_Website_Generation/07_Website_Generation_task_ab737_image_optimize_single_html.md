---
id: 07_Website_Generation_task_ab737_image_optimize_single_html
name: 图片优化单文件页面
category: 07_Website_Generation
sub_category: 内容与知识生产
task_type: Multimedia Editing-Image Editing
timeout_seconds: 900
modality: pure-text
difficulty: L1
grading_type: llm_judge
grading_weights:
  automated: 0.0
  llm_judge: 1.0
tags:
  - artifactsbench
  - web-site-gen
source:
  benchmark: ArtifactsBench
  index: 737
---

# 图片优化单文件页面

## Prompt

请在 /tmp_workspace 下创建项目。如果启动网站时遇到端口冲突，请自行选择其他可用端口。

我这有一张图片 layer-1.jpg，尺寸好像不太对。请帮我把它优化一下，然后把所有代码写进一个 HTML 文件里，可以做到吗？请保证代码可以直接运行演示。（如果工作区里没有这张图，可以自己生成一张示例图片代替 layer-1.jpg 来完成演示。）

## Expected Behavior

Agent 应产出一个单一 HTML 文件：其中对图片（layer-1.jpg 或自生成的示例图）做了尺寸/比例等优化处理，并将优化后的图片嵌入该 HTML 文件内（如 base64/data URI），页面能正常展示图片，在不同视口下缩放正常，图片加载有合理的处理。

## Grading Criteria

本题仅使用 LLM Judge 评分，10 个 Criterion 权重均为 10%。每个 Criterion 按 ArtifactsBench 原始锚点以 0~10 整数评分，入库时折算为 0.0~1.0（criterion 分 × 0.1）。

## Automated Checks

```python

```

## LLM Judge Rubric

说明：

- 每个 Criterion 只能使用 `0.0 ~ 1.0`、步长 `0.1`（对应原 checklist 的 0~10 分，下文锚点以 0~10 分表述）。
- 锚点中的"扣 N 分"从 10 分起扣，扣完为止；"加 N 分"从 0 分起加，上限 10 分。
- 每个 Criterion 标注 `采证方式`，如适用附 `采证动作`；评分必须引用证据（截图文件名／代码位置／观察记录）。
- 采证动作执行失败时，先在代码中确认该功能是否实现；若代码已实现而操作未生效，记录采证失败及原因（原生弹窗、拖拽模拟失效等），按代码实现情况给分，不因采证失败直接扣分。
- 满分锚点是质量天花板而非需求底线，Prompt 未明示的能力做不到时表现为得分低，不判零。

### Criterion 1: 图片优化处理 (key: c01_image_optimization, weight: 0.1)

采证方式：代码为主，页面观察为辅。

采证动作：打开页面确认图片正常显示且比例正常；结合代码确认对图片尺寸、宽高比、文件大小、质量、格式做了哪些优化处理。

评分锚点：审查代码是否对收到的图片（layer-1.jpg）做了正确的分析与优化，检查是否处理了尺寸、宽高比、文件大小、质量和格式。没有做任何优化计 0 分；只做了基础的尺寸调整计 5 分；正确执行了全面优化（缩放、压缩、必要时的格式转换）计 10 分。

### Criterion 2: HTML 结构组织 (key: c02_html_structure, weight: 0.1)

采证方式：代码为主。

评分锚点：检查 HTML 文档是否遵循语义化标记原则，使用了适合图片展示的标签（如 figure、picture 等）；检查是否应用了响应式设计原则（max-width、viewport 设置）。基础 HTML 结构缺失扣 5 分；不当使用非语义化标签扣 3 分。满分 10 分。

### Criterion 3: 图片加载技术 (key: c03_image_loading, weight: 0.1)

采证方式：代码为主，页面观察为辅。

采证动作：刷新页面观察图片加载过程；结合代码确认是否使用懒加载、渐进式加载或 loading 属性，以及是否有针对不支持特性的浏览器的兜底方案。

评分锚点：评估代码是否实现了现代图片加载技术，如懒加载、渐进式加载或使用 loading 属性；检查是否为不支持某些特性的浏览器提供兜底方案。未使用任何优化技术扣 5 分；实现只是基础水平且没有兜底扣 3 分。满分 10 分。

### Criterion 4: 单 HTML 文件集成 (key: c04_single_file_integration, weight: 0.1)

采证方式：代码为主，页面观察为辅。

采证动作：确认交付物是单个 HTML 文件且图片以内嵌方式集成（base64/data URI 等），断开外部资源的情况下打开页面验证图片仍可显示。

评分锚点：验证图片是否按要求正确嵌入单个 HTML 文件中，可通过 base64 编码、data URI 或其他合适方式实现。图片没有集成进单个文件计 0 分；有基础集成但存在问题计 5 分；集成得当、编码正确并兼顾性能计 10 分。

### Criterion 5: 代码鲁棒性 (key: c05_robustness, weight: 0.1)

采证方式：代码为主。

评分锚点：评估代码能否处理常见异常情况（如图片加载失败、浏览器特性不支持等）并提供友好的错误处理或兜底机制。鲁棒性强、能有效处理这些边界情况计 10 分；鲁棒性一般计 5 分；完全未处理异常计 0 分。

### Criterion 6: 创新功能 (key: c06_innovation, weight: 0.1)

采证方式：页面操作 + 代码。

采证动作（辅助）：若页面提供缩放/平移等交互，逐一尝试并记录效果。

评分锚点：检查是否包含提升体验的惊喜功能（如：1. 渐进式图片加载效果 2. 缩放/平移功能 3. 基于视口的动态图片优化）。每实现一项实用创新加 3 分，上限 10 分。

### Criterion 7: 冗余功能检查 (key: c07_redundancy, weight: 0.1)

采证方式：代码为主。

评分锚点：严查三类冗余：1. 同类功能重复实现（如一种图片加载方式就够了却实现了多种）2. 与图片优化无关的功能模块（如不必要的动画）3. 影响性能的花哨特效（如拖慢图片渲染的重型 JavaScript）。每发现一处冗余扣 3 分；冗余代码干扰核心功能直接计 0 分。

### Criterion 8: 工程质量 (key: c08_engineering, weight: 0.1)

采证方式：代码。

评分锚点：审查代码组织、错误处理方式、跨浏览器兼容性考虑和性能优化手段。发现全局命名空间污染扣 5 分；代码不模块化或存在过量注释/不必要的复杂度扣 5 分；忽视性能最佳实践扣 5 分。满分 10 分。

### Criterion 9: 图片展示设计专业性 (key: c09_visual_design, weight: 0.1)

采证方式：截图。

采证动作：桌面 1440×900 截整页图，检查图片在视口内的容纳、留白与样式。

评分锚点：评估图片呈现是否遵循现代设计原则：1）图片在视口内容纳得当 2）图片四周有合适的内外边距 3）样式处理专业（如有边框、阴影等则运用得当）。图片容纳不当扣 3 分；留白不足扣 5 分；样式不专业扣 5 分。满分 10 分。

### Criterion 10: 用户体验流畅性 (key: c10_user_experience, weight: 0.1)

采证方式：页面操作。

采证动作：刷新页面记录加载表现；将视口切换至移动端宽度（如 375px）观察图片缩放；若有交互元素则逐一操作并记录直观性。

评分锚点：判断图片展示体验是否最优：1）加载迅速且加载过程有视觉指示 2）在不同视口下图片缩放正常 3）若添加了交互元素，交互直观易懂。加载慢且无指示扣 5 分；移动端缩放表现差扣 3 分；交互元素令人困惑或不直观扣 5 分。满分 10 分。

## Workspace Path

```
workspace/07_Website_Generation/task_ab737_image_optimize_single_html
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
