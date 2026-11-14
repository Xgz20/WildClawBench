# Loomy 五题三并发闭环验收

2026-11-14 在当前 `feat/loomy-macos-general-e2e` worktree 完成真实验证。
客户端为 Apple Silicon Mac 上的 Loomy 0.9.39／随包 OpenCode 1.14.22，执行模型
`imodel/spark-x2.6`、原生 `variant=high`。沿用旧 `general-custom60-v1`，数据集 digest
为 `e5fd1ed401b45729d85d7aaf9c94c36d3900c1bcb43446bb7d43cca584a2886c`。

## 验收结果

| 环节 | 结果与依据 |
| --- | --- |
| 五题执行 | 五题各发送一次；四题正常完成，一题原生 HTTP 502 失败并保留原作答 |
| 真实三并发执行 | 原生用户创建至主助手结束区间的峰值为 3；三题同时在途累计 261.377 秒，另保留三会话同时 busy 的快照 |
| 正式采集 | 五题完成原生采集、真实进程收尾、候选冻结和离线 verify-only |
| 三并发语义评分 | 三道 hybrid 各使用独立项目和新聊天；SDK 核验 gpt-6.1-sol／high、cwd、唯一冻结 Prompt 及明确完成 |
| 评分重叠 | 三个原生评分回合共同重叠 89.489 秒；北京时间 10:43:54.831 至 10:45:24.320 |
| 有效评分 | 两道 automated 由受管规则 Worker 评分；五题均为 valid，无 evaluation_error 或 unscored，均分 95/100 |
| 回传与导入 | package-return → import-return → select-import → validate-inputs 全部通过；导入副本的五题 verify-score --archived 全部通过 |
| 报告 | 同源 JSON、Markdown、Excel 生成并封存；Excel 10 Sheet、11 组关键范围检查、公式错误 0，已逐 Sheet 看图 |
| 流程状态 | unit 的 execute／collect-evidence／score／package 与 batch 的 prepare／import-return／report 均为 COMPLETED |

三并发依据来自原生消息／回合区间及运行快照，不由槽位配置推断。UI 派发仍串行。
本轮含框架修复和观察等待，流程墙钟不能作为客户端性能基准。

## 题目与原始结果

| 旧60题任务 | 原评分类型 | 原生执行状态 | 分数 |
| --- | --- | --- | ---: |
| 01_Productivity_Flow_task_009_action_reconciliation | hybrid | completed | 100 |
| 01_Productivity_Flow_task_010_launch_program_pack | hybrid | candidate_error：HTTP 502 | 85 |
| 02_Code_Intelligence_task_007_async_cache_singleflight | automated | completed | 100 |
| 02_Code_Intelligence_task_008_config_migrator | automated | completed | 90 |
| 05_Creative_Synthesis_task_007_survey_campaign_pack | hybrid | completed | 100 |

Atlas 已写出四个交付文件，最后一次主模型请求连续三次收到原生 HTTP 502；数据库
留下空的已结束助手消息，未写入 finish 或 error。框架归档同一 session、同一请求窗口
的原始主请求错误行，核对原 Prompt、模型／High、全部工具结束、后端身份及空闲状态，
按 FAILED／candidate_error 收口。独立裁判按原文件和原 Rubric 给出 85 分，失败状态
继续进入报告；没有将其改成成功或统一计零，也没有重发、换题或修改候选。

## 本轮框架修复

- `c457a4a9`、`9fa56fee`：只读探针支持后端未启动。实测随包二进制版本和 SHA；
  未观察的 PID、端口、数据库所有权与 health 保持为空，首次正常发送后按原生来源绑定。
- `360b36a0`：补齐主模型 HTTP 5xx 的原生失败证据、终态观察、离线回放、采集屏障及
  独立评分准入。辅助标题／记忆请求、其它会话、HTTP 402、未结束工具和仍忙碌后端
  不进入该准入分支；不修改 Loomy 安装包或原生数据库。
- `c36edbe9`：自动规则的 not-required 组不再显示为 None／None 独立裁判。
  报告通过显式展示配置使用“Spark-X2.6 高”，实际模型、验证信息和分数保持原样。

对应发行版本为组件 `loomy=0.1.10`、执行 `0.15.10`、采集 `0.12.11`、评分
`0.10.108`、报告 `0.8.53`。执行批次仍绑定其原始发行；修复通过独立发行和显式
source-repair-manifest 接续原 attempt，未重新 prepare 已执行批次。旧清单、状态、
journal 原字节、全部错误历史、首版报告及封存 ZIP 都保留。

Node 34 项通过；开发 Python 3.12 的 83 项与专用规则 Python 3.11 的 10 项通过，
合计 Python 93 项。覆盖冷启动来源、一次发送、原生身份、5xx 失败正反例、评分准入、
候选冻结、旧证据回放、Skill 布局、发行准备、round workspace 与报告展示。

## 产物与复核

本地验收根目录是 worktree 下的 `.agents/loomy-validation/acceptance-5x3-r2/`。
其中原件不进入源码 Git；以下均相对此目录：

- `round/Loomy/`：五题 execution、正式 evidence、原队列、源码修复清单与评分编排。
- `concurrency-audit.json`：五题原生执行和三次评分回合的区间、来源路径及 SHA。
- `scoring-control/native-completed-proof-{1..3}.json`：真实模型／High、Prompt 与完成证明；
  不导出裁判思考正文。
- `archive-score-verification.json`：导入副本五题独立验分结果。
- `visual-review.json`：10 Sheet 与全部预览检查记录。
- `acceptance-summary.json`：完整闭环的机器可读验收摘要。
- `distribution/loomy-macos-5x3-validation-20261114-r2/reports/loomy-five-three-final-v2/`：
  最终 JSON、Markdown、审计、Excel、预览和 report receipt。
- `distribution/loomy-macos-5x3-validation-20261114-r2/reports/sealed-loomy-five-three-final-v2/`：
  已封存的最终规范报告 ZIP。

回传包 SHA256：`99ba01d6bf5e4398c33076fa2a219ff4eadf7f36734ed39016849ac5f6288b6c`。
最终规范报告 ZIP SHA256：`93fcf1998d70495eb488fc05e8122d5db89e6e0e0a0a3e2229102fa446fc17ef`。

此前六题 r3 的 202 个证据文件逐一 SHA 核对无漂移，六题使用新收口器离线复验也均通过。
题目、GT、评分权重、旧发行与既有批次绑定保持原样；本轮未推送开发分支。

Token、缓存及模型请求次数的提供方语义尚未准入，正式值保持 null／unavailable，
报告显示缺失覆盖。工具数和原生任务区间已有来源；本次总工具调用 89 次。
此验收范围为上述版本、平台和五题，不外推全部旧60题或其它 Loomy 版本。
