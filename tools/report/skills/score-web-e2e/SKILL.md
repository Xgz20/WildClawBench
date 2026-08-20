---
name: score-web-e2e
description: 在桌面评分智能体中对单个 Web 站点用例独立评分；作为可单独安装和升级的离线 Skill，驱动 Agent 启动候选站点、使用自身浏览器按 Prompt、Expected Behavior 和 Rubric 操作取证，并用 Node.js 校验生成标准 JSON。不得调用 WildClawBench 评分流程或固定 Playwright checker。
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

## 评分流程

1. 读取 `private-scoring/task_contract.json` 和 `.web-e2e-scoring-ready`，校验批次、题目、Harness 和哈希。`execution_record.json` 默认不存在；存在时再读取并校验执行状态和资源字段。
2. 在 `workspace/` 检查 `package.json`，由评分 Agent 执行：

   ```bash
   cd workspace
   npm install
   npm run build
   npm run start -- --host 127.0.0.1 --port 4173
   ```

   只监听 `127.0.0.1`，不得使用真实凭证。每题开始前关闭上一题服务并清理相同 Origin 的浏览器存储。
3. 实际点击、输入、切换、刷新、改变视口或上传文件验证检查点；不得只看源码、静态 DOM 或截图推断交互成功。
4. 逐 criterion 记录动作、观察、理由和证据。视觉检查点必须有视口截图；交互检查点必须写明动作前后状态。
5. 使用评分智能体必有的 Node.js 执行确定性辅助脚本，测试人员不手工运行命令。先从当前已安装 Skill 的实际位置解析 `<score-web-e2e-skill-dir>`，不能假设题目内存在 `.agents/skills/`：

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

脚本只校验字段和计算分数，不替 Agent 判断。criterion 为 0–1；页面美观度是独立 0–100 指标，`included_in_total=false`。定义为 `pending_definition` 时必须是 `null`。

证据不足、浏览器不可用、站点无法启动或评分异常时，使用 `evaluation_status=evaluation_error` 并保留错误事实，不伪造成功。

## 回传准备

全部单题完成后，可在一个不参与评分的管理会话中选择 Harness 根目录并运行：

```bash
node <score-web-e2e-skill-dir>/scripts/build_submission.mjs \
  --package-root . \
  --output submission.json
```

运行前先关闭所有站点进程；由管理 Agent 只删除本次 `npm install` 生成、可重新安装的 `execution/tasks/*/workspace/node_modules` 和 `score/tasks/*/workspace/node_modules`，以及候选过程意外生成的 `.git`，不得删除源文件或评分证据。

脚本校验全部 `task_score.json`、证据路径、身份和敏感文件，并阻止把残留的 `node_modules`、`.git` 打入回传包，然后生成根目录 `submission.json`。随后测试人员使用 ZIP 工具压缩整个 Harness 根目录回传；报告 Skill 会从 ZIP 中定位唯一 `submission.json`。

详细字段见 [references/scoring-contract.md](references/scoring-contract.md)。
