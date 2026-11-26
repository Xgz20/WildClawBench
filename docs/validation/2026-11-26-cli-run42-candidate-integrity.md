# CLI 执行 #42、评分组 #7 异常排查

## 远程原始证据

2026-11-26 对 `172.31.101.44:9619` 只读检查。原执行成功，评分组失败；用例为
`01_Productivity_Flow_task_005_support_handoff`，结果 ID `937`，执行与评分版本均为 v1。

评分目录：
`/data1/astron/claw/astronclaw-eval/wildclawbench/wcb-output/run-42/scoring-jobs/7/937`。

- 评分使用 AStudio、DeepSeek-V4.1-Flash、High、模板 `winarena-pc-20261125-a`。
- 冻结模板绑定记录的控制器修订为 `4adaa72571149964ac0d8e44dcfab3228b79a14a`，
  镜像 digest 为 `sha256:363af9d8d3d4dd0f15126d6d084586679b1d12df62741545e6194e8337990240`。
  此处为冻结配置身份，未另行核对 AgentCube 平台的实际 Pod 镜像。
- 留存 `health.json` 显示 `healthy`、协议 `wgui.v2`；首个调用的原生报告为
  `completed`、`product_event:task_complete`。
- 首个调用的 `astudio-runtime.json` 显示实际就绪版本 `3.7.0`，从模板 `3.7.1`
  按既有运行配置准备；`loginSource=template`、`sessionRestored=false`。
- 远程 `src/cli_scoring.py` SHA256 为
  `c644e11d9c407eea1f98b5dc6c7b957959aae6e7ee3a75239ab998cf8b1b07a1`，
  与排查前本仓库 HEAD `9c229727` 中该文件一致。

`operation.log` 中三次裁判尝试均为 `CLI_JUDGE_CANDIDATE_DRIFT`。
对应 `judge-calls` ID 为 `10b995cad6bd4d058a49b7dc61a176e3`、
`7fa0bfcc76e84078af05ad967f87c372`、`e343994747ec4f0eb59adbd50c5a4b8c`。
三个原生裁判都返回了 JSON，但框架在回传校验阶段拒绝。

三次各有 8 个目录/文件条目，其中 6 个文件的路径、大小及 SHA256 均与输入一致。
差异是文件权限从 `0644` 变成 `0444`，系 Windows 回收包的只读保护策略。
原实现把 POSIX mode 也计入跨系统比对，导致误判。

`result.json` 虽保留规则小计 `0.7`，但 `_grading.llm_notes` 是
`judge failed: CLI_JUDGE_CANDIDATE_DRIFT`。平台正确拒绝发布此小计为有效分数，
却只保存了“评分用例轮次 #937 未形成有效分数”，详情也没有直接显示错误。

## 修复与验证

- 桌面评分比较路径、条目类型、大小和内容 SHA256，允许权限位在跨系统回传时变化。
  保存 `candidate-integrity.json`，记录输入、回传清单及校验结论。
  Docker CLI 评分与冻结输入的原有严格校验维持原语义。
- 平台保存原始裁判错误及日志位置；历史通用错误按本作业、本轮次的回执只读补充原因，
  不修改数据库历史、不混用评分组或执行版本。
- 逐轮评分列表和评分详情直接显示异常，并跳转该次评分的日志与产物目录。
- 本地验证：框架 6 项 unittest（含权限变化通过、同大小改写、增删、改名、类型变化拒绝）；
  平台后端 35 项回归、前端 8 项回归、所改前端文件 ESLint 和生产构建通过。
- 修复前留存证据的三组完整内容清单比对均通过；未启动任何新评分或重新使用旧分数。
  本轮未修改远程部署或原始执行/评分记录，正式重评由用户手动验收。
