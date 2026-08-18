export const meta = {
  name: 'wildclaw-low-score-analysis-r5-flash',
  description: 'round5 xsparkx2flash@astroncode 低分根因分析（批次文件由子代理加载）',
  phases: [
    { title: 'Load', detail: '子代理读取批次JSON' },
    { title: 'Analyze', detail: '每任务一个子代理，批内并发' },
  ],
}

let input = args
if (typeof input === 'string') input = JSON.parse(input)
const unit = input.unit
const files = input.batch_files || []
if (!files.length) throw new Error('batch_files 为空')

const LOAD_SCHEMA = {
  type: 'object',
  properties: { tasks: { type: 'array', items: { type: 'object' } } },
  required: ['tasks'],
  additionalProperties: false,
}

const SCHEMA = {
  type: 'object',
  properties: {
    task_id: { type: 'string' },
    result_analysis: { type: 'string', description: '结果分析（中文，600-1200字）：任务概述、执行过程还原、逐失分检查点的证据与原因' },
    root_cause_analysis: { type: 'string', description: '根因总结（中文，1-2句话，80-150字），落到常见根因类别' },
    checkpoint_analysis: {
      type: 'array',
      description: '逐个数值检查点的结构化结论和证据引用；必须覆盖 score.json 中所有检查点，不能只列失分项',
      items: {
        type: 'object',
        properties: {
          checkpoint: { type: 'string' },
          score: { type: 'number' },
          conclusion: { type: 'string' },
          evidence_refs: {
            type: 'array', minItems: 1,
            items: {
              type: 'object',
              properties: {
                source: { type: 'string' }, locator: { type: 'string' }, excerpt: { type: 'string' },
              },
              required: ['source', 'locator'], additionalProperties: false,
            },
          },
        },
        required: ['checkpoint', 'score', 'conclusion', 'evidence_refs'],
        additionalProperties: false,
      },
    },
    attribution_layer: {
      type: 'string',
      enum: ['L1a', 'L1b', 'L2', 'L3', 'L4', 'uncertain', 'none'],
      description: '正式五层中的主导归属层：L1a/L1b/L2/L3/L4；uncertain 是待确认状态，不是第六层；证据不足无法区分时使用 uncertain；模型调用请求体/响应体中未提供的工具使用 L1b，只有 Harness 违反已声明工具契约才使用 L2',
    },
    attribution_confidence: {
      type: 'string',
      enum: ['confirmed', 'probable', 'unconfirmed', 'none'],
      description: '归因置信度；confirmed 需直接证据充分并排除主要替代解释，probable 允许一个未闭环因素，unconfirmed 表示关键证据缺失',
    },
    attribution_evidence: {
      type: 'string',
      description: '归因证据；必须写明来源、关键事实、支持该层的理由；confirmed 还要排除主要替代解释；证据不足时写明缺失材料及无法区分模型与Harness',
    },
  },
  required: ['task_id', 'result_analysis', 'root_cause_analysis', 'checkpoint_analysis', 'attribution_layer', 'attribution_confidence', 'attribution_evidence'],
  additionalProperties: false,
}

