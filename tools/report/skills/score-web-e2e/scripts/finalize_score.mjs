#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const SCHEMA_VERSION = "wildclawbench.web-e2e-task-score/v1";
const SKILL_VERSION = "2.0.0";
const EXECUTION_STATUSES = new Set(["completed", "execution_error", "timeout", "pending"]);
const EVALUATION_STATUSES = new Set(["completed", "evaluation_error"]);

function parseArgs(argv) {
  const result = {};
  for (let index = 0; index < argv.length; index += 2) {
    const key = argv[index];
    const value = argv[index + 1];
    if (!key?.startsWith("--") || value === undefined) throw new Error(`参数格式错误: ${key ?? ""}`);
    result[key.slice(2)] = value;
  }
  return result;
}

function loadJson(filename) {
  const value = JSON.parse(fs.readFileSync(filename, "utf8"));
  if (!value || Array.isArray(value) || typeof value !== "object") throw new Error(`JSON 顶层必须是对象: ${filename}`);
  return value;
}

function number(value, label, minimum, maximum) {
  if (typeof value !== "number" || !Number.isFinite(value)) throw new Error(`${label} 必须是数字`);
  if (value < minimum || value > maximum) throw new Error(`${label} 必须位于 ${minimum}..${maximum}`);
  return value;
}

function round(value) {
  return Math.round((value + Number.EPSILON) * 100) / 100;
}

function weightedDimensions(criteria, byKey, dimension) {
  const groups = new Map();
  for (const criterion of criteria) {
    const group = String(criterion[dimension] ?? "").trim();
    if (!group) continue;
    if (!groups.has(group)) groups.set(group, []);
    groups.get(group).push([Number(criterion.weight), Number(byKey.get(criterion.key).score)]);
  }
  return Object.fromEntries([...groups.entries()].map(([key, values]) => {
    const totalWeight = values.reduce((sum, [weight]) => sum + weight, 0);
    const score = values.reduce((sum, [weight, value]) => sum + weight * value, 0);
    return [key, round(score / totalWeight * 100)];
  }));
}

