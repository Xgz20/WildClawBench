---
name: score-web-e2e
description: 在桌面评分智能体中对单个自建或 ArtifactsBench Web 用例独立评分；按 task contract 选择详细指标或原始 0–10 轻量 Profile，驱动浏览器操作取证并用 Node.js 生成标准 JSON，不调用 WildClawBench 评分流程或固定 Playwright checker。
---

# Web E2E 单题评分

每个评分会话必须且只能评分一个 `task_id`。测试人员把以下目录选为评分智能体工作空间：

```text
<harness-package-root>/score/tasks/<task_id>/
```

当前根必须同时存在：

```text
workspace/
private-scoring/task_contract.json
.web-e2e-scoring-ready
```

`score-web-e2e` 必须由评分智能体的 Skill 管理功能独立安装并启用，不从当前题目目录加载。管理员通常分发 `<batch_id>__score-web-e2e-skill.zip`；同一版本每台评分客户端只安装一次，升级时替换独立 Skill 即可。

不得访问工作空间父目录或其他用例。新会话只隔离对话上下文；单题工作空间用于隔离文件索引和评分结果。

先读取 `task_contract.json.metric_profile`：缺失时按旧包兼容为 `web-e2e-detailed-v1`。

- `web-e2e-detailed-v1`：Criterion 使用归一化 `score`（0–1），生成功能一级/二级维度和独立美观度结果。
- `artifactsbench-web-v1`：严格按 Rubric 的原始 0–10 整数锚点填写 `raw_score`；脚本确定性生成 `score=raw_score/10`。不填写独立美观度，不生成一级/二级维度。Rubric 中声明截图采证的 Criterion 仍必须引用截图，这只是原始 Criterion 证据，不是额外美观度指标。

## 评分流程

1. 读取 `private-scoring/task_contract.json` 和 `.web-e2e-scoring-ready`，校验批次、题目、Harness 和哈希。`execution_record.json` 默认不存在；存在时再读取并校验执行状态和资源字段。
2. 不预设候选站点的前端框架、包管理器、构建工具或启动命令。先只读检查 `workspace/` 中的 README、`package.json`、`packageManager`、锁文件、scripts、框架配置、`index.html` 和已有构建目录，再按实际产物选择启动方式：

   - Node 工程：优先遵循项目自己的启动说明；根据 `packageManager` 和锁文件选择 npm、pnpm、yarn 或 bun，不混用包管理器。只在依赖缺失且启动确实需要时安装依赖；只在项目声明的预览或生产启动方式需要构建时执行 build。启动前读取 scripts 的真实内容，不得默认项目一定存在 `build`、`start`，也不得把 Vite 参数盲目传给其他服务器。
   - 原生 HTML/CSS/JavaScript 或已有静态构建产物：不得为了适配评分流程而创建 `package.json` 或安装前端依赖。使用评分 Skill 内置的零依赖静态服务器，例如：

     ```bash
     node <score-web-e2e-skill-dir>/scripts/serve_static.mjs \
       --root workspace \
       --host 127.0.0.1 \
       --port 4173
     ```

     单页应用需要 history fallback 时增加 `--spa-fallback`。若入口位于 `dist/`、`build/` 等目录，`--root` 指向实际可发布目录。
   - 其他技术栈：遵循仓库内可验证的启动说明和配置；不要改写候选源码或脚本来迎合固定命令。无法确定安全、可重复的启动方式时记录 `evaluation_error`，不要猜测。

   无论采用哪种方式，都只监听 `127.0.0.1`；启动后先访问实际 URL，确认页面和静态资源可加载，再开始评分，并把实际 URL 写入 `score_input.json.site_url`。不得使用真实凭证。每题开始前关闭上一题服务并清理相同 Origin 的浏览器存储。
