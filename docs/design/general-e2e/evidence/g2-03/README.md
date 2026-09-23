# G2-03 AstronStudio 轨迹归档、标准化与检索证据

> 证据边界：本文只记录所列日期、批次和 revision 的事实，保留原失败与未知项。当前集成进度和下一步统一见[集成契约](../../../e2e/端到端自动化评测Harness接入契约.md#integration-progress)，不从本文旧“当前/下一步”推导最新支持状态。

## 结论

2026-09-18 在已完成的 AStudio 3.3.1 / GLM-5.2 / High / 完全访问真机 attempt 上，使用 `collect-general-e2e` `0.2.0` 的轨迹子能力完成只读归档：

- S1 精确归档 148 个原生 turn 事件，转换为 24 个标准事件，包含 5 组不重复的 call/result；
- S4 精确归档 319 个原生 turn 事件，转换为 5 个标准事件，包含完整最终回复且无工具调用；
- 两个索引的 `completeness.status=complete`、`omitted_event_count=0`、`missing=[]`；
- 原生事件只按已冻结的 `thread_id + turn_id` 读取，再校验 provider session、lifecycle generation 和 cwd；未混入同库其他任务、评分会话或 `turn_id IS NULL` 的后台事件；
- General E2E 契约验证器能读取两份 index 和 transcript，现有 `transcript_loader` 能从 S1 读取 4 条 assistant 消息和 5 次工具调用，从 S4 读取唯一最终 assistant 回复。

这些证据只完成 G2-03。尚未生成 `resource-metrics-v1`、未冻结候选，也未生成正式执行回执；`collect-general-e2e` 整体因此仍为 `interface_only`。

## 真机范围与产物

| 样本 | task / attempt | 原生绑定 | 原生/标准/调用 | 产物 SHA-256 |
| --- | --- | --- | --- | --- |
| S1 | `02_Code_Intelligence_task_001_temperature_cli_fix` / `693c1c28-a78a-409b-82d7-b0dfcadb3132` | thread `1fc7cf29-ec97-41ab-8264-51d23cc86bc5`<br>turn `01a0afda-4a76-79a2-887a-09cc22592523`<br>session `01a0afda-3943-74b1-99a1-86fefb8e2f67` | 148 / 24 / 5 | raw `7181fd47a6811190a0c03854e5bf382b0d99cd2aa90e0962998911a5bd499cd0`<br>transcript `a829deabe469e9827497d7e13dc8df5d2f6c5d70d5bc6d541b0e17a64abf2ed7`<br>index `6c1df7aee6dbc225492f1c96c7748fe9f3e08ed31ca64de88004d74bebf6a20b` |
| S4 | `01_Productivity_Flow_task_003_retro_agenda` / `143cdcd2-6a04-4486-ac1c-f1564b725103` | thread `d34a6ebb-581e-452c-96bd-e9f0eb101744`<br>turn `01a0afe4-02dd-7562-8315-24dcb9cb765a`<br>session `01a0afe3-e980-7a91-a889-1d3801846d26` | 319 / 5 / 0 | raw `5a04620f463cb3f5c7491a31165a9b748aef1ef0887ef6ec5b6793dd8d20b709`<br>transcript `f5d958f9801e2a9bd8e37894f03c3c7488c65eb3a39f6bf8fe37aedc9d7193b2`<br>index `a57b5e534a47458885f58005f1971e028c76d148d5234692b7e8631da63d25e5` |

产物入口：

- [S1 trace index](s1/trace-index.json)、[S1 标准 transcript](s1/transcript.jsonl)、[S1 原始归档](s1/raw/astronstudio-provider-events.jsonl)；
- [S4 trace index](s4/trace-index.json)、[S4 标准 transcript](s4/transcript.jsonl)、[S4 原始归档](s4/raw/astronstudio-provider-events.jsonl)。

`filtered_native_event_count` 表示已保留在原始 JSONL、但有意不转换为高层标准事件的流式 delta、reasoning 摘要和重复 item update；不表示归档丢失。

## 工具调用和路径映射实证

S1 标准轨迹保留一次 `file_change` 和四次 `command`，每个 call ID 只有一个 `tool_call` 和一个后续 `tool_result`。例如：

- call `call_ltxjrhtyydau3njm77g3rcxm` 的调用位于 transcript sequence 16 / line 17，原始位置 `raw/...jsonl#L118`；
- 该调用保留真实命令 `python3 -m unittest discover -s project -p 'test_*.py' -v`，结果 sequence 17 保留 3 个测试通过的完整输出、`exit_code=0`和原生耗时；
- 文件修改 call `call_ejc5vlbeymeopijqtq32l5g8` 同时保留 converter.py 的本机绝对路径和 `/tmp_workspace/project/converter.py`，按规范路径查询命中 call/result 两个事件。

工具调用另提供 `message.role=assistant + content[].type=tool_use + name/input/arguments` 兼容视图。现有自建题的 `tool_audit` 读法在真实 S1 transcript 上读到的名称为 `file_change, command, command, command, command`，参数和 canonical `tool.arguments` 同源。

## 只读检索实证

对 S1 call ID 执行 `--page-size 1`，返回：

- `total_matches=2`、`total_pages=2`、`has_previous=false`、`has_next=true`；
- 第一条命中为 sequence 16 的 `tool_call`，定位到 transcript line 17 和 raw line 118。

对 `/tmp_workspace/project/converter.py` 执行路径查询，返回 `total_matches=2`，分别为文件修改 call 和 result。对 S4 执行文本查询可定位 user 任务和最终 assistant 回复；最终回复的原始引用为 `raw/...jsonl#L317`。

## 验证边界

- Node 轨迹专项 6/6 PASS：精确会话过滤、调用关联、规范路径、自动规则兼容、分页定位、不完整降级、session 污染拒绝和哈希篡改拒绝；
- General E2E 59/59、旧 `eval_e2e` 60/60、Web Python 112/112 PASS；General probe 8/8、execute 9/9、trace 6/6，Web AstronStudio 49/49、WorkBuddy 92/92、QwenWork 44/44、Codex Desktop 52/52、资源指标 20/20、截图接收 8/8 PASS；
- 13 个 Web/General Skill quick validate 和 General layout gate PASS；
- 两份真机 trace index 通过 `validate_contract_file`，两份 transcript 通过 `validate_transcript_jsonl`；
- 对同一原生库和执行状态使用 `--replace` 重新归档后，S1/S4 六个产物 SHA-256 全部不变；
- 常见凭据模式静态扫描无命中。原始事件未脱敏，因为该两题轨迹未发现真实凭据；`source.redacted=false` 与之一致。

MAC-03 仍为 `NOT_RUN`，因为它还要求 G2-04 的资源指标对账。
