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
  },
  required: ['task_id', 'result_analysis', 'root_cause_analysis'],
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
   - 若执行层错误表明任务根本没跑起来（如 workspace 缺失、API 额度耗尽、认证 401、request_count=0），直接定性为**环境/基础设施问题，非模型能力问题**，并在根因中明确标注；
   - 若是超时（timed_out=true），必须进一步读 transcript 区分：是"环境慢/没机会跑完"还是"模型陷入循环不收敛"。

3. **读执行全过程找证据**：Read ${t.transcript || '（transcript 缺失）'}
   - JSONL 格式，每行一个事件：message.content[] 含 type=text（模型输出）、type=tool_use（实际执行的操作，name 如 exec_command，input 里是命令/代码）、type=tool_result（工具返回）。
   - 文件约 ${t.transcript_kb} KB，超过 100KB 请用 Read 的 offset/limit 分页读完关键部分，禁止只读开头就下结论。
   - 带着第 1 步弄清的**每一个失分检查点**去找证据：模型是否做了对应操作？做错在哪一步？产物是否落盘到判分代码检查的路径？
   - 常见失分信号：工具调用协议不兼容（tool_result 里大量 unsupported call 报错）、只读不写、产物写错路径、代码反复报同一个错、伪造结果文本但无对应 tool_use、过早结束。
   - 对代码类失败，必须**提取失败的具体代码/命令片段**，分析到具体逻辑错误（如键名错、路径错、格式串错），不许止步于"报错了"。
   ${t.agent_log ? `- 补充证据可读 agent.log：${t.agent_log}` : ''}

4. **输出**（中文，结构化）：
   - result_analysis：任务概述（1-2句）→ 执行过程还原（模型实际做了什么）→ 逐失分检查点分析（要求什么 / transcript 证据（含关键片段或行号）/ 为何扣分）。
   - root_cause_analysis：1-2 句话总结根本原因，落到以下类别之一或组合，并注明主导归属层（L1a 底层推理 / L1b 长程执行 / L3 环境基础设施 / L4 评测系统）：
     工具调用协议不兼容 / 超时或循环不收敛 / API额度或认证故障 / 视觉通道失效 / 产物未落盘或路径错误 / 代码错误 / 幻觉或编造 / 任务理解偏离 / 判分脚本刚性或评测系统问题 / 能力短板。
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