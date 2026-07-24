export const meta = {
  name: 'wildclaw-eval-case-analysis',
  description: 'WildClawBench 评测用例分析：失分根因分析与满分成功对照分析',
  phases: [
    { title: 'Analyze', detail: '每任务一个子代理，批内并发' },
  ],
}

// ---------------------------------------------------------------------------
// args 归一化（可能被序列化为 JSON 字符串传入）
// ---------------------------------------------------------------------------
let input = args
if (typeof input === 'string') {
  try { input = JSON.parse(input) } catch (e) { throw new Error('args 不是合法 JSON: ' + e.message) }
}
const unit = input.unit || `${input.model || 'unknown'}@${input.harness || 'unknown'}`
const tasks = Array.isArray(input.tasks) ? input.tasks : []
const batchSize = input.batch_size || 10
const completed = new Set(input.completed_task_ids || [])

if (!tasks.length) throw new Error('args.tasks 为空：请传入精简后的任务列表（见 utils.simplify_task）')

const todo = tasks.filter(t => t && t.task_id && !completed.has(t.task_id))
log(`单元 ${unit}：共 ${tasks.length} 个任务，跳过已完成 ${tasks.length - todo.length} 个，待分析 ${todo.length} 个`)

// ---------------------------------------------------------------------------
// 子代理输出 schema
// ---------------------------------------------------------------------------
const SCHEMA = {
  type: 'object',
  properties: {
    task_id: { type: 'string' },
    analysis_type: {
      type: 'string',
      enum: ['failure', 'unscored', 'success_control'],
      description: '失分、无有效得分或满分成功对照',
    },
    result_analysis: {
      type: 'string',
      description: '结果分析（中文，600-1200字）：执行过程还原及检查点证据；满分任务说明成功路径',
    },
    root_cause_analysis: {
      type: 'string',
      description: '失分根因总结；满分任务明确写明无失分根因并总结成功关键',
    },
  },
  required: ['task_id', 'analysis_type', 'result_analysis', 'root_cause_analysis'],
  additionalProperties: false,
}

