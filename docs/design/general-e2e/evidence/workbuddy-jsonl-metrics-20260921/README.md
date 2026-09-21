# WorkBuddy v8 原生模型响应与 Token 补采

2026-09-21，在工作区分支 `feature/astroncode-eval` 完成采集修复及 v8 旧产物补采。实现提交 `d6883269eb2a94799e27e8fcdd951edb72bb3e92`；collect Skill `0.7.0`、report Skill `0.3.0`、新增共享组件 `workbuddy-jsonl-metrics 0.1.0`。

后续[原生耗时补采](../workbuddy-native-timing-20260921/README.md)已生成包含 Token 与耗时的新报告；本页 Token 数据、补采目录及旧包均保留。原生请求重叠峰值复核为 2，历史“默认三路已验收”收窄为三槽调度已验收。

## 更正与验证范围

旧 General collector 只读取 runtime API 的顶层 `request.usage={}`，并把一个用户请求计为一个模型请求。客户端实际已把每次模型响应的 `providerData.rawUsage / usage` 写入 `~/.workbuddy/projects/<编码工作目录>/<sessionId>.jsonl`。本次复用公共解析器，以 session/cwd、runtime trace ID、原 Prompt/user_query、工具调用集合和回复内容核对归属，按 `providerData.messageId` 去重；多个工具和三种 usage 镜像不重复累加。

新 collector 在首次正式采集时自动归档 JSONL、更新 trace-index 与 resource metrics。JSONL 缺失时模型响应数保持 null；不会继续用顶层用户请求数代替。原始请求重试和未落盘失败没有完整证据，`request_attempt_count` 仍 unavailable。原始 usage 不含推理 Token 时，不能把归一化字段中的默认 0 当作实测。

对 v8 已评分的冻结数据，新增 `evidence/resource-supplements/<task-id>/`，保存原 JSONL、指标和补采清单。清单绑定旧 execution record、resource metrics、collect receipt 的 SHA；报告从补采 JSONL 再次计算并核对数值。旧 record、candidate、标准轨迹、score、submission 和报告不修改。

## 五题更正结果

| task ID | 模型响应数 | 工具调用数 | 输入 Token | 输出 Token | 总 Token | 缓存读取 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `01_Productivity_Flow_task_003_retro_agenda` | 1 | 0 | 35202 | 543 | 35745 | 10240 |
| `01_Productivity_Flow_task_005_support_handoff` | 8 | 9 | 301172 | 2112 | 303284 | 282432 |
| `02_Code_Intelligence_task_001_temperature_cli_fix` | 6 | 6 | 217104 | 692 | 217796 | 212288 |
| `03_Social_Interaction_task_003_colleague_leave_reply` | 1 | 0 | 35377 | 91 | 35468 | 22144 |
| `06_Safety_Alignment_task_001_suspicious_installer` | 5 | 4 | 180263 | 909 | 181172 | 175936 |
| 合计 | **21** | **19** | **769118** | **4347** | **773465** | **703040** |

以上字段完整覆盖 5/5 任务、21/21 已落盘模型响应。输入已包含缓存读取，不再次相加。按这些原生总量派生的输入缓存命中率为 91.4086%；该比例不是新的评分项。缓存写入、推理 Token、HTTP 总尝试仍不可观测。

## 本地回传与报告

- 原件根：`/Users/gzx/debug-workspace/e2e-evaluate/wb3/v8`。
- 新报告目录：`p/wb3-v8/reports/workbuddy-three-slot-v8-jsonl-metrics`；旧 `workbuddy-three-slot-v8` 目录保留。
- 原始文件对账：`resource-audit/before.json` 和 `after.json`，131 个原文件 SHA 全部相同，含五题执行证据、候选、dispatch journal、五份 score、submission 和旧报告。
- 新 package ID：`7e09ceb0848c79d31e6a7e81f8ee8d0a9bc437f44d2307803fc627c9c7094d66`。
- 新 ZIP SHA：`9afb1d2ed7943f0f39cd4a48da7e1b276e3f32889dd8fdaa35700b4ec4f62f3d`。
- 新包导入产生预期冲突，显式选择新 package；旧包 `e7f6dc50...43627` 保留。unit、batch 均无待执行动作。
- 评分仍为 5/5 valid、均分 0.8275、evaluation_error=0、unscored=0；没有重跑 Harness 或 Judge。
- 新报告 JSON / Markdown / Excel SHA：`593037fa0ac9e2fd6c4be3ae8f102a75c2088561bc83bc341d6903dd6742802f` / `202b29901cb23d6e6606a89bbb2f7fc10bf5e87f6b85a912cfcf174840c730f8` / `09f9a0a4801c25b3441750b98122caccad4e7b7e071e40f59b2f28712984a799`。

## 分发与检查

生产套件：`report-workspace/general-e2e/releases/workbuddy-jsonl-metrics-20260921`，source revision 为上述实现提交，suite SHA `37dd52b8b642024b5f50fe2c16dec1d24addfb476adb56c62ffa1e76fe842755`，catalog SHA `eb49aa8e8d51be4dec98a802f0bbc177b9e6b3c3a8dfc1f0db0115da5b7e3aea`。调试构建与生产构建同 SHA；套件、目录及七 Skill 校验通过。

General Node 170/170；Python 布局/打包/报告/回传 47/47；源码布局和 diff 检查通过。新增测试覆盖多工具去重、缺失覆盖、raw/normalized 冲突、跨会话/请求/Prompt/工具集合/回复污染、补采不可覆盖，以及修改指标并重算清单哈希仍被复算拒绝。新 collector 生成的含 JSONL 证据通过通用 finalizer；真实 v8 补采五题及新回传报告验证通过。Excel 四 Sheet、四个关键范围、公式扫描和四张预览通过。

本次验收是已有原生日志的采集/补采/回传/报告验证；没有用新 suite 再执行五题。既有三槽调度真机结论仍对应 v8 原执行源码与冻结身份，不证明原生三路请求同时执行。
