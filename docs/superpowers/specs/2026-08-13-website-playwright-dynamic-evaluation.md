# Web 站点 Playwright 动态评测设计

## 1. 决策摘要

`web-site-gen` 任务采用混合证据评分：内容与交互 Criterion 由仓库维护的 Playwright 任务级检查器执行，视觉 Criterion 由 Claude 基于框架截取的正式浏览器截图评分。两类结果继续使用任务 Rubric 中的 canonical `key` 和原始 `weight` 合并，不新增另一套指标，也不改变非 Web v2 和 legacy 用例的评分入口。

一期只验证本地单页站点。浏览器检查不允许访问外部网络，不引入自动探索 Agent，也不让被测 Agent 看到检查器实现。新 Web 用例必须同时提供可运行站点、符合可访问性语义的交互控件，以及与 Rubric 对齐的任务级检查脚本。

## 2. 目标与边界

目标：

- 用真实浏览器执行导航、筛选、表单、CRUD、状态联动和刷新持久化等操作；
- 固定视口、网络策略和初始状态，使同一产物的检查结果可重复；
- 视觉 Judge 只接收正式截图，不读取源码、transcript 或动态检查结果；
- 保留 `automated.<key>`、`llm_judge.<key>`、`overall_score` 和 `_dimensions` 报告契约；
- 将构建、浏览器、截图、trace 和 Judge 请求/响应落盘，支持问题复核。

非目标：

- 不让 LLM 自主决定点击路径；
- 不验证真实支付、第三方登录、外部 API 或线上资源；
- 不使用失败诊断截图进行视觉评分；
- 不改变现有 Web Rubric 的 key、一级/二级维度和权重；
- 不改变 PPT、普通 v2 或 legacy 用例的评分行为。

## 3. 识别与兼容性

任务 frontmatter 的 `tags` 包含 `web-site-gen` 时，`src/utils/task_parser.py` 将其解析为 `metric_profile=web-site-gen`。`src/utils/grading.py::run_grading()` 仅在该 profile 下进入网站动态分支：

- `primary != visual_layout` 的 Criterion 交给 Playwright；
- `primary == visual_layout` 的 Criterion 交给视觉 Judge；
- 其他 profile 继续使用现有 v2 流程；
- 没有 v2 Rubric 的历史任务继续使用 legacy `grade()` 流程。

报告同时识别历史 `source_semantic` 和新的 `browser_runtime+visual_llm`。混合报告中只有 `metric_profile=web-site-gen` 的任务进入站点评测指标聚合。

## 4. 运行流程

1. Agent 在 `/tmp_workspace` 生成站点并结束执行。
2. 评分阶段将 `eval/checks/website` 复制到同一容器的 `/tmp/_wildclaw_website_checks`。复制发生在 Agent 结束之后，检查器代码不进入 Agent 工作目录。
3. `runner.py` 在 `/tmp_workspace` 中检查 `package.json`，缺少 `node_modules` 时执行 `npm install`，随后执行 `npm run build`。
4. Runner 使用 `npm run start -- --host 127.0.0.1 --port 4173` 启动站点并轮询就绪状态。
5. Playwright 使用 Chromium、`1440x900` 视口和新建 browser context。浏览器只允许访问 `127.0.0.1:4173`、`localhost:4173`、`data:`、`blob:` 和 `about:`。
6. 任务脚本的 `run(page, screenshot_dir)` 按固定操作序列执行非视觉检查，并按 canonical key 返回 0 或 1。
7. `capture_visual(page, screenshot_dir)` 截取正式视觉证据，并将白名单写入 `website/summary.json.screenshots`。
8. 视觉 Judge 的每次 attempt 只包含视觉 Rubric 和全部白名单截图。源码、transcript、动态评分结果和 `failure-*.png` 不进入请求。
9. `merge_website_evidence()` 按原始 Criterion 权重合并动态与视觉结果，写入 `score.json`。

## 5. 任务级检查脚本契约

脚本路径为：

```text
eval/checks/website/tasks/task_<序号>_<任务后缀>.py
```

文件名必须与任务 ID 中 `task_...` 后缀一致，并导出：

