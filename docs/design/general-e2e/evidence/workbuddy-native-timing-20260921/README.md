# WorkBuddy v8 原生任务耗时补采与并发口径更正

> 证据边界：本文只记录所列日期、批次和 revision 的事实，保留原失败与未知项。当前集成进度和下一步统一见[集成契约](../../../e2e/端到端自动化评测Harness接入契约.md#integration-progress)，不从本文旧“当前/下一步”推导最新支持状态。

2026-09-21，直接在 `feature/astroncode-eval` 实现并验证。采集提交 `5631cbd80e719c9f41df93329cc655a02d38f1c1`；报告行高修复 `f681a4247f418c99b6546e72750499d60df00065`。本轮只消费既有冻结证据，没有启动 Harness、发送 Prompt 或重做评分。

## 指标定义与实现

旧 collector 对两个时间字段硬编码 unavailable，但 v8 原 runtime binding 已归档请求的 `timestamp`、`completedAt` 和 `finishTimestamp`。新 collector 按精确 session/request/cwd/Prompt 绑定读取 runtime snapshot，即使 session JSONL 缺失也能采集耗时。

| 字段 | 起止点 | 含义 |
| --- | --- | --- |
| `agent_duration_seconds` | `request.startedAt`（缺失回退 `timestamp`）→ `completedAt`（缺失回退 `finishTimestamp`） | 原生请求生命周期，含工具和客户端处理 |
| `duration_seconds` | 冻结 `prompt.sent_at` → 同一原生完成点 | 任务流程时间，额外包含发送和排队等待 |

均为毫秒差除以 1000，不解释为纯模型推理时间。不使用 SQLite `sessions.updated_at`、文件 mtime、collect 结束时间或题目 `timeout_seconds`。缺失字段为 null、真实零值保留 0；非法类型、负值、倒序和结束字段顺序冲突失败关闭。`finishTimestamp` 略早于 `completedAt` 是正常的两个完成阶段。

`collect-general-e2e 0.7.1` 与 `report-general-e2e 0.3.2` 消费共享组件 `workbuddy-jsonl-metrics 0.2.0`。组件继续验证旧 Token 补采算法 `0.1.0`，时间补采有独立 schema/version。每题新增 `evidence/timing-supplements/<task-id>/`，绑定原 execution/resource/collect receipt、runtime binding 和旧 Token supplement SHA；报告端从归档时间再次复算。旧目录不可覆盖，未改变原评分绑定。

## 五题结果与并发复核

下表所有时刻为 2026-09-21 UTC。完整 task ID、源路径和 SHA 见本地 `timing-audit/verification.json`。

| 任务后缀 | 发送时间 | 原生开始 | 原生完成 | 原生耗时（秒） | 流程耗时（秒） |
| --- | --- | --- | --- | ---: | ---: |
| retro_agenda | 06:51:09.005 | 06:51:37.257 | 06:52:10.637 | 33.380 | 61.632 |
| support_handoff | 06:51:52.415 | 06:52:37.091 | 06:54:32.890 | 115.799 | 160.475 |
| temperature_cli_fix | 06:52:48.973 | 06:53:37.195 | 06:54:53.844 | 76.649 | 124.871 |
| colleague_leave_reply | 06:53:56.477 | 06:54:37.321 | 06:54:53.381 | 16.060 | 56.904 |
| suspicious_installer | 06:54:54.156 | 06:55:37.315 | 06:56:41.722 | 64.407 | 107.566 |
| 合计 | | | | **306.295** | **511.448** |
| 平均（5 题） | | | | **61.259** | **102.2896** |

两项均完整覆盖 5/5。报告的批次墙钟继续依据冻结 execution record，为 304.465 秒；不拿流程总和或原生总和替代。

按半开区间 `[start,end)` 复算：发送后未结束任务峰值 **3**，原生请求区间重叠峰值 **2**。v8 证明 `run_slots=3` 配置、三槽调度、2 次动态补位和每题一次发送，**未证明三路原生请求同时执行**。旧队列回执 `observed_max_concurrency=3` 原样保留，解释收窄为发送口径；G7-01 调整为主流程可用、原生三路重叠待验收。报告标题沿用冻结 batch 配置中的“三路执行验收”，应按此处的三槽调度范围理解。

## 本地报告与不可变核对

本地原件根：`/Users/gzx/debug-workspace/e2e-evaluate/wb3/v8`。

- 当前报告：`p/wb3-v8/reports/workbuddy-three-slot-v8-native-timing-v2/`，包含同源 JSON、Markdown、Excel 和报告回执。
- `timing-audit/audit.py`、`before.json`、`after.json`：633 个原文件 SHA 完全不变，覆盖原执行/候选/轨迹、Token 补采、评分/submission、旧报告、旧回传及已导入原件。
- `timing-audit/verify-results.py`、`verification.json`：逐题复算时间、两种并发峰值，并核对评分和所有非时间资源指标不变。
- 保持 5/5 valid、均分 0.8275、evaluation_error=0、unscored=0；模型响应 21、工具 19、输入 769118、输出 4347、总 Token 773465、缓存读取 703040。缓存写入、推理 Token、HTTP 尝试数仍 unavailable。
- collect receipt SHA：`1bc32b69fc92820b46bf95725ce67777097f96c96af7eaf9ea2321672a0b3a0e`；submission SHA：`09d4849d69996c4a6fd46b60acb690b3152d321e3ad446f6c72668baea5a53a2`，均未改变。
- 新 package ID：`e153170edbf98413fe0e250fc1f602fa989da5297300f6a16d507cd7f6e311df`；ZIP SHA：`ebbd631cf8d00ad610d3ce75ce9b1b423c41562e73c4cc31260b375b0df4fa5a`。归档位于 `timing-audit/returns/`；已 import 并显式 select，旧包保留。
- 当前报告 JSON SHA：`8270833dbc37198df31c60612fe61a11032a2518cc0d4da362eabeb027866bda`。
- 当前 Markdown SHA：`2b9e651b67d02bf121e3287dc635a70cf4965ab8b9fe752a8d3d73f3bcd27dd2`。
- 当前 Excel SHA：`cc2028c70134f30698fe199a26aa4a93cca88cb3910ae6f09117c31c11013e46`。
- 报告回执 SHA：`94073fd5996a7ba1c7e403de8e8c5942712cafdef601c1f2608d0bd7ae7f3271`，已登记；batch/unit 的 `recommended_actions=[]`。

## 发行与验证边界

正式发行：`report-workspace/general-e2e/releases/workbuddy-native-timing-20260921-v2`，源码 `f681a4247f418c99b6546e72750499d60df00065`；suite SHA `97e6b5a3aabd1b6dfe31602892b609e5ade326e76461b1bfe242dab1faa49046`，catalog SHA `f829535ef33279a5e73de4e09285e95d7cc07bf860b5b4d12732e438ecf2da57`。release-root/suite 和七 Skill 验包通过。首次报告构建保留在 `workbuddy-three-slot-v8-native-timing`；v2 修复新耗时依据的固定行高截断，不改变数值。

General Node 172/172；Python layout/build/report/run 47/47。追加原生来源篡改、无 Token 补采兼容检查后，WorkBuddy 专项 7/7；报告行高修复后 layout/report 15/15。新 collector fixture 通过正式 finalizer，覆盖 JSONL 缺失但时间仍可采、缺值、零值、回退、非法时间和补采重算防篡改。真实 v8 五题补采、脱仓打包/导入/报告通过；Excel 四 Sheet、四个关键范围、公式错误 0，四张初版预览及修复后的受影响预览已检查。

本次是采集与报告验证，不是新 Harness 执行 smoke。未修改 timeout 策略、未派发平台任务、未 push。剩余 WorkBuddy 原生三路重叠须使用新真实运行验证，不以本次补采或离线测试替代。