// ---------------------------------------------------------------------------
// 分析 prompt
// ---------------------------------------------------------------------------
function buildPrompt(t) {
  const analysisType = t.analysis_type || 'failure'
  const isControl = analysisType === 'success_control'
  const failed = Object.entries(t.failed_checkpoints || {})
    .map(([k, v]) => `  - ${k} = ${v}`)
    .join('\n') || '  （无失分检查点记录）'
  const scoreDesc = (t.score_pct === null || t.score_pct === undefined)
    ? '无有效得分（score.json 缺失或判分失败）'
    : `${t.score_pct} 分（百分制）`

  const objective = isControl
    ? '该任务为满分成功对照。请还原成功路径，分析哪些操作和验证使全部评分要求得到满足；禁止编造失分或能力问题。'
    : '请分析该任务的失分根因；若无有效得分，优先分析执行或判分异常。'

  return `你是评测用例分析专家。请分析 WildClawBench 任务 ${t.task_id}（单元 ${unit}）。${objective}

## 已知信息（来自评测结果）
- 套件：${t.suite}
- 总得分：${scoreDesc}
- 分析类型：${analysisType}
- 失分检查点（<1.0 的判分项）：
${failed}
- 执行层错误（execution_status.error）：${t.error_execution || '无'}
- 判分层错误（score.json.error）：${t.error_grading || '无'}
- 是否超时：${t.timed_out ? '是' : '否'}（状态：${t.status || '未知'}）
- 资源用量：请求 ${t.usage?.request_count ?? '?'} 次 / ${t.usage?.total_tokens ?? '?'} tokens / 耗时 ${t.usage?.elapsed_time ?? '?'} 秒

## 分析步骤（务必按序执行，用证据说话，不臆测）

1. **读任务定义**：Read ${t.task_file || '（task_file 缺失，请从 task_id 推断任务目标）'}
   该 .md 文件包含任务 Prompt 与**判分代码**（automated checks）。先弄清每个检查点具体检查什么（文件路径、内容格式、阈值）。失分任务逐项定位扣分要求；满分对照逐项确认成功证据。

2. **判断错误层级（优先）**：
   - 若执行层错误表明任务根本没跑起来（如 workspace 缺失、API 额度耗尽、认证 401、request_count=0），直接定性为**环境/基础设施问题，非模型能力问题**，并在根因中明确标注；
   - 若是超时（timed_out=true），必须进一步读 transcript 区分：是"环境慢/没机会跑完"还是"模型陷入循环不收敛"。

3. **读执行全过程找证据**：Read ${t.transcript || '（transcript 缺失）'}
   - JSONL 格式，每行一个事件：message.content[] 含 type=text（模型输出）、type=tool_use（实际执行的操作，name 如 exec_command，input 里是命令/代码）、type=tool_result（工具返回）。
   - 文件约 ${t.transcript_kb} KB，超过 100KB 请用 Read 的 offset/limit 分页读完关键部分，禁止只读开头就下结论。
   - ${isControl ? '逐个检查点找成功证据：模型做了哪些关键操作、如何验证、产物为何满足判分代码；同时记录可复用的高质量执行行为。' : '带着第 1 步弄清的每一个失分检查点去找证据：模型是否做了对应操作？做错在哪一步？产物是否落盘到判分代码检查的路径？'}
   - 常见失分信号：工具调用协议不兼容（tool_result 里大量 unsupported call 报错）、只读不写、产物写错路径、代码反复报同一个错、伪造结果文本但无对应 tool_use、过早结束。
   - 对代码类失败，必须**提取失败的具体代码/命令片段**，分析到具体逻辑错误（如键名错、路径错、格式串错），不许止步于"报错了"。
   ${t.agent_log ? `- 补充证据可读 agent.log：${t.agent_log}` : ''}

4. **输出**（中文，结构化）：
   - result_analysis：任务概述（1-2句）→ 执行过程还原（模型实际做了什么）→ ${isControl ? '逐检查点说明要求、transcript 成功证据（含关键片段或行号）及有效做法。' : '逐失分检查点分析要求、transcript 证据（含关键片段或行号）及扣分原因。'}
   - root_cause_analysis：${isControl ? '写成“满分对照，无失分根因；成功关键在于……”，用 1-2 句话总结最关键的正确行为，不标能力问题归属层。' : '用 1-2 句话总结根本原因，落到以下类别之一或组合，并注明主导归属层（L1a 底层推理 / L1b 长程执行 / L3 环境基础设施 / L4 评测系统）：工具调用协议不兼容 / 超时或循环不收敛 / API额度或认证故障 / 视觉通道失效 / 产物未落盘或路径错误 / 代码错误 / 幻觉或编造 / 任务理解偏离 / 判分脚本刚性或评测系统问题 / 能力短板。'}
   - 环境/基础设施问题必须标注「非模型能力问题」；得分 > 85 的任务标注「本质高分，非能力短板」。

返回 JSON（task_id 填 "${t.task_id}"，analysis_type 填 "${analysisType}"）。`
}

// ---------------------------------------------------------------------------
// 批内并发执行
// ---------------------------------------------------------------------------
const batches = []
for (let i = 0; i < todo.length; i += batchSize) batches.push(todo.slice(i, i + batchSize))

const all = []
for (let b = 0; b < batches.length; b++) {
  log(`批次 ${b + 1}/${batches.length}（${batches[b].length} 个任务）`)
  const results = await parallel(batches[b].map(t => () =>
    agent(buildPrompt(t), { label: `analyze:${t.task_id}`, phase: 'Analyze', schema: SCHEMA })
  ))
  const ok = results.filter(Boolean)
  log(`批次 ${b + 1} 完成：成功 ${ok.length}/${batches[b].length}`)
  all.push(...ok)
}

log(`全部完成：${all.length}/${todo.length}`)
return all
