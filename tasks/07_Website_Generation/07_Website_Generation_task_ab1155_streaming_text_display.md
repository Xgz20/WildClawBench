---
id: 07_Website_Generation_task_ab1155_streaming_text_display
name: 流式文本展示应用
category: 07_Website_Generation
sub_category: 内容与知识生产
task_type: Web Applications-Communication
timeout_seconds: 900
modality: pure-text
difficulty: L3
grading_type: llm_judge
grading_weights:
  automated: 0.0
  llm_judge: 1.0
tags:
  - artifactsbench
  - web-site-gen
source:
  benchmark: ArtifactsBench
  index: 1155
---

# 流式文本展示应用

## Prompt

请在 /tmp_workspace 下创建项目。如果启动网站时遇到端口冲突，请自行选择其他可用端口。

我想用 Vue + Axios + ThinkPHP 对接 Deepseek API，实现一个流式文本展示功能：模型返回的文本一段一段地实时显示在页面上。请帮我把这套代码写出来。

请确保生成的代码可以直接运行、用于演示展示。

## Expected Behavior

Agent 应生成前后端完整的流式文本展示工程：Vue 前端通过 Axios 发起流式请求并把文本增量渲染到页面，ThinkPHP 后端以 SSE 或 chunked 方式转发 Deepseek API 的流式响应。无真实 API Key 时应有可演示的降级方案（如模拟流式数据），页面上能看到文字逐步出现的效果。

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
- 采证动作执行失败时，先在代码中确认该功能是否实现；若代码已实现而操作未生效，记录采证失败及原因（PHP 环境缺失、无 API Key 等），按代码实现情况给分，不因采证失败直接扣分。
- 满分锚点是质量天花板而非需求底线（如请求取消、重试机制），Prompt 未明示的能力做不到时表现为得分低，不判零。

### Criterion 1: 流式展示核心功能 (key: c01_streaming_display, weight: 0.1)

采证方式：页面操作为主，代码为辅。

采证动作：启动前端（后端不可用时用其降级／模拟模式），触发一次文本生成，观察文字是否逐段实时出现而非一次性整段显示，记录渲染节奏；结合代码确认 SSE／chunked 的处理逻辑。

评分锚点：审查代码是否通过 Vue.js 响应式数据绑定准确实现实时流式文本展示，包括对 Server-Sent Events（SSE）或 chunked 传输编码的正确处理；检查文本分片是否以逐字或逐词的平滑动画渐进渲染。未实现流式展示计 0 分；只做了简单的文本追加计 5 分；完整实现带缓冲与显示控制的平滑流式效果计 10 分。

### Criterion 2: Vue + Axios 集成架构 (key: c02_vue_axios_integration, weight: 0.1)

采证方式：代码为主。

采证动作（辅助）：查看 Axios 请求配置（responseType、超时、进度监听）与 Vue 响应式更新的实现位置。

评分锚点：评估 Axios 是否为流式请求正确配置了 responseType（stream/text）、超时处理与进度监听；检查是否恰当利用 Vue 响应式系统做实时 UI 更新且无性能瓶颈。未实现请求取消扣 5 分；长时间流式会话存在内存泄漏扣 3 分。满分 10 分。

### Criterion 3: ThinkPHP 后端流式响应 (key: c03_thinkphp_streaming, weight: 0.1)

采证方式：代码为主。

采证动作（辅助）：若 PHP 环境可用则启动后端并请求流式接口，观察响应头与分块输出；否则审查响应头设置与缓冲刷新代码。

评分锚点：检查 ThinkPHP 后端是否正确实现流式响应：响应头设置正确（Transfer-Encoding: chunked 或 Content-Type: text/event-stream），Deepseek API 对接包含妥善的错误处理与限流；确认后端能维持长连接并正确刷新缓冲。未处理 API Key 安全问题扣 5 分；未处理流式连接中断扣 3 分。满分 10 分。

### Criterion 4: Deepseek API 集成完备性 (key: c04_deepseek_integration, weight: 0.1)

采证方式：代码为主。

评分锚点：评估 Deepseek API 集成是否包含正确的鉴权、请求格式组装、响应解析，以及针对各种 API 响应场景的错误处理；检查流式参数配置是否正确、API 限流与配额是否妥善管理。缺少 API 响应校验扣 5 分；未实现失败请求的重试机制扣 3 分。完整实现且具备全面的错误恢复能力计 10 分。

### Criterion 5: 代码鲁棒性 (key: c05_robustness, weight: 0.1)

采证方式：代码为主。

采证动作（辅助）：在流式输出进行中刷新或离开页面，观察是否报错。

评分锚点：评估代码能否处理常见异常情况（网络中断、API 超时、响应格式异常、流式过程中组件卸载等）并提供友好的错误提示或恢复机制。鲁棒性强、能有效处理这些边界情况并平稳降级计 10 分；鲁棒性一般计 5 分；完全未处理异常计 0 分。

### Criterion 6: 创新功能 (key: c06_innovation, weight: 0.1)

采证方式：页面操作 + 代码。

评分锚点：检查是否包含提升流式体验的惊喜功能（如：1. 与文字出现同步的打字音效 2. 可调节的流式速度控制 3. 不同内容类型用不同颜色高亮 4. 流式内容导出功能 5. 暂停／继续流式输出）。每实现一项实用创新加 3 分，上限 10 分。

### Criterion 7: 冗余功能检查 (key: c07_redundancy, weight: 0.1)

采证方式：代码为主。

评分锚点：严查三类冗余：1. 相似功能的重复实现（如多套文本渲染方案并存）2. 与流式文本展示无关的功能模块（如内置文件管理系统）3. 影响流式性能的花哨特效（如文本渲染时的复杂粒子动画）。每处冗余扣 3 分；核心流式功能被冗余代码干扰直接计 0 分。

### Criterion 8: 工程质量 (key: c08_engineering, weight: 0.1)

采证方式：代码。

评分锚点：审查模块化设计（如 API 服务／Vue 组件／工具函数分离）、Composition API 或 Options API 的规范使用、以及 TypeScript 集成（如适用）。存在全局状态污染或不遵循 Vue 最佳实践扣 5 分；代码重复率过高（超过 30%）扣 5 分；缺少妥善的组件生命周期管理扣 5 分。满分 10 分。

### Criterion 9: 界面视觉专业性 (key: c09_visual_design, weight: 0.1)

采证方式：截图。

采证动作：桌面 1440×900 分别截取空闲状态与流式输出中的整页图。

评分锚点：评估流式文本展示是否符合现代设计原则：1）配色和谐、对比度保证可读性 2）排版得当，行距充足（1.4~1.6 倍）、字号合适 3）布局干净、留白与视觉层次恰当 4）有加载状态与进度指示。每处设计欠佳的视觉元素扣 3 分；文本可读性差扣 5 分；流式输出过程中布局混乱扣 5 分。满分 10 分。

### Criterion 10: 流式动画流畅性 (key: c10_streaming_animation, weight: 0.1)

采证方式：页面操作。

采证动作：完整观察一次流式输出全过程，记录速度是否均匀、光标／打字指示动画表现、长文本换行与滚动情况；将窗口缩窄到移动宽度再观察一次。

评分锚点：判断流式文本动画是否符合人类阅读习惯：1）流式速度稳定、无突兀停顿 2）光标或打字指示动画平滑 3）文本换行与溢出处理妥当 4）快速更新时无视觉故障 5）响应式设计适配不同屏幕尺寸。每处卡顿动画扣 5 分；文本渲染出现瑕疵扣 3 分；移动端流式体验差扣 5 分。满分 10 分。

## Workspace Path

```
workspace/07_Website_Generation/task_ab1155_streaming_text_display
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