3. 开始浏览器评分前读取 [浏览器交互评分与误判防护](references/browser-interaction-scoring.md)。每个 criterion 先恢复其“预设状态”，再实际点击、输入、切换、刷新、改变视口或上传文件；不得携带前序检查点的污染状态，也不得只看源码、静态 DOM 或截图推断交互成功。
4. 首次操作未生效时，不得立即记 0。日期/时间、清空输入、取色器、滑块、HTML5 拖放、原生对话框、下载和瞬时状态必须使用参考文档中的适配方式复核，并回读操作前、提交前和提交后的公开状态。源码只用于识别控件和事件模型，不能替代页面验证。
5. 逐 criterion 记录动作、观察、理由和证据。视觉检查点必须有视口截图；交互检查点必须写明动作前后状态。原生对话框、下载事件、瞬时状态等无法由截图完整表达的事实可保存为 `private-scoring/evidence/` 下的 Markdown 或 JSON 观察记录并引用。
6. 在填写完成后审计所有 0 分理由。如果理由实质是“评分工具无法输入、拖动、捕获或验证”，或评分员主动跳过删除、清空等 Rubric 指定操作，必须先按交互指引复核；仍因工具限制无法判定时使用 `evaluation_status=evaluation_error`，不能伪装成候选功能失败。
7. 仅 `web-e2e-detailed-v1` 读取 [美观度评分标准](references/aesthetic-scoring.md) 和 [结构化定义](references/aesthetic-rubric.json)。复用功能评分截图，常规选择 4–6 张不重复的代表性截图，覆盖桌面主状态、桌面交互状态、适用的空/错误/加载/选中/禁用状态，以及窄屏主状态和窄屏交互状态。简单页面允许只提供最低 2 张桌面图和 1 张不大于 480px 的窄屏图；复杂页面按实际状态增加。对带标签的截图集合做一次统一判定，不得逐图给总分后平均，也不得用重复截图改变分数。ArtifactsBench Profile 跳过本步骤。
8. 使用评分智能体必有的 Node.js 执行确定性辅助脚本，测试人员不手工运行命令。先从当前已安装 Skill 的实际位置解析 `<score-web-e2e-skill-dir>`，不能假设题目内存在 `.agents/skills/`：

   ```bash
   node <score-web-e2e-skill-dir>/scripts/init_score.mjs \
     --task-contract private-scoring/task_contract.json \
     --output private-scoring/score_input.json

   node <score-web-e2e-skill-dir>/scripts/finalize_score.mjs \
     --task-contract private-scoring/task_contract.json \
     --score-input private-scoring/score_input.json \
     --output private-scoring/task_score.json
   ```

若当前题目确实带有可选的 `execution_record.json`，在 finalize 命令中增加 `--execution-record execution_record.json`。旧包仍可继续同时传入 `--manifest task_manifest.json`，但新包不生成该文件。

脚本只校验字段和计算分数，不替 Agent 判断。详细 Profile 的 criterion 为归一化 0–1，页面美观度是独立 0–100 指标，`included_in_total=false`。ArtifactsBench Profile 的输入是 `raw_score` 0–10 整数，输出同时保存原始分与归一化分；总分按归一化 Criterion 加权后转为百分制。

详细 Profile 中，评分 Agent 填写 32 个美观度检查点状态和证据，以及 6 个一级维度的理由和证据，不填写一级维度分数。脚本将 `MET/PARTIAL/UNMET/NA` 固化为 `100/50/0/null`；每个一级维度按所属适用护栏项与加分项等权平均，再按 `15/25/20/15/10/15` 加权计算唯一美观度总分。`NA` 排除分子和分母，某个一级维度全部为 `NA` 时拒绝出分。

美观度标准内置于独立评分 Skill。旧评分包中的 `aesthetic_metric.status=pending_definition` 不影响使用新版 Skill，但旧的单一 `aesthetic_score` 输入不再有效，必须按当前结构重新填写。美观度取证自身失败时使用 `aesthetic.status=evaluation_error` 并填写错误；它不改变功能总分。

证据不足、浏览器不可用、站点无法启动或评分异常时，使用 `evaluation_status=evaluation_error` 并保留错误事实，不伪造成功。

## 回传准备

全部单题完成后，可在一个不参与评分的管理会话中选择 Harness 根目录并运行：

```bash
node <score-web-e2e-skill-dir>/scripts/build_submission.mjs \
  --package-root . \
  --output submission.json
```

运行前先关闭所有站点进程；由管理 Agent 只删除本次依赖安装生成、可重新安装的 `execution/tasks/*/workspace/node_modules` 和 `score/tasks/*/workspace/node_modules`，以及候选过程意外生成的 `.git`，不得删除源文件或评分证据。

脚本校验全部 `task_score.json`、证据路径、身份和敏感文件，并阻止把残留的 `node_modules`、`.git` 打入回传包，然后生成根目录 `submission.json`。随后测试人员使用 ZIP 工具压缩整个 Harness 根目录回传；报告 Skill 会从 ZIP 中定位唯一 `submission.json`。

详细字段见 [评分 JSON 契约](references/scoring-contract.md)。
