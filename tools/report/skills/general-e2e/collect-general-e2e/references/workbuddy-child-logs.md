# WorkBuddy原生子Agent SDK取证

原生父请求中的`Agent`工具可以把实际读表、计算、写入和核验交给独立子会话。父SDK及父工具返回不代表子会话实际执行了摘要中声称的操作。

collector在可信终态后，从精确父SDK旁的`<父session>/subagents/agent-*.jsonl`读取稳定原件。它要求父Runtime和SDK中的唯一调用匹配，子首条指令逐字等于原父调用参数；逐行核对root request、父baggage、子独立session/request、完整cwd和父执行时间范围。重复谱系、错参数、异会话、越界时间、未知用户发送、外来结果、符号链接和未准入的嵌套目录均拒绝。

`native-tool-execution-start/v1`通过原tool ID、request和模型响应ID绑定Runtime的`toolExecutionStartedAt`作为实际派发下界，并保存SDK调用记录时点。SDK写记录可以晚于实际派发，不能用写记录时间替代派发时间后再加任意容差。派发字段存在但非法/来源不符时拒绝；缺失时明确声明SDK时间来源。旧43证明没有此Profile，复验继续使用原SDK时点和原字段，不补写旧证明。

子SDK可穿插`session-meta`元数据，其sessionId是文件名中的`agent-<id>`别名，模型事件仍保持独立逻辑session。只接受精确的id/type/sessionId/timestamp/meta字段及已知`hostKind=unopted, agentRuntime=local-agent`形状，别名和时间范围必须匹配；元数据逐字保留并独立列明，不转换为用户或模型事件。其他额外字段、运行时、别名或消息形状拒绝。

部分已完成Runtime卡片只保留单字段description，值为原字符串或空对象占位。只对这两个精确形状，且原meta的description、工具名、子类型、isSubagent、request ID以及SDK模型响应ID全部匹配时，以SDK原始完整参数逐字核对子首条指令；分别保存`runtime-description-only-sdk-full-arguments/v1`或`runtime-empty-description-sdk-full-arguments/v1`来源说明，不填回或改写Runtime参数。其他缺参数形状不准入。

原子调用/返回和最终助手是否完整单独记入子来源证明；原生子执行留下的未返回调用或明确`incomplete`结果保持partial，不补造返回或成功。原始子文件逐字写入`raw/workbuddy-subagents/`，证明写入`bindings/workbuddy-linked-child-sdk.json`；父转录、父call ID、一次发送记录、执行起止、人工介入和候选均不改。finalize与verify-only从正式归档原件重新计算谱系与证明。

原生`<agent-id>/tool-results/call_<id>.txt`及对应`-render.txt`输出文件一并独立封存。只接受同一子SDK中真实存在的call ID和明确的目录布局，记录此绑定依据；不把render文本冒充原始结果，也不从同名文件推断工具执行成功。其他目录、嵌套子Agent或未知文件形式继续拒绝。

原生MCP还会生成`mcp-<tool>-<epoch>-<suffix>.txt`。此文件名不冒充模型call ID；只有同一子SDK的真实MCP工具返回明确包含原绝对路径，且工具名和文件前缀一致时，才保存路径与全部来源event/call ID。复验只比较归档原件里的路径字符串，不访问原绝对路径；不按文件时间或名称近似猜配。

评分交接沿标准raw_trace和binding_evidence引用闭包复制全部子原件。需要判定实际工具操作或验收覆盖时，裁判应读取相应子日志，不能仅凭父Agent摘要推断完成。

当前资源Profile仍统计绑定的主会话响应，明确保留`CHILD_AGENT_USAGE_NOT_INCLUDED`。独立封存不代表子用量已通过计数准入；全链路Token/响应/工具总数保持未知，报告必须说明主会话口径和子日志覆盖，不把主指标当作整个Agent树总量。此版本不改变已冻结资源算法或既有成绩。

已经生成的旧collector输出不覆盖。修复收集使用同一可信终态的新输出目录，保留旧输入、源发行和SHA，在正式收口前明确选择新来源；已经正式发布的证据仍须通过独立补采协议，不能原地追加文件。

采集状态是独立的派生副本：原Native绑定引用保持，另加入本次证明的unit-relative路径/大小/SHA，并以`collector_derived_bindings`显式注明来源阶段。原执行状态不改写。状态与trace-index中的完整binding摘要集合必须相同，通用collection验证不放宽；资源来源中的状态摘要在新增证明后重新绑定。
