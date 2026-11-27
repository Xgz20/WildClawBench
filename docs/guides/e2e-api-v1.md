# 端到端执行器机器协议 v1

平台、Python 脚本与执行 Skill 共用 eval/run_e2e.py。平台在子命令前传入 --api-version 1。响应包含 schema、api_version、type 和 data，type 为 result、event 或 error。

支持 `runtime-preflight` 能力的发行可使用 `preflight --plan PLAN --check-runtime`，额外验证执行进程的 AgentCube Token、User-ID、TTL 和端点域名解析。失败返回 `valid=false` 及具体 issues，不创建沙箱。默认 preflight 仍可离线检查选题和参数；带 `--agentcube-config` 的原调用规则保持兼容。该检查不验证远端账号权限或 VM 可用性，实际执行仍需可访问的公司网络。

`--agentcube-config` 指向非密钥 JSON 配置；平台通过 `WCB_E2E_AGENTCUBE_CONFIG` 引用同一文件。`namespace` 未填写时为 `agentcube-windows`，同时用于会话创建请求和 PicoD/Windows 路由。以下为相关字段示例，其余身份、地址和运行时字段按部署配置保留：

```json
{
  "namespace": "agentcube-windows",
  "template": "winarena-pc-20261118-a",
  "create_timeout_seconds": 1800
}
```

`create_timeout_seconds` 为创建会话的 HTTP 读取等待上限，必须为正整数，默认沿用 900 秒。它独立于单题执行预算；增加创建等待时间会相应增加预检要求的 expire TTL 余量。模板选项仍来自能力目录，修改模板时同步核对该目录。新配置用于新批次，保留旧配置文件供既有冻结批次恢复。创建超时且未得到 session ID 时保持 `NEEDS_ATTENTION`，须先核对原平台请求，不自动重复创建。

操作员在控制台将唯一实例与原请求核对、确认已销毁后，可用 `reconcile-absent-creation --workspace-root ROOT --batch-id ID --execution-key KEY --platform-proof JSON --expected-proof-sha256 SHA --agentcube-config CONFIG` 收口派发前的创建超时。观测 JSON 使用 `wildclawbench.agentcube-creation-observation/v1`，包含原 `identity`、`creation_intent_at`、精确 `session_id`、`app_id`、`user_id`、`namespace`、`template`、带时区的 `created_at/destroyed_at/observed_at`、`source_url`、`observed_state: destroyed` 和 `matching_session_count: 1`。这份文件是操作员核对记录，不能替代线上检查；命令还会用冻结身份对精确 session ID 执行只读查询，只接受平台明确的同 ID `not found` 回执。已派发任务、身份/时间不匹配、存活或无法确认的会话均拒绝释放本地占位。原错误、观测与查询回执先封存备份，再追加创建失败状态；不改批次清单或执行器绑定，不生成可评分结果，不创建或删除远端会话。

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

## 多题、多轮次执行重跑

发布 `execution-selection-rerun-v1` 能力的发行支持 `rerun-selected`。重复传入
`--execution-key` 选定明确的 `(unit_id, task_id, run_index)`，可同时覆盖多个题目和
配置单元；不传空范围，不把空选择解释为整批重跑。示例：

```bash
python eval/run_e2e.py --api-version 1 rerun-selected \
  --workspace-root /absolute/results --batch-id example \
  --execution-key unit-a/run-0001/task-1 \
  --execution-key unit-a/run-0002/task-2 \
  --request-id rerun-errors-001 \
  --expected-attempts /absolute/expected-attempts.json \
  --agentcube-config /absolute/identity.json --jsonl
```

`expected-attempts.json` 是执行身份到旧 attempt ID 的映射。控制器在同一个事务中
验证全部范围、资源状态和期望版本，再创建选中轮次的新版本；任一未知或过期身份
使整个选择失败，不部分重置。相同请求 ID 和相同范围可幂等续接，不重复派题；
请求范围改变或已被后续执行替代时拒绝复用。

选中轮次共用原批次的并发调度器，不由平台逐题启动互相竞争的控制器。未选中
轮次、旧原件、备份与评分历史保持原绑定。新执行版本需要重新评分。
`--cancel-before-dispatch` 仍创建可审计的新版本，但取消其派发。
原 `rerun-case`、单轮重跑、执行历史和版本化导出接口保持兼容。

## 本地接续与覆盖

