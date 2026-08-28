---
id: 07_Website_Generation_task_ab078_svg_smartphone_speech_bubbles
name: 手机对话气泡黑白插画
category: 07_Website_Generation
sub_category: 创意与娱乐
task_type: SVG Generation-SVG Images
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
  index: 78
---

# 手机对话气泡黑白插画

## Prompt

请在 /tmp_workspace 下创建项目。如果启动网站时遇到端口冲突，请自行选择其他可用端口。

我想要一幅黑白插画：一部智能手机，屏幕上方冒出若干对话气泡。请用 SVG 代码来实现这幅插画。

## Expected Behavior

Agent 应生成一个可在浏览器中直接打开的 SVG 插画页面：画面中有一部轮廓清晰、比例合理的智能手机，机身上方伸出多个带指向手机的小尾巴的对话气泡，整幅插画只使用黑、白、灰三类颜色。SVG 元素应有合理的分组与命名，页面缩放时插画不变形。

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

### Criterion 1: 手机基本结构 (key: c01_smartphone_structure, weight: 0.1)

采证方式：截图为主，代码为辅。

采证动作：在浏览器中打开插画页面，桌面 1440×900 截整页图，确认画面中的手机是否包含机身、屏幕、Home 键、摄像头等关键部件且比例、位置合理。

评分锚点：检查手机轮廓是否包含关键部件（机身、屏幕、Home 键、摄像头），比例与位置是否合理，画面应能一眼认出是一部智能手机。基本结构缺失计 0 分；只有简化轮廓计 5 分；所有关键部件都用合适的 SVG path 元素和分组良好实现计 10 分。

### Criterion 2: 对话气泡实现 (key: c02_speech_bubbles, weight: 0.1)

采证方式：截图 + 代码。

采证动作：在截图中确认对话气泡的数量、形状与指向；在代码中确认气泡是否用 `<path>` 元素或组合图形绘制出平滑曲线。

评分锚点：评估是否绘制了多个形状规范的对话气泡（含指向手机的小尾巴／箭头），是否正确使用 `<path>` 元素或组合图形实现平滑曲线。只有基础矩形气泡计 3 分；气泡曲线绘制规范计 7 分；气泡形状／大小富有变化且尾巴正确指向手机计 10 分。

### Criterion 3: 黑白配色 (key: c03_black_white_scheme, weight: 0.1)

采证方式：截图 + 代码。

采证动作：检查截图中是否出现黑白灰以外的颜色；在代码中检索 fill/stroke/opacity 属性的取值，确认全部为黑、白或灰度值。

评分锚点：核实插画是否严格只使用黑、白与灰度值，不含任何彩色；检查 fill、stroke、opacity 属性是否用得恰当，以营造层次与对比。每出现一处彩色扣 3 分；对比度不足、元素难以分辨扣 5 分。满分 10 分。

### Criterion 4: SVG 结构与层级 (key: c04_svg_structure, weight: 0.1)

采证方式：代码为主。

评分锚点：审查 SVG 元素的组织方式：是否用 `<g>` 标签合理分组、元素是否用 id 或 class 属性做有意义的命名、嵌套是否得当；相关元素（手机部件、对话气泡）是否归入同一分组。结构扁平、完全没有分组扣 5 分；命名规范不统一扣 3 分。满分 10 分。

### Criterion 5: 代码鲁棒性 (key: c05_robustness, weight: 0.1)

采证方式：代码为主。

采证动作（辅助）：调整浏览器窗口大小，观察插画是否随容器缩放且不变形。

评分锚点：评估 SVG 代码是否正确设置视口、采用响应式手法（viewBox、preserveAspectRatio），能否适配不同容器尺寸而不变形，并在不同浏览器下保持外观正常。鲁棒性强、以上考量处理到位计 10 分；一般计 5 分；完全没有考虑计 0 分。

### Criterion 6: 创新功能 (key: c06_innovation, weight: 0.1)

采证方式：页面操作 + 代码。

评分锚点：检查是否包含为插画加分的惊喜功能（如：1. 对话气泡的细腻动画 2. 响应悬停／点击的交互元素 3. 在黑白限定内巧用渐变或图案纹理）。每实现一项实用创新加 3 分，上限 10 分。

### Criterion 7: 冗余检查 (key: c07_redundancy, weight: 0.1)

采证方式：代码为主。

评分锚点：严查三类冗余：1. 本可简化却写得过于复杂的路径 2. 相似元素的重复定义 3. 对整体画面没有贡献的过度细节。每发现一处冗余扣 3 分；冗余元素喧宾夺主、遮蔽核心画面直接计 0 分。

### Criterion 8: 工程质量 (key: c08_engineering, weight: 0.1)

采证方式：代码。

评分锚点：审查代码组织（有意义的注释、规范缩进）、优化程度（重复元素使用 symbol 复用、路径点数精简）与最佳实践（命名空间使用正确、属性顺序合理）。路径过于冗长扣 5 分；定义存在明显重复扣 5 分；因优化不足导致文件体积无谓偏大扣 5 分。满分 10 分。

### Criterion 9: 专业设计水准 (key: c09_design_standards, weight: 0.1)

采证方式：截图。

采证动作：桌面 1440×900 截整页图，评估构图、线条与留白。

评分锚点：评估整体设计是否符合专业插画原则：1）构图均衡、视觉重心得当 2）线条粗细与风格统一 3）留白与比例运用得当。构图失衡扣 3 分；风格元素不统一扣 5 分；空间运用差、造成视觉混乱扣 5 分。满分 10 分。

### Criterion 10: 可访问性与语义化 (key: c10_accessibility, weight: 0.1)

采证方式：代码。

评分锚点：判断 SVG 是否具备恰当的可访问性特性：1）正确的 title 与 desc 元素 2）在合适位置使用 ARIA 属性 3）可读文字内容用真正的 `<text>` 元素而非路径绘制。缺少 title/desc 扣 4 分；文字内容不可访问扣 3 分；缺乏语义化结构扣 3 分。满分 10 分。

## Workspace Path

```
workspace/07_Website_Generation/task_ab078_svg_smartphone_speech_bubbles
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
