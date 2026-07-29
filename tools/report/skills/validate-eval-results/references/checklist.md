# 评测结果有效性检查清单

## 自动检查

| 方面 | 核心问题 | 典型证据 | 默认级别 |
|---|---|---|---|
| 结果完整性 | unit、任务、run、score/status/usage/transcript 是否齐全可解析；run 文件缺失是否由前置模型/Harness 失败导致 | 路径、缺失文件、JSON 错误、failure_stage | FAIL/REVIEW/INFO |
| 得分合法性 | `overall_score` 是否为有限数且在 `[0,1]`，summary 是否可复算 | 原值、重算均值 | FAIL |
| 横向可比性 | 各 unit 任务集、run 数、timeout 是否一致 | 每 unit 任务数和配置 | FAIL/REVIEW |
| 执行状态 | finished/error/timeout 是否矛盾，错误责任属于评测框架还是模型/Harness | status、timed_out、error、轨迹 | FAIL/REVIEW/INFO |
| 用量指标 | token/request/cost 是否非负，请求数能否从原始事件复算 | usage 与 transcript 事件 | FAIL/REVIEW |
| 环境故障 | 认证、限流、服务端、网络、磁盘、权限、容器、视觉通道是否失败 | runtime events、原始 session、runner/status 结构化字段 | REVIEW/FAIL |
| 共因故障 | 是否有代理健康检查、网关、Docker daemon 或宿主机日志直接证明共享基础设施故障 | 结构化故障事件、受影响 unit 列表 | FAIL |
| 版本配置 | 同 unit 是否混用 harness 版本、镜像 | execution_status 字段 | FAIL/REVIEW |
| 数据污染 | 不同任务是否共享完全相同 transcript | SHA-256 与路径 | FAIL |

## 人工复核

1. 评测前置资源是否一致：容器镜像、CPU/内存/磁盘、网络策略、代理、API endpoint、密钥权限、预置文件和时钟。
2. 运行时段是否存在系统性干扰：供应商故障、限流、并发拥塞、宿主机负载、磁盘满、容器残留、批次中断或重启。
3. 环境问题的作用域是否被正确判断：单模型或多数模型同任务同时间出现都不能单独证明共享环境故障；共现只提升调查优先级，必须补充代理健康、网关或宿主机的直接证据。
4. 超时是否可归因：模型循环/低效或任务未完成属于能力结果，不影响有效性门禁；只有 timeout 配置错误或评测框架阻塞才影响有效性。
5. API 来源是否明确：模型 MaaS、grader、GitHub/搜索/邮件/日历/图像/语音工具、任务 mock 必须分开。模型 API 429/5xx 默认 `external_service/REVIEW`，不能按受影响模型数升级。
6. 评分是否可执行且确定：grader 依赖、模型裁判、随机性、文件权限和输入资产是否正确；抽样复核高分、零分和边界分。
7. 多轮评测是否存在顺序效应、缓存污染、复用 workspace、重复 seed 或失败重试选择偏差。
8. 被过滤、补跑、手工修正的数据是否有审计记录，最终报告是否只使用已确认范围。

## 判定边界

- 确定性结构错误、不可复算或不可比数据判 `FAIL`。
- 明确的评测 runner、任务准备、容器调度、轨迹采集、grader 或数据解析错误判 `FAIL`。
- 超时、Harness 非零退出、过早结束、工具协议不兼容等已归因的模型/Harness 结果只记 `INFO`，不改变门禁结论。
- 模型 API 429/5xx 仅由结构化模型请求错误触发，单模型和多模型场景均判 `REVIEW`；日志、工具输出、模型文本和任务代码中的关键词不触发。
- 无法区分评测框架与模型/Harness 责任的执行错误，以及比例异常和统计分布异常判 `REVIEW`。
- 修复数据文件不能替代重跑；只有明确的数据解析缺陷（如旧版 `request_count` 聚合错误）才可在备份和审计记录下重解析。
- 报告中应明确剥离“非模型能力问题”，但不得静默删除异常用例或只汇报有利子集。