结果包的 `selected_scope` 是本次导出范围，`parent_scope` 保留父批次全部执行身份。`not_exported` 与 `unavailable_executions` 区分未选择和未封存条目。选中题目的 `task-inputs/` 同时保留题目定义、发送 Prompt、依赖和私有评分材料。

`purpose=scoring` 会为可评分执行生成单题标准输入。导入回执的 `scoring_contexts` 提供本机 context 和冻结 Skill 路径，其余路径相对 context_root。`local_reports` 为每个成功题提供 General 标准 batch-root 或 Web 报告 YAML。先对独立单题评分，再使用相应 run/report Skill 收口回传和报告。按父范围检查多配置、多 run 和失败题覆盖，General 多来源汇总沿用 report-general-e2e 的显式逐题来源选择。

产物清单的 `source` 说明来源。`final_response` 来自绑定原生完成轨迹。`completeness=present` 表示当前文件可读取，其 SHA 供传输对账，执行完整性和备份校验以快照、原始 seal 及 backup receipt 为依据。失败原生轨迹明确标为 partial 或 missing。原始包导入会重新验证整包成员集合、成员摘要及 capsule 绑定。

取消沿原身份停止派发，采集并封存已派发任务后释放沙箱。采集或进程清理尚未核验时保留 NEEDS_ATTENTION。Windows 清理回执在进程变更前落盘，恢复复用已观察的 PID、创建时间和路径，补充收口已记录的工作区服务。观察中断与取消分别记录，`resume` 接续原远端 job。

执行器发行使用只读版本目录部署。批次保存 root、Python、Git revision、api_version 和冻结参数。该路径在批次生命周期内需保留原发行，平台默认发行的更新仅影响新批次。

支持 `windows-astudio-runtime-bootstrap` 的发行可在 AgentCube 身份 JSON 中显式配置 `astudio_runtime`：`version`、HTTPS `download_url`、`size`、`sha512` 固定官方 Windows 安装包；可选 `session_file` 指向本机 0600 的原生 AStudio 登录快照，`sync_clock` 默认 true。登录快照必须来自用户授权的账号，不包含在输入包、日志或结果导出中。AgentCube Token 仍只从环境注入，两类凭据不能混用。

该准备步骤在题目派发前运行，校验安装包大小及 SHA-512、核验 app.asar 版本，并在候选 Workspace 之外保留受保护的旧状态备份。它按明确运行配置准备克隆沙箱，不改共享模板或既有冻结发行。Windows 时钟与控制器 UTC 偏差超过 120 秒时先校正，原有轨迹不改写。安装和登录恢复意图、配置指纹及状态回执可恢复；启动回执不明时只观察原状态文件，不重复启动安装。恢复时拒绝替换已有运行配置或登录快照。

恢复登录后先启动客户端，等待当前账号范围内的新模型目录包含请求模型，才允许进入控制器选择/派发阶段，避免冷启动的 Auto 回退目录被误当成最终能力。准备阶段还把 `C:\tmp_workspace` 作为执行目录的 Junction，以保留原题 `/tmp_workspace` 语义；如果该路径已有非目标目录或链接则拒绝覆盖。

新版 AStudio 的长粘贴可能在原生 user_message 中保存为单个 `<pasted_text>` JSON 块。绑定仅允许一个仅含 `text` 字段的条目，解码正文必须完整匹配冻结 PROMPT；额外正文、多附件或未知字段均拒绝。原始消息不改写，绑定证据同时记录传输类型及原文、解码正文 SHA-256。恢复继续复用原 session 和 task-run job，不重复发送题目。

历史批次的冻结采集器不识别新原生格式时，`export --purpose scoring --verification-skill-dir <新版collect-general-e2e目录>` 可显式补充独立采集校验器。包内保存其完整副本和 inventory 摘要，原批次、数据集、评分 Skill 与题目绑定不变；已有评分交接绑定拒绝冲突覆盖。该选项只准备可供离线评分的材料，不启动评分。

新批次默认使用 `winarena-pc-20261118-a`。模板和内置模型候选可由能力文件发布，运行时以部署的控制器、客户端和原生回读为准。

WorkBuddy 新批次默认开启完全访问，执行单元冻结 `workbuddy_full_access: true`。执行器通过 WGUI `product_config.ui.permission` 传递 `full access`。当前模板的 WorkBuddy 驱动也会在发送题目前通过原生流程切换并确认完全访问。API 和 CLI 显式请求默认权限时，执行器要求驱动支持该权限参数。

