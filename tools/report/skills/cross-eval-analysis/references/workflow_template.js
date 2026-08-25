export const meta = {
  name: 'wildclaw-cross-eval-analysis',
  description: 'WildClawBench 固定模型或固定 Harness 的逐用例证据对比分析',
  phases: [
    { title: 'Analyze', detail: '按控制变量逐用例核对两侧结果与轨迹' },
  ],
}

let input = args
if (typeof input === 'string') {
  try { input = JSON.parse(input) } catch (error) { throw new Error('args 不是合法 JSON: ' + error.message) }
}
const manifest = input?.manifest
if (!manifest || manifest.kind !== 'cross_eval_manifest') {
  throw new Error('args.manifest 必须是 build_cross_eval_manifest.py 生成的 manifest 对象')
}

const schema = {
  type: 'object',
  properties: {
    schema_version: { type: 'number' },
    executive_summary: { type: 'string' },
    pair_reports: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          target_unit: { type: 'string' },
          reference_unit: { type: 'string' },
          summary: { type: 'string' },
          strengths: { type: 'array', items: { type: 'object' } },
          weaknesses: { type: 'array', items: { type: 'object' } },
          typical_cases: { type: 'array', items: { type: 'object' } },
        },
        required: ['target_unit', 'reference_unit', 'summary', 'strengths', 'weaknesses', 'typical_cases'],
        additionalProperties: false,
      },
    },
    comparability_analysis: {
      type: 'object',
      properties: {
        summary: { type: 'string' },
        scope_note: { type: 'string' },
        impact_rows: { type: 'array', items: { type: 'object' } },
      },
      required: ['summary', 'scope_note', 'impact_rows'],
      additionalProperties: false,
    },
    unconfirmed_items: { type: 'array', items: { type: 'object' } },
  },
  required: ['schema_version', 'executive_summary', 'pair_reports', 'comparability_analysis', 'unconfirmed_items'],
  additionalProperties: false,
}

const units = manifest.units || []
const taskIndex = Object.fromEntries((manifest.comparisons || []).map(item => [item.task_id, item]))
const axisText = manifest.axis === 'model'
  ? `固定 Harness：${manifest.fixed?.harness || ''}，比较模型`
  : `固定模型：${manifest.fixed?.model || ''}，比较 Harness`

const prompt = `你是 WildClawBench 跨单元评测分析人员。${axisText}

请基于下方 manifest，逐个配对目标单元与每个参照单元。先读每个任务定义和两侧 score.json、execution_status.json，再读两侧完整 transcript；如果某侧存在 agent_interaction.jsonl，必须核对模型请求体/响应体中的工具清单、tool call 和协议错误。

## 硬性要求
1. 只分析 manifest.scope.task_ids 中的完整任务 ID；不把共同无效任务写成 0 分，不扩展到 manifest 外。
2. 先比较同一任务两侧实际检查点和行为，再总结模型/Harness 差异。平均分只作背景，不能单独证明根因。
3. 每个 strengths/weaknesses 项必须有完整 task_id、与 manifest 一致的 task_name、mechanism、delta_pct_points 和 evidence_refs；每个 evidence_ref 必须写 source、locator、excerpt。
4. 每个典型案例必须写完整 task_id、task_name、what_tested（题目简述/考察点）、score_summary、problem、evidence_summary、confidence 和 evidence_refs。优先选约 3 个机制不同且证据充分的案例；样本不足时说明原因，不要凑数。
5. 文风务实、克制，不写“模型不行”“Harness 很差”等评价。写“差异集中在……”“两侧均完成……”“目标侧在……环节未闭环”。
6. L3/L4 只能作为可比性和未闭环因素说明，不能直接写成模型或 Harness 能力短板。任务超时仅在 manifest 已标记 \`valid_capability_outcome\` 时作为能力结果分析；unsupported call 不能单独判定 Harness 问题，缺少工具清单或调度证据时使用 unconfirmed。
7. 不编造行号。只能引用实际读到的文件、JSON 字段、行号、命令或产物路径；如果证据不足，放入 unconfirmed_items。
8. 正文只简要提及异常和不可比结果。详细内容写入 comparability_analysis 与 unconfirmed_items：逐步给出排除后的样本数、两侧均分、分差，并为每个排除项补齐完整 task_id、task_name、得分、判定依据、处理结论和 evidence_refs。没有排除项时返回空 impact_rows 和空 unconfirmed_items，并在 summary 说明未发现影响可比性的异常。

## manifest
${JSON.stringify(manifest, null, 2)}

## 参评单元
${JSON.stringify(units, null, 2)}

## 任务索引
${JSON.stringify(taskIndex, null, 2)}

返回符合 schema 的 JSON。executive_summary 只写 2-4 句；每个 pair summary 只写 2-3 句，先写接近/共同项，再写差异集中项。异常审计细节由渲染器统一放到报告附录。`

const result = await agent(prompt, { label: 'cross-eval-analysis', phase: 'Analyze', schema })
if (!result) throw new Error('跨单元分析未返回结果')
return result