export function finalize(manifest, contract, execution, scoreInput) {
  const batchIds = new Set([manifest.batch_id, contract.batch_id, execution.batch_id]);
  if (batchIds.size !== 1) throw new Error(`batch_id 不一致: ${[...batchIds].join(", ")}`);
  const taskId = contract.task_id;
  if (manifest.task_id !== taskId || execution.task_id !== taskId) throw new Error("task_id 不一致");
  if (manifest.source?.task_sha256 !== contract.source?.task_sha256) throw new Error("task_sha256 不一致");

  const executionStatus = execution.execution?.status;
  const evaluationStatus = scoreInput.evaluation_status;
  if (!EXECUTION_STATUSES.has(executionStatus)) throw new Error(`非法 execution.status: ${executionStatus}`);
  if (!EVALUATION_STATUSES.has(evaluationStatus)) throw new Error(`非法 evaluation_status: ${evaluationStatus}`);
  const manifestModel = String(manifest.model?.id ?? "");
  const executionModel = String(execution.model?.id ?? "");
  const manifestHarness = String(manifest.harness?.id ?? "");
  const executionHarness = String(execution.harness?.id ?? "");
  if (manifestModel && executionModel !== manifestModel) throw new Error("execution_record.model.id 与 task manifest 不一致");
  if (executionHarness !== manifestHarness) throw new Error("execution_record.harness.id 与 task manifest 不一致");
  if (evaluationStatus === "evaluation_error" && !String(scoreInput.evaluation_error ?? "").trim()) {
    throw new Error("evaluation_error 状态必须填写 evaluation_error");
  }

  const criteria = contract.criteria ?? [];
  const observed = scoreInput.criteria ?? [];
  const expectedKeys = criteria.map((item) => item.key);
  const actualKeys = observed.map((item) => item.key);
  if (JSON.stringify(expectedKeys) !== JSON.stringify(actualKeys)) {
    throw new Error("score_input.criteria 必须按 task contract 原顺序完整填写");
  }
  const forcedZero = ["execution_error", "timeout", "pending"].includes(executionStatus) || evaluationStatus === "evaluation_error";
  const byKey = new Map();
  const calculationByKey = new Map();
  for (const item of observed) {
    const hasScore = item.score !== null && item.score !== undefined;
    if (!forcedZero || hasScore) item.score = number(item.score, `criteria.${item.key}.score`, 0, 1);
    if (!forcedZero || hasScore) {
      if (!String(item.reason ?? "").trim()) throw new Error(`criteria.${item.key}.reason 不能为空`);
      if (!Array.isArray(item.actions) || item.actions.length === 0) throw new Error(`criteria.${item.key}.actions 至少记录一个操作或检查动作`);
      if (!Array.isArray(item.evidence) || item.evidence.length === 0) throw new Error(`criteria.${item.key}.evidence 至少记录一条证据`);
    }
    byKey.set(item.key, item);
    calculationByKey.set(item.key, { score: hasScore ? item.score : 0 });
  }

  const successfulEvaluation = executionStatus === "completed" && evaluationStatus === "completed";
  if (successfulEvaluation) {
    for (const criterion of criteria.filter((item) => item.primary === "visual_layout")) {
      if (!byKey.get(criterion.key).evidence.some((item) => item && item.type === "screenshot")) {
        throw new Error(`视觉检查点必须包含 screenshot 证据: ${criterion.key}`);
      }
    }
  }
  const totalWeight = criteria.reduce((sum, item) => sum + Number(item.weight), 0);
  if (criteria.length === 0 || Math.abs(totalWeight - 1) > 0.001) throw new Error("task contract criterion 权重无效");
  const rawScore = criteria.reduce((sum, item) => sum + Number(item.weight) * calculationByKey.get(item.key).score, 0);
  const totalScore = forcedZero ? 0 : round(rawScore / totalWeight * 100);

  const aestheticContract = contract.aesthetic_metric ?? {};
  let aestheticValue = scoreInput.aesthetic_score;
  if (aestheticContract.status === "pending_definition" && aestheticValue !== null && aestheticValue !== undefined) {
    throw new Error("美观度定义尚未提供，aesthetic_score 必须为 null");
  }
  if (aestheticValue !== null && aestheticValue !== undefined) {
    aestheticValue = number(aestheticValue, "aesthetic_score", 0, 100);
    if (!String(scoreInput.aesthetic_reason ?? "").trim()) throw new Error("填写 aesthetic_score 时必须填写 aesthetic_reason");
  } else {
    aestheticValue = null;
  }

  const primary = weightedDimensions(criteria, calculationByKey, "primary");
  const secondary = weightedDimensions(criteria, calculationByKey, "secondary");
  const zeroed = (value) => Object.fromEntries(Object.keys(value).map((key) => [key, 0]));
  return {
    schema_version: SCHEMA_VERSION,
    identity: {
      batch_id: manifest.batch_id,
      task_id: taskId,
      task_name: contract.task_name ?? taskId,
      difficulty: contract.difficulty ?? "unknown",
      model: execution.model ?? manifest.model ?? {},
      harness: execution.harness ?? manifest.harness ?? {},
    },
    execution: execution.execution ?? {},
    usage: execution.usage ?? {},
    tools: execution.tools ?? {},
    evaluation: {
      status: evaluationStatus,
      error: scoreInput.evaluation_error ?? null,
      site_url: scoreInput.site_url ?? null,
      browser: scoreInput.browser ?? {},
      criteria: criteria.map((criterion) => {
        const observation = byKey.get(criterion.key);
        return {
          index: criterion.index,
          key: criterion.key,
          name: criterion.name,
          primary: criterion.primary,
          secondary: criterion.secondary,
          weight: criterion.weight,
          score: observation.score,
          reason: observation.reason,
          actions: observation.actions,
          evidence: observation.evidence,
        };
      }),
      scorer: scoreInput.scorer ?? {},
    },
    metrics: {
      total_score: totalScore,
      score_rate: totalScore,
      strict_full_score: totalScore === 100 && !forcedZero,
      primary_dimensions: forcedZero ? zeroed(primary) : primary,
      secondary_dimensions: forcedZero ? zeroed(secondary) : secondary,
      aesthetic: {
        score: aestheticValue,
        max_score: 100,
        included_in_total: false,
        status: aestheticContract.status ?? "pending_definition",
        reason: scoreInput.aesthetic_reason ?? null,
      },
    },
    artifacts: execution.artifacts ?? {},
    provenance: {
      skill_version: SKILL_VERSION,
      scored_at: new Date().toISOString(),
      task_sha256: contract.source?.task_sha256 ?? null,
      workspace_exec_sha256: contract.source?.workspace_exec_sha256 ?? null,
    },
  };
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  for (const key of ["manifest", "task-contract", "execution-record", "score-input", "output"]) {
    if (!args[key]) throw new Error(`必须提供 --${key}`);
  }
  const result = finalize(
    loadJson(args.manifest),
    loadJson(args["task-contract"]),
    loadJson(args["execution-record"]),
    loadJson(args["score-input"]),
  );
  fs.mkdirSync(path.dirname(path.resolve(args.output)), { recursive: true });
  fs.writeFileSync(args.output, `${JSON.stringify(result, null, 2)}\n`, "utf8");
  process.stdout.write(`PASS: ${path.resolve(args.output)}\n`);
}

if (process.argv[1] && fs.realpathSync(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    main();
  } catch (error) {
    process.stderr.write(`FAIL: ${error.message}\n`);
    process.exitCode = 2;
  }
}
