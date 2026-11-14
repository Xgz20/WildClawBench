# 端到端执行器机器协议 v1

平台、Python 脚本与执行 Skill 共用 eval/run_e2e.py。平台在子命令前传入 --api-version 1。响应包含 schema、api_version、type 和 data，type 为 result、event 或 error。

支持 `runtime-preflight` 能力的发行可使用 `preflight --plan PLAN --check-runtime`，额外验证执行进程的 AgentCube Token、User-ID、TTL 和端点域名解析。失败返回 `valid=false` 及具体 issues，不创建沙箱。默认 preflight 仍可离线检查选题和参数；带 `--agentcube-config` 的原调用规则保持兼容。该检查不验证远端账号权限或 VM 可用性，实际执行仍需可访问的公司网络。

```bash
python eval/run_e2e.py --api-version 1 describe
python eval/run_e2e.py --api-version 1 catalog --scenario general --dataset general-custom70-v4
python eval/run_e2e.py --api-version 1 preflight --plan /absolute/plan.json
python eval/run_e2e.py --api-version 1 run --workspace-root /absolute/results --plan /absolute/plan.json --agentcube-config /absolute/identity.json --jsonl
python eval/run_e2e.py --api-version 1 status --workspace-root /absolute/results --batch-id example
python eval/run_e2e.py --api-version 1 events --workspace-root /absolute/results --batch-id example --after-cursor 0
python eval/run_e2e.py --api-version 1 artifacts --workspace-root /absolute/results --batch-id example
python eval/run_e2e.py --api-version 1 export --workspace-root /absolute/results --batch-id example --purpose scoring --output /absolute/download.zip
python eval/run_e2e.py import --workspace-root /absolute/local --archive /absolute/download.zip
```

describe 返回 Git revision、能力、场景、模板、模型和参数元数据。模板目录可由执行器 WCB_E2E_CAPABILITIES_FILE 配置，未注册驱动的条目为 enabled=false。

catalog 复用数据集锁和 Web parser，preflight 与 prepare 共享范围解析器。预检返回 selection_sha256、实际题目和执行数量，并检查已声明运行要求。传入身份配置时还检查配置及 TTL。预检只读取材料。

run --jsonl 的持久化事件与 events 的 data 结构相同。cursor 是本批次递增序号，消费者按批次和 cursor 去重。恢复继续读取原批次游标。status 将内部状态投影为 state、terminal、资源、采集及备份字段，平台按事实判断可用操作。

schemas/e2e-api-v1 提供计划、状态、事件、产物和结果包的 Draft-07 Schema。同协议版本允许增加可选字段，破坏性变化使用新主版本。产物按清单 path 定位，执行器检查路径和链接。

purpose=scoring 整理成功题的本地 Skill 标准输入。结果包保留父范围、失败现场和实际覆盖缺口。LOCAL_START.md 描述路径恢复和 Skill 接续。外部 receipt 用于核对整包 SHA，单 ZIP 导入同样验证包内完整清单、成员摘要与父批次锁。

退出码 0 表示命令成功返回，1 表示执行范围含失败，2 表示输入或协议错误，3 表示待处理，130 表示观察中断。业务终态以公开快照与回执判断。

## 本地接续与覆盖

结果包的 `selected_scope` 是本次导出范围，`parent_scope` 保留父批次全部执行身份。`not_exported` 与 `unavailable_executions` 区分未选择和未封存条目。选中题目的 `task-inputs/` 同时保留题目定义、发送 Prompt、依赖和私有评分材料。

`purpose=scoring` 会为可评分执行生成单题标准输入。导入回执的 `scoring_contexts` 提供本机 context 和冻结 Skill 路径，其余路径相对 context_root。`local_reports` 为每个成功题提供 General 标准 batch-root 或 Web 报告 YAML。先对独立单题评分，再使用相应 run/report Skill 收口回传和报告。按父范围检查多配置、多 run 和失败题覆盖，General 多来源汇总沿用 report-general-e2e 的显式逐题来源选择。

产物清单的 `source` 说明来源。`final_response` 来自绑定原生完成轨迹。`completeness=present` 表示当前文件可读取，其 SHA 供传输对账，执行完整性和备份校验以快照、原始 seal 及 backup receipt 为依据。失败原生轨迹明确标为 partial 或 missing。原始包导入会重新验证整包成员集合、成员摘要及 capsule 绑定。

取消沿原身份停止派发，采集并封存已派发任务后释放沙箱。采集或进程清理尚未核验时保留 NEEDS_ATTENTION。Windows 清理回执在进程变更前落盘，恢复复用已观察的 PID、创建时间和路径，补充收口已记录的工作区服务。观察中断与取消分别记录，`resume` 接续原远端 job。

执行器发行使用只读版本目录部署。批次保存 root、Python、Git revision、api_version 和冻结参数。该路径在批次生命周期内需保留原发行，平台默认发行的更新仅影响新批次。

支持 `windows-astudio-runtime-bootstrap` 的发行可在 AgentCube 身份 JSON 中显式配置 `astudio_runtime`：`version`、HTTPS `download_url`、`size`、`sha512` 固定官方 Windows 安装包；可选 `session_file` 指向本机 0600 的原生 AStudio 登录快照，`sync_clock` 默认 true。登录快照必须来自用户授权的账号，不包含在输入包、日志或结果导出中。AgentCube Token 仍只从环境注入，两类凭据不能混用。

该准备步骤在题目派发前运行，校验安装包大小及 SHA-512、核验 app.asar 版本，并在候选 Workspace 之外保留受保护的旧状态备份。它按明确运行配置准备克隆沙箱，不改共享模板或既有冻结发行。Windows 时钟与控制器 UTC 偏差超过 120 秒时先校正，原有轨迹不改写。安装和登录恢复意图、配置指纹及状态回执可恢复；启动回执不明时只观察原状态文件，不重复启动安装。恢复时拒绝替换已有运行配置或登录快照。

当前默认模板 winarena-pc-20261104-a 发布已验证的 Auto/High 与 Spark-X2.5/High。2026-11-09 的 Max 配置两次在 controller select_reasoning 阶段被拒绝，默认目录已收口到 high，预检会拒绝未发布档位。新增可用组合通过执行器能力文件发布。

scoring-purpose 导出另提供 parent_reports，按 run 保存完整父 General 范围的 report-only manifest 与 report-config，保留原输入制品锁。接收方将独立单题标准回传导入为显式来源后，可直接将其 path 交给 selected_report.py 的 --batch-root，按 expected_execution_keys 检查全范围。coverage_status 区分完整与部分材料，单题快速评分仍使用 scoring_contexts。包索引记录 exporter_revision，执行发行仍由 parent-batch 的原快照保存。新版只读导出器可在协议 v1 下整理旧批次的封存原件。