function buildPrompt(t) {
  const failed = Object.entries(t.failed_checkpoints || {}).map(([k, v]) => `  - ${k} = ${v}`).join('\n') || '  （无失分检查点记录）'
  const scoreDesc = (t.score_pct === null || t.score_pct === undefined) ? '无有效得分（score.json 缺失或判分失败）' : `${t.score_pct} 分（百分制）`
  return `你是评测失分根因分析专家。请分析 WildClawBench 任务 ${t.task_id}（单元 ${unit}）的失分根因。

## 已知信息（来自评测结果）
- 套件：${t.suite}
- 总得分：${scoreDesc}
- 失分检查点（<1.0 的判分项）：
${failed}
- 执行层错误（execution_status.error）：${t.error_execution || '无'}
- 判分层错误（score.json.error）：${t.error_grading || '无'}
- 是否超时：${t.timed_out ? '是' : '否'}（状态：${t.status || '未知'}）
- 资源用量：请求 ${t.usage?.request_count ?? '?'} 次 / ${t.usage?.total_tokens ?? '?'} tokens / 耗时 ${t.usage?.elapsed_time ?? '?'} 秒

## 分析步骤（务必按序执行，用证据说话，不臆测）

1. **读任务定义**：Read ${t.task_file || '（task_file 缺失，请从 task_id 推断任务目标）'}
   该 .md 文件包含任务 Prompt 与**判分代码**（automated checks）。判分代码是"判决书"——每个失分检查点对应代码里一个具体检查，先弄清每个失分点到底检查什么（文件路径、内容格式、阈值）。

2. **判断错误层级（优先）**：
   - 若外部大模型服务调不通、服务认证失败、流控/限流、网络不通或模型专属视觉服务返回 401，定性为 **L3 评测环境与推理服务基础设施问题，非模型能力问题**，并在根因中明确标注；
   - 若评测 Runner、容器生命周期、框架创建/挂载 Workspace、框架异常终止进程、任务定义或 Grader 导致任务无法执行/得分失真，定性为 **L4 评测系统问题，非模型能力问题**，并在根因中明确标注；Runner 创建 Workspace 失败不能直接归 L3；
   - 若 Harness 自身会话、工具调度、超时截断或产物回收异常，定性为 **L2 Harness 问题**；只有契约和 Harness 日志都能证明时才这样归因；
   - 若模型在请求体/响应体的可用工具清单中看不到 bash、read 等工具，却主动调用这些工具，定性为 **L1b 模型 Agent 能力问题**；Harness 是否增加拒绝、替代工具或其他兜底，只能作为改进方向；
   - 只有工具已在模型可见清单或 Harness 明确契约中，但 Harness 没有正确注册、映射、调度、回传，或会话状态/重试/超时控制异常，才定性为 **L2 Harness 问题**；必须有契约与调度证据；
   - 若只有 unsupported call 而缺少工具清单、Harness 契约或调度日志，填写 uncertain，明确缺失材料；uncertain 是待确认状态，不是第六层，也不参与五层统计；
   - 若是超时（timed_out=true），必须区分：统一任务 deadline 到期且模型持续循环、反复报错或没有完成交付，归 **L1b**；Harness 在 deadline 前错误截断归 **L2**；Runner/容器在 deadline 前异常终止或 timeout 配置错误归 **L4**；外部模型服务/网络没有给模型执行机会归 **L3**。不能因为最终由 Runner/容器结束进程，就把正常任务超时归为 L3 或 L4。

3. **读执行全过程找证据**：Read ${t.transcript || '（transcript 缺失）'}
   - JSONL 格式，每行一个事件：message.content[] 含 type=text（模型输出）、type=tool_use（实际执行的操作，name 如 exec_command，input 里是命令/代码）、type=tool_result（工具返回）。
   - 文件约 ${t.transcript_kb} KB，超过 100KB 请用 Read 的 offset/limit 分页读完关键部分，禁止只读开头就下结论。
   ${t.agent_interaction ? `- AstronCode 原始 Harness↔模型交互轨迹：Read ${t.agent_interaction}（约 ${t.agent_interaction_kb} KB）。重点查找模型请求体中的 tools 清单、响应体中的 tool call 和 unsupported call；它用于协议层核对，不能替代 transcript 对实际执行和交付结果的核对。` : '- 若这是 AstronCode 但 agent_interaction.jsonl 缺失，明确记录“缺少模型请求/响应轨迹”，不要仅凭 unsupported call 判断是模型还是 Harness。'}
   - 带着第 1 步弄清的**每一个失分检查点**去找证据：模型是否做了对应操作？做错在哪一步？产物是否落盘到判分代码检查的路径？
   - 常见失分信号：工具调用协议不兼容（tool_result 里大量 unsupported call 报错）、只读不写、产物写错路径、代码反复报同一个错、伪造结果文本但无对应 tool_use、过早结束。
   - 对代码类失败，必须**提取失败的具体代码/命令片段**，分析到具体逻辑错误（如键名错、路径错、格式串错），不许止步于"报错了"。
   ${t.agent_log ? `- 补充证据可读 agent.log：${t.agent_log}` : ''}

4. **输出**（中文，结构化）：
   - result_analysis：任务概述（1-2句）→ 执行过程还原（模型实际做了什么）→ 逐失分检查点分析（要求什么 / transcript 证据（含关键片段或行号）/ 为何扣分）。
   - checkpoint_analysis：逐个列出 score.json 中所有数值检查点，不得只列失分项；保留原始名称、实际分数、扣分结论和至少一个带 source/locator 的 evidence_ref，禁止编造定位。
   - root_cause_analysis：1-2 句话总结根本原因，落到以下类别之一或组合，并注明主导归属层（L1a 模型基础推理能力 / L1b 模型 Agent 能力 / L2 Harness 运行与工具编排 / L3 评测环境与推理服务基础设施 / L4 评测系统、任务与 Grader）：
     模型调用请求体/响应体中未提供的工具归 L1b；只有工具已在模型可见清单或 Harness 明确契约中，但 Harness 没有正确注册、映射、调度、回传，或会话状态/重试/超时控制异常，才归 L2。unsupported call 不能单独证明工具未暴露；必须核对工具清单和 Harness 调度日志。Harness 兜底属于改进建议，不改变模型根因；证据不足时标记 uncertain/unconfirmed，并明确缺少什么证据、无法区分模型与 Harness；
     工具调用协议不兼容 / 超时或循环不收敛 / API额度或认证故障 / 视觉通道失效 / 产物未落盘或路径错误 / 代码错误 / 幻觉或编造 / 任务理解偏离 / 判分脚本刚性或评测系统问题 / 能力短板。
   - attribution_layer：填写主导层 L1a/L1b/L2/L3/L4；无法区分模型与 Harness 时填写 uncertain。uncertain 是待确认状态，不是第六层，也不参与五层统计；无失分成功对照填写 none。
   - attribution_confidence：直接证据充分且排除主要替代解释填写 confirmed；允许一个未闭环因素但现有证据支持当前判断填写 probable；关键证据缺失、无法可靠归因填写 unconfirmed；成功对照填写 none。
   - attribution_evidence：必须写明证据来源、关键事实和归因理由；AstronCode 优先引用 agent_interaction.jsonl 核对工具清单和请求/响应，chat_openclaw.jsonl 用于核对实际执行。confirmed 还要说明主要替代解释为何不成立；证据不足时明确写“缺少……证据，无法区分具体是模型问题还是 Harness 问题”。
   - 环境/基础设施问题必须标注「非模型能力问题」；得分 > 85 的任务标注「本质高分，非能力短板」。

返回 JSON（task_id 填 "${t.task_id}"）。`
}

const all = []
for (let b = 0; b < files.length; b++) {
  log(`批次 ${b + 1}/${files.length}: 加载 ${files[b]}`)
  const loaded = await agent(
    `用 Read 工具读取文件 ${files[b]}。它是一个 JSON 数组，元素是任务对象。把数组内容**原样、完整、不增删改任何字段**地作为 tasks 返回。若文件很长，务必读完整个文件再返回。`,
    { label: `load:batch${b}`, phase: 'Load', schema: LOAD_SCHEMA, effort: 'low' }
  )
  const tasks = ((loaded && loaded.tasks) || []).filter(t => t && t.task_id)
  log(`批次 ${b + 1}: 加载到 ${tasks.length} 个任务`)
  if (!tasks.length) continue
  const results = await parallel(tasks.map(t => () =>
    agent(buildPrompt(t), { label: `analyze:${t.task_id}`, phase: 'Analyze', schema: SCHEMA })
  ))
  const ok = results.filter(Boolean)
  log(`批次 ${b + 1} 完成：成功 ${ok.length}/${tasks.length}`)
  all.push(...ok)
}
log(`全部完成：${all.length}`)
return all