- `RUNTIME_KEYS`：Rubric 中所有非 `visual_layout` key；
- `VISUAL_KEYS`：Rubric 中所有 `visual_layout` key；
- `async run(page, screenshot_dir)`：执行确定性操作与断言；
- `async capture_visual(page, screenshot_dir)`：可选，返回正式截图 manifest。

每个检查点只负责一个 Rubric Criterion。应优先使用 role、accessible name、`label`、`placeholder` 和明确文本定位；只有语义定位不足时才使用稳定属性。检查必须验证操作后的可观察状态，而不是仅验证点击没有报错。例如删除记录后同时核对列表、汇总、图表和排名，刷新持久化后重新核对页面状态。

新增 Web 用例的站点实现应满足：

- 交互控件使用原生 `button`、`input`、`select` 或等价 ARIA role；
- 表单字段有稳定且唯一的 `label` 或 placeholder；
- 对话框使用 `role=dialog`，展开控件维护 `aria-expanded`；
- 业务状态可以从 DOM、Canvas 文本捕获或明确属性观察；
- 初始数据固定，日期、金额、排序和筛选结果不依赖当前时间或随机数；
- 持久化只使用本地确定性存储，浏览器刷新后可复现；
- 图片、字体和业务数据不依赖外网。

这些要求不是规定统一的页面布局，而是保证不同站点都能通过用户可感知语义被稳定操作。仅依赖 CSS 层级、随机 class 或坐标点击的页面无法得到稳定检查结果。

## 6. 评分与产物

动态结果写为 `automated.<key>`，视觉结果写为 `llm_judge.<key>`。缺失 key 显式按 0 处理，并记录到 `_grading.missing_runtime_keys` 或 `_grading.missing_visual_keys`。`_dimensions` 使用：

```json
{
  "metric_profile": "web-site-gen",
  "evidence_mode": "browser_runtime+visual_llm"
}
```

正常批量评测的 run 目录新增：

```text
website/
  summary.json
  build.log
  server.log
  console.json
  network.json
  page-errors.json
  trace.zip
  screenshots/*.png
judge/
  summary.json
  attempt-001/request.json
  attempt-001/response.json
  attempt-001/parsed.json
score.json
```

`summary.json.screenshots` 是视觉证据唯一白名单。失败截图仍保存在 `screenshots/` 供诊断，但不会发送给 Judge。Judge 审计保存图片相对路径、MIME、SHA256 和大小，不保存 base64；请求和响应写盘前统一脱敏。

## 7. 失败语义

- 缺少 `package.json`、构建失败或站点无法启动：`website/summary.json.status=candidate_failed`，对应动态项和视觉项不能得分；
- Playwright、检查器导入或评测基础设施异常：`status=evaluator_failed`，错误同时进入评分审计，不能解释为模型能力问题；
- 单个断言失败：只将该 Criterion 记为 0，并保存 `failure-<key>.png`，其他检查继续执行；
- 外部网络请求：浏览器拦截并记录到 `network.json`；
- Judge 无有效 JSON：使用现有重试与异常输出识别，所有 attempt 保留审计；
- 正式截图缺失或无效：返回 `WEB_VISUAL_EVIDENCE_FAILED`，不回退到源码猜测视觉质量。

## 8. 验证记录

2026-08-13 在 macOS Docker Desktop、`wildclawbench-astroncode-ubuntu:v0.4-ppt` 上完成两项真实验证：

- task 005 动态检查执行 21 个 Criterion，15 个通过、6 个按站点实际行为失分；构建、启动和浏览器流程成功，console/page/network 异常均为 0。收紧后的“最大支出分类及金额”检查为 0，未再被页面其他区域文本误判。
- task 001 完整动态加 Claude Judge 流程一次成功，`overall_score=0.90`；内容、交互、视觉一级维度分别为 1.00、0.80、1.00。Judge 请求只包含 `desktop-home.png` 和 `faq-section.png`，未包含诊断截图、源码、transcript、动态结果、base64 或凭据。

上述记录证明两条关键链路可用，不代表五个 Web 任务已在本次代码上重新完成整批评测。正式发布前仍应按目标模型和 Harness 重跑完整 Web 范围并执行报告有效性门禁。