scoring-purpose 导出另提供 parent_reports，按 run 保存完整父 General 范围的 report-only manifest 与 report-config，保留原输入制品锁。接收方将独立单题标准回传导入为显式来源后，可直接将其 path 交给 selected_report.py 的 --batch-root，按 expected_execution_keys 检查全范围。coverage_status 区分完整与部分材料，单题快速评分仍使用 scoring_contexts。包索引记录 exporter_revision，执行发行仍由 parent-batch 的原快照保存。新版只读导出器可在协议 v1 下整理旧批次的封存原件。

## 环境预处理

`describe` 发布 `windows-environment-preprocessing` 能力。配置单元可提供 `preprocessing`，其中 `default` 为冻结方案或 null，`overrides` 按用例 ID 覆盖，同样允许 null 表示不应用该方案的环境修改及 Prompt 引用。方案包含 `version_id`、`version`、`name` 和有序 `steps`。环境修改步骤指定 `kind`、`timeout`、附件摘要 `asset`，以及该动作的专用字段。

发布 `preprocess-prompt-plugin-step-v1` 的执行器另外支持 AStudio 方案中的
`{"kind":"prompt_plugin","plugin_mentions":["sites-skills"]}`。每个方案最多一个此类
步骤，可以只有此步骤；无需附件或自定义超时。它固定在环境修改步骤之后，工作区
投递完毕、派题之前，沿用既有插件检查器验证安装、启用状态、版本、来源和文件摘要。
失败即停止派发，步骤回执与插件核验详情归档；成功后沿用生效 Prompt 的摘要与恢复
绑定，执行后继续核对插件漂移。沙箱生命周期预算包含前后核验与检查器投递时间。

插件名属于方案版本，按单元默认与逐题方案覆盖生效；默认不选方案时原 Prompt 字节
保持不变。旧的 `prompt_directives` 仍可读取和执行，新方案步骤与非空旧执行级引用
不能同时使用，防止两套引用规则互相覆盖。新增步骤不改变原冻结批次和既有四种动作。

`inspect-preprocess-asset --kind ... --name ... --file ...` 校验上传件并返回类型、大小、SHA-256、可选 Skill 名称或插件/内核版本。预检返回 `preprocessing_sha256` 和按单元展开的生效范围。创建预处理批次时，`run` 接收 `--expected-preprocessing-sha256` 和按 SHA-256 命名的 `--preprocess-asset-dir`。执行器验证并冻结为私有控制文件，续接沿用同一版本。公开回执包含版本号、步骤结果与摘要。

每个 `asset` 固定 `kind`、`name`、`size` 和 `sha256`。`skill` 指定 `target` 和 `source`，来源为 `auto`、`user`、`astudio` 或 `runtime`。`plugin` 指定已安装插件的 `target` 和本地或远程 `marketplace`。`acode` 从 ZIP 中读取内核及配套清单。`powershell` 可在 `attachments` 中绑定 `kind=file` 的附件，并通过 `$env:WCB_PREPROCESS_ATTACHMENTS` 读取。预检为每步预留最多 300 秒的投递预算及运行预算。

远程市场插件通过已安装的缓存身份绑定目标。试验包替换本次沙箱内原缓存目录的内容，保留远程身份记录和原缓存目录版本。回执分别标明试验包版本与远程缓存版本。独立验证记录缓存摘要及可取得的运行时回读。正式执行在发题前和任务返回后检查缓存身份、目录及摘要，发生变化时拒绝发布该次执行就绪回执。

投递先压缩并切块，每次 WGUI 工作区上传最多 32 MiB，以兼容单次 64 MiB 限制。Windows 端核验完整包和成员摘要后才执行。回执在同一个 Windows 会话中回读，文件未发布时继续等待，发布后核对本次步骤身份。

支持 `windows-preprocess-validation` 的执行器可用 `validate-preprocess --request REQUEST --workspace-root DIRECTORY` 在临时沙箱独立执行已冻结的方案。请求包含 `profile_id`、`model` 和 `recipe`，附件放在验证目录的 `preprocess-assets/<sha256>`。结果持续写入 `validation.json`，包含阶段、逐步结果、失败码与资源释放确认。该流程使用正常的 AgentCube 身份与模板配置，只执行预处理。PowerShell 使用非零退出码或未处理异常报告失败，返回结构化错误类别、错误标识及可定位的行号。需要验证具体副作用时可编写断言，也可用 `Write-Error -ErrorId PREPROCESS_ASSERTION_FAILED` 标明失败原因。
