---
id: 07_Website_Generation_task_ab1565_product_review_list_page
name: 商品评价列表页
category: 07_Website_Generation
sub_category: 旅行与消费决策
task_type: Web Applications-Online Shopping
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
  index: 1565
---

# 商品评价列表页

## Prompt

请在 /tmp_workspace 下创建项目。如果启动网站时遇到端口冲突，请自行选择其他可用端口。

我在做一个商品评价页面，已有一个 Vue 响应式的评价数据列表（list），每条评价的字段类似这样：

```
avatar: "https://lutuyiyi.xyz/uploads/20250309/6973bf0c46fb7b55077020e478ad431c.jpeg"
content: "ssssssssss"
createtime: 1742028195
id: 5
images: ""
nickname: "Jingcang"
star: 1
user_id: 3
```

页面已有的模板片段：

```
<view class="plr30">
    <view class="fs34 col10 fwb pb20">商品评价</view>
```

请帮我补全这个评价列表的前端代码，样式仿照大众点评。

## Expected Behavior

Agent 应生成可运行的商品评价列表页面：按大众点评风格渲染评价列表，每条评价展示头像、昵称、星级、评价内容和格式化后的时间；评价带图时以图集形式展示并支持预览，无图时正常留空；数据变化时列表随之更新。

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
- 满分锚点是质量天花板而非需求底线（如 Criterion 2 的图片缩放预览），Prompt 未明示的能力做不到时表现为得分低，不判零。

### Criterion 1: 评价列表展示功能 (key: c01_review_list, weight: 0.1)

采证方式：页面操作为主，代码为辅。

采证动作：打开评价页面，逐条核对头像、昵称、星级、评价内容、时间是否正确显示并截图；结合代码确认数据绑定字段、空列表处理与分页／加载更多逻辑。

评分锚点：评估代码是否正确渲染评价列表数据、结构是否合理，检查头像、昵称、评价内容、星级（star）与时间是否正常展示。数据绑定错误扣 5 分；列表未处理空状态扣 3 分；未实现分页扣 3 分。满分 10 分。

### Criterion 2: 评价图片图集功能 (key: c02_image_gallery, weight: 0.1)

采证方式：页面操作为主，代码为辅。

采证动作：找到带图评价，点击图片验证是否可预览、放大；核对无图评价（images 为空）是否正常展示不留破图。

评分锚点：检查实现是否正确处理评价图片，包括多图展示、空图片数组的处理、以及图片预览功能。完全没有处理图片计 0 分；只实现了基础图片展示计 5 分；实现完整图集并支持预览与缩放计 10 分。

### Criterion 3: 时间戳格式化 (key: c03_timestamp_format, weight: 0.1)

采证方式：页面观察 + 代码。

采证动作：核对页面上每条评价的时间显示（如"2 小时前"或"2025-03-15 16:43"），结合代码确认 Unix 时间戳（createtime）的转换逻辑。

评分锚点：验证 Unix 格式的时间戳（createtime）是否被正确转换为人类可读的格式；检查实现采用相对时间（如"2 小时前"）还是本地化的绝对时间。直接显示原始 Unix 时间戳计 0 分；只做了基础格式化计 5 分；能处理多种时间格式并正确本地化计 10 分。

### Criterion 4: Vue 响应式数据绑定 (key: c04_vue_reactivity, weight: 0.1)

采证方式：代码为主，页面操作为辅。

采证动作（辅助）：若页面提供新增／修改评价数据的入口（或通过控制台修改 list），触发一次数据变化，观察列表是否随之更新。

评分锚点：评估代码是否正确利用了 Vue 的响应式系统（数据中的 __ob__: Observer 即为提示）。检查 list 的变化能否正确反映到 UI 上，computed 计算属性与 watcher 的使用是否得当。响应式绑定失效计 0 分；基础响应式可用但存在边界场景 bug 计 5 分；充分发挥 Vue 响应式体系计 10 分。

### Criterion 5: 代码鲁棒性 (key: c05_robustness, weight: 0.1)

采证方式：代码为主。

采证动作（辅助）：检查页面对缺字段数据、超长评价内容的呈现是否正常。

评分锚点：评估代码能否处理常见异常情况（如数据字段缺失、获取评价时网络出错、超长内容的显示问题等）并提供友好的错误处理或兜底方案。鲁棒性强、能有效处理这些边界情况计 10 分；鲁棒性一般计 5 分；完全未处理异常计 0 分。

### Criterion 6: 创新功能 (key: c06_innovation, weight: 0.1)

采证方式：页面操作 + 代码。

评分锚点：检查代码是否包含提升体验的惊喜功能（如：1. 评价排序／筛选选项 2. 带动画的交互式星级评分 3. "有用／没用"这类用户互动按钮）。每实现一项实用创新加 3 分，上限 10 分。

### Criterion 7: 冗余功能检查 (key: c07_redundancy, weight: 0.1)

采证方式：代码为主。

评分锚点：严查三类冗余：1. 同类功能重复实现（如同一份数据用多种方式重复展示）2. 与评价无关的功能模块（如不必要的用户主页板块）3. 影响性能的花哨特效（如过多的动画）。每处冗余扣 3 分；冗余代码干扰核心功能直接计 0 分。

### Criterion 8: 工程质量 (key: c08_engineering, weight: 0.1)

采证方式：代码。

评分锚点：审查组件结构（如把评价条目拆分为独立组件）、代码复用性与可维护性。发现全局状态污染扣 5 分；代码重复率过高（超过 30%）扣 5 分；未使用合适的 CSS 方案（如 BEM 或 scoped CSS）扣 5 分。满分 10 分。

### Criterion 9: 界面视觉专业性 (key: c09_visual_design, weight: 0.1)

采证方式：截图。

采证动作：桌面 1440×900 截评价列表整页图，必要时补截带图评价区域。

评分锚点：评估整体设计是否符合现代设计原则：1）配色和谐（主色不超过 3 种）2）布局间距合理（元素间距遵循 8px 倍数原则）3）专业字体体系（正文字号不小于 14px、行高不低于 1.5 倍）。每处视觉拥挤扣 3 分；刺眼配色扣 5 分；图文排版混乱扣 5 分。满分 10 分。

### Criterion 10: 动态交互流畅性 (key: c10_interaction_fluency, weight: 0.1)

采证方式：页面操作。

采证动作：连续滚动评价列表、展开长评价或点开图片、点击星级各操作 3 次，记录反馈与流畅度。

评分锚点：判断动效是否符合移动应用标准：1）滚动顺滑无卡顿 2）展开评价或加载图片有过渡动画 3）点星等用户交互有清晰的视觉反馈。每处操作无反馈扣 5 分；滚动时有性能问题扣 3 分；交互目标难以点中扣 5 分。满分 10 分。

## Workspace Path

```
workspace/07_Website_Generation/task_ab1565_product_review_list_page
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
