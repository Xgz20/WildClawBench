#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const SCHEMA_VERSION = "wildclawbench.web-e2e-task-score/v1";
const SKILL_VERSION = "4.0.0";
const DETAILED_PROFILE = "web-e2e-detailed-v1";
const ARTIFACTSBENCH_PROFILE = "artifactsbench-web-v1";
const EXECUTION_STATUSES = new Set(["completed", "execution_error", "timeout", "pending", "not_recorded"]);
const EVALUATION_STATUSES = new Set(["completed", "evaluation_error"]);
const AESTHETIC_EVALUATION_STATUSES = new Set(["completed", "evaluation_error"]);
const AESTHETIC_RUBRIC_PATH = fileURLToPath(
  new URL("../references/aesthetic-rubric.json", import.meta.url),
);

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

const AESTHETIC_RUBRIC = loadJson(AESTHETIC_RUBRIC_PATH);

function number(value, label, minimum, maximum) {
  if (typeof value !== "number" || !Number.isFinite(value)) throw new Error(`${label} 必须是数字`);
  if (value < minimum || value > maximum) throw new Error(`${label} 必须位于 ${minimum}..${maximum}`);
  return value;
}

function metricProfile(contract) {
  const profile = String(contract.metric_profile ?? DETAILED_PROFILE);
  if (![DETAILED_PROFILE, ARTIFACTSBENCH_PROFILE].includes(profile)) {
    throw new Error(`不支持的 metric_profile: ${profile}`);
  }
  return profile;
}

function criterionJudgment(item, profile) {
  if (profile === ARTIFACTSBENCH_PROFILE) {
    const rawScore = number(item.raw_score, `criteria.${item.key}.raw_score`, 0, 10);
    if (!Number.isInteger(rawScore)) {
      throw new Error(`criteria.${item.key}.raw_score 必须是 0..10 整数`);
    }
    const score = rawScore / 10;
    if (item.score !== null && item.score !== undefined) {
      const supplied = number(item.score, `criteria.${item.key}.score`, 0, 1);
      if (Math.abs(supplied - score) > 1e-9) {
        throw new Error(`criteria.${item.key}.score 必须等于 raw_score / 10`);
      }
    }
    return { rawScore, score };
  }
  return { rawScore: null, score: number(item.score, `criteria.${item.key}.score`, 0, 1) };
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

function contractIdentity(contract) {
  const identity = contract.identity ?? {};
  return {
    batch_id: identity.batch_id ?? contract.batch_id,
    source_revision: identity.source_revision ?? contract.source_revision ?? null,
    task_id: identity.task_id ?? contract.task_id,
    task_name: identity.task_name ?? contract.task_name,
    difficulty: identity.difficulty ?? contract.difficulty,
    model: identity.model ?? contract.model ?? {},
    harness: identity.harness ?? contract.harness ?? {},
  };
}

function effectiveExecution(identity, execution) {
  if (execution) return execution;
  return {
    batch_id: identity.batch_id,
    task_id: identity.task_id,
    model: identity.model ?? {},
    harness: identity.harness ?? {},
    execution: {
      status: "not_recorded",
      started_at: null,
      finished_at: null,
      duration_seconds: null,
      error: null,
    },
    usage: {
      input_tokens: null,
      output_tokens: null,
      total_tokens: null,
      request_count: null,
      cost_usd: null,
    },
    tools: { call_count: null, format_accuracy: null },
    artifacts: {},
  };
}

function evidencePath(value, label) {
  const raw = String(value ?? "").trim();
  const parts = raw.split(/[\\/]+/);
  if (!raw || path.isAbsolute(raw) || parts.includes("..") || parts[0] !== "evidence") {
    throw new Error(`${label} 必须位于 private-scoring/evidence 下`);
  }
  return raw;
}

function evidenceLabels(value, knownLabels, label) {
  if (!Array.isArray(value) || value.length === 0) throw new Error(`${label} 至少引用一个截图标签`);
  const labels = value.map((item) => String(item ?? "").trim());
  if (labels.some((item) => !item || !knownLabels.has(item))) {
    throw new Error(`${label} 引用了不存在的截图标签`);
  }
  return labels;
}

function aestheticErrorResult(message) {
  return {
    evaluation: {
      status: "evaluation_error",
      error: message,
      screenshots: [],
      dimensions: [],
      checklist: [],
      strengths: [],
      defects: [],
    },
    metrics: {
      score: null,
      max_score: AESTHETIC_RUBRIC.max_score,
      included_in_total: false,
      status: "evaluation_error",
      rubric_id: AESTHETIC_RUBRIC.rubric_id,
      rubric_version: AESTHETIC_RUBRIC.rubric_version,
      scoring_mode: AESTHETIC_RUBRIC.scoring_mode,
      primary_dimensions: {},
      secondary_dimensions: {},
      secondary_dimension_scores: {},
      reason: message,
    },
  };
}

function aestheticNotApplicable() {
  return {
    evaluation: { status: "not_applicable" },
    metrics: {
      score: null,
      included_in_total: false,
      status: "not_applicable",
      primary_dimensions: {},
      secondary_dimensions: {},
      secondary_dimension_scores: {},
    },
  };
}

function finalizeAesthetic(scoreInput, successfulEvaluation) {
  const raw = scoreInput.aesthetic;
  if (!raw || Array.isArray(raw) || typeof raw !== "object") {
    throw new Error("必须按当前美观度标准完整填写 aesthetic；不再接受单一 aesthetic_score");
  }
  if (!AESTHETIC_EVALUATION_STATUSES.has(raw.status)) {
    throw new Error(`非法 aesthetic.status: ${raw.status ?? ""}`);
  }
  if (raw.status === "evaluation_error") {
    const message = String(raw.error ?? "").trim();
    if (!message) throw new Error("aesthetic.evaluation_error 必须填写 error");
    return aestheticErrorResult(message);
  }

  if (!successfulEvaluation && (!Array.isArray(raw.screenshots) || raw.screenshots.length === 0)) {
    return aestheticErrorResult(String(scoreInput.evaluation_error ?? "主评分未正常完成，且没有完成美观度取证"));
  }

  if (!Array.isArray(raw.screenshots) || raw.screenshots.length < 3) {
    throw new Error("美观度统一判定至少需要 2 张桌面截图和 1 张窄屏截图");
  }
  const screenshotLabels = new Set();
  const screenshotPaths = new Set();
  const screenshots = raw.screenshots.map((item, index) => {
    const label = String(item?.label ?? "").trim();
    const screenshotPath = evidencePath(item?.path, `aesthetic.screenshots[${index}].path`);
    const width = number(item?.viewport?.width, `aesthetic.screenshots[${index}].viewport.width`, 1, 10000);
    const height = number(item?.viewport?.height, `aesthetic.screenshots[${index}].viewport.height`, 1, 10000);
    const state = String(item?.state ?? "").trim();
    const description = String(item?.description ?? "").trim();
    if (!label || !state || !description) {
      throw new Error(`aesthetic.screenshots[${index}] 必须填写 label、state 和 description`);
    }
    if (screenshotLabels.has(label)) throw new Error(`美观度截图标签重复: ${label}`);
    if (screenshotPaths.has(screenshotPath)) throw new Error(`美观度截图路径重复: ${screenshotPath}`);
    screenshotLabels.add(label);
    screenshotPaths.add(screenshotPath);
    return { label, path: screenshotPath, viewport: { width, height }, state, description };
  });
  const desktopCount = screenshots.filter((item) => item.viewport.width >= 1024).length;
  const narrowCount = screenshots.filter((item) => item.viewport.width <= 480).length;
  if (desktopCount < 2 || narrowCount < 1) {
    throw new Error("美观度截图必须覆盖至少 2 个桌面状态和 1 个不大于 480px 的窄屏状态");
  }

  const expectedDimensionIds = AESTHETIC_RUBRIC.dimensions.map((item) => item.id);
  const actualDimensionIds = Array.isArray(raw.dimensions) ? raw.dimensions.map((item) => item?.id) : [];
  if (JSON.stringify(expectedDimensionIds) !== JSON.stringify(actualDimensionIds)) {
    throw new Error("aesthetic.dimensions 必须按标准顺序完整填写 6 个维度");
  }

  const expectedChecklistIds = AESTHETIC_RUBRIC.checklist.map((item) => item.id);
  const actualChecklistIds = Array.isArray(raw.checklist) ? raw.checklist.map((item) => item?.id) : [];
  if (JSON.stringify(expectedChecklistIds) !== JSON.stringify(actualChecklistIds)) {
    throw new Error("aesthetic.checklist 必须按标准顺序完整填写 22 个护栏项和 10 个加分项");
  }
  const allowedChecklistStatuses = new Set(AESTHETIC_RUBRIC.checklist_statuses);
  const checklist = AESTHETIC_RUBRIC.checklist.map((definition, index) => {
    const item = raw.checklist[index];
    const status = String(item.status ?? "");
    const rationale = String(item.rationale ?? "").trim();
    if (!allowedChecklistStatuses.has(status)) {
      throw new Error(`aesthetic.checklist.${definition.id}.status 非法: ${status}`);
    }
    if (!rationale) throw new Error(`aesthetic.checklist.${definition.id}.rationale 不能为空`);
    return {
      id: definition.id,
      type: definition.type,
      dimension: definition.dimension,
      label: definition.label,
      status,
      score: AESTHETIC_RUBRIC.checklist_score_values[status],
      rationale,
      evidence: evidenceLabels(item.evidence, screenshotLabels, `aesthetic.checklist.${definition.id}.evidence`),
    };
  });

  const dimensions = AESTHETIC_RUBRIC.dimensions.map((definition, index) => {
    const item = raw.dimensions[index];
    if (item.score !== null && item.score !== undefined) {
      throw new Error(`aesthetic.dimensions.${definition.id}.score 由二级检查点自动计算，输入必须为 null`);
    }
    const rationale = String(item.rationale ?? "").trim();
    if (!rationale) throw new Error(`aesthetic.dimensions.${definition.id}.rationale 不能为空`);
    const applicableChecklist = checklist.filter(
      (check) => check.dimension === definition.id && check.score !== null,
    );
    if (applicableChecklist.length === 0) {
      throw new Error(`${definition.id} 的二级检查点不能全部为 NA`);
    }
    const scoreSum = applicableChecklist.reduce((sum, check) => sum + check.score, 0);
    const maxScore = applicableChecklist.length * 100;
    return {
      id: definition.id,
      label: definition.label,
      weight: definition.weight,
      score: round(scoreSum / maxScore * 100),
      score_sum: scoreSum,
      max_score: maxScore,
      applicable_checklist_count: applicableChecklist.length,
      rationale,
      evidence: evidenceLabels(item.evidence, screenshotLabels, `aesthetic.dimensions.${definition.id}.evidence`),
    };
  });

  if (!Array.isArray(raw.strengths) || raw.strengths.some((item) => !String(item ?? "").trim())) {
    throw new Error("aesthetic.strengths 必须是非空字符串数组或空数组");
  }
  const defectSeverities = new Set(AESTHETIC_RUBRIC.defect_severities);
  if (!Array.isArray(raw.defects)) throw new Error("aesthetic.defects 必须是数组");
  const defects = raw.defects.map((item, index) => {
    const severity = String(item?.severity ?? "");
    const description = String(item?.description ?? "").trim();
    const where = String(item?.where ?? "").trim();
    if (!defectSeverities.has(severity) || !description || !screenshotLabels.has(where)) {
      throw new Error(`aesthetic.defects[${index}] 必须填写合法 severity、description 和截图标签 where`);
    }
    return { severity, description, where };
  });

  const weightTotal = dimensions.reduce((sum, item) => sum + item.weight, 0);
  if (weightTotal !== 100) throw new Error("内置美观度维度权重之和必须为 100");
  const score = round(dimensions.reduce((sum, item) => sum + item.score * item.weight, 0) / weightTotal);
  return {
    evaluation: {
      status: "completed",
      error: null,
      screenshots,
      dimensions,
      checklist,
      strengths: raw.strengths.map((item) => String(item).trim()),
      defects,
    },
    metrics: {
      score,
      max_score: AESTHETIC_RUBRIC.max_score,
      included_in_total: false,
      status: "completed",
      rubric_id: AESTHETIC_RUBRIC.rubric_id,
      rubric_version: AESTHETIC_RUBRIC.rubric_version,
      scoring_mode: AESTHETIC_RUBRIC.scoring_mode,
      primary_dimensions: Object.fromEntries(dimensions.map((item) => [item.id, item.score])),
      secondary_dimensions: Object.fromEntries(checklist.map((item) => [item.id, item.status])),
      secondary_dimension_scores: Object.fromEntries(checklist.map((item) => [item.id, item.score])),
      reason: raw.strengths.length ? raw.strengths.map((item) => String(item).trim()).join("；") : null,
    },
  };
}

export function finalize(manifest, contract, execution, scoreInput) {
  const identity = contractIdentity(contract);
  const profile = metricProfile(contract);
  if (scoreInput.metric_profile && scoreInput.metric_profile !== profile) {
    throw new Error(`score_input metric_profile 不一致: ${scoreInput.metric_profile} vs ${profile}`);
  }
  if (!identity.batch_id || !identity.task_id) throw new Error("task contract 缺少 batch_id 或 task_id");
  const effective = effectiveExecution(identity, execution);
  const batchIds = [identity.batch_id, manifest?.batch_id, effective.batch_id].filter(Boolean);
  if (new Set(batchIds).size !== 1) throw new Error(`batch_id 不一致: ${batchIds.join(", ")}`);
  const taskId = identity.task_id;
  if ((manifest?.task_id && manifest.task_id !== taskId) || effective.task_id !== taskId) throw new Error("task_id 不一致");
  if (manifest?.source?.task_sha256 && manifest.source.task_sha256 !== contract.source?.task_sha256) {
    throw new Error("task_sha256 不一致");
  }

  const executionStatus = effective.execution?.status;
  const evaluationStatus = scoreInput.evaluation_status;
  if (!EXECUTION_STATUSES.has(executionStatus)) throw new Error(`非法 execution.status: ${executionStatus}`);
  if (!EVALUATION_STATUSES.has(evaluationStatus)) throw new Error(`非法 evaluation_status: ${evaluationStatus}`);
  const identityModel = String(identity.model?.id ?? "");
  const manifestModel = String(manifest?.model?.id ?? "");
  const executionModel = String(effective.model?.id ?? "");
  const identityHarness = String(identity.harness?.id ?? "");
  const manifestHarness = String(manifest?.harness?.id ?? "");
  const executionHarness = String(effective.harness?.id ?? "");
  const modelIds = [identityModel, manifestModel, executionModel].filter(Boolean);
  const harnessIds = [identityHarness, manifestHarness, executionHarness].filter(Boolean);
  if (new Set(modelIds).size > 1) throw new Error("model.id 不一致");
  if (new Set(harnessIds).size > 1) throw new Error("harness.id 不一致");
  if (harnessIds.length === 0) throw new Error("task contract 缺少 harness.id");
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
    const rawValue = profile === ARTIFACTSBENCH_PROFILE ? item.raw_score : item.score;
    const hasScore = rawValue !== null && rawValue !== undefined;
    const judgment = (!forcedZero || hasScore)
      ? criterionJudgment(item, profile)
      : { rawScore: null, score: null };
    if (!forcedZero || hasScore) {
      if (!String(item.reason ?? "").trim()) throw new Error(`criteria.${item.key}.reason 不能为空`);
      if (!Array.isArray(item.actions) || item.actions.length === 0) throw new Error(`criteria.${item.key}.actions 至少记录一个操作或检查动作`);
      if (!Array.isArray(item.evidence) || item.evidence.length === 0) throw new Error(`criteria.${item.key}.evidence 至少记录一条证据`);
    }
    byKey.set(item.key, { ...item, rawScore: judgment.rawScore, normalizedScore: judgment.score });
    calculationByKey.set(item.key, { score: hasScore ? judgment.score : 0 });
  }

  const successfulEvaluation = ["completed", "not_recorded"].includes(executionStatus) && evaluationStatus === "completed";
  if (successfulEvaluation) {
    for (const criterion of criteria) {
      const requiredTypes = new Set(criterion.evidence_policy?.required_types ?? []);
      if (criterion.primary === "visual_layout") requiredTypes.add("screenshot");
      for (const requiredType of requiredTypes) {
        if (!byKey.get(criterion.key).evidence.some((item) => item && item.type === requiredType)) {
          throw new Error(`检查点必须包含 ${requiredType} 证据: ${criterion.key}`);
        }
      }
    }
  }
  const totalWeight = criteria.reduce((sum, item) => sum + Number(item.weight), 0);
  if (criteria.length === 0 || Math.abs(totalWeight - 1) > 0.001) throw new Error("task contract criterion 权重无效");
  const rawScore = criteria.reduce((sum, item) => sum + Number(item.weight) * calculationByKey.get(item.key).score, 0);
  const totalScore = forcedZero ? 0 : round(rawScore / totalWeight * 100);

  const primary = weightedDimensions(criteria, calculationByKey, "primary");
  const secondary = weightedDimensions(criteria, calculationByKey, "secondary");
  const zeroed = (value) => Object.fromEntries(Object.keys(value).map((key) => [key, 0]));
  const aesthetic = profile === DETAILED_PROFILE
    ? finalizeAesthetic(scoreInput, successfulEvaluation)
    : aestheticNotApplicable();
  return {
    schema_version: SCHEMA_VERSION,
    metric_profile: profile,
    identity: {
      batch_id: identity.batch_id,
      task_id: taskId,
      task_name: identity.task_name ?? taskId,
      difficulty: identity.difficulty ?? "unknown",
      model: effective.model ?? identity.model ?? manifest?.model ?? {},
      harness: effective.harness ?? identity.harness ?? manifest?.harness ?? {},
    },
    execution: effective.execution ?? {},
    usage: effective.usage ?? {},
    tools: effective.tools ?? {},
    evaluation: {
      status: evaluationStatus,
      error: scoreInput.evaluation_error ?? null,
      site_url: scoreInput.site_url ?? null,
      browser: scoreInput.browser ?? {},
      aesthetic: aesthetic.evaluation,
      criteria: criteria.map((criterion) => {
        const observation = byKey.get(criterion.key);
        return {
          index: criterion.index,
          key: criterion.key,
          name: criterion.name,
          primary: criterion.primary,
          secondary: criterion.secondary,
          weight: criterion.weight,
          ...(profile === ARTIFACTSBENCH_PROFILE ? { raw_score: observation.rawScore } : {}),
          score: observation.normalizedScore,
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
      primary_dimensions: profile === DETAILED_PROFILE ? (forcedZero ? zeroed(primary) : primary) : {},
      secondary_dimensions: profile === DETAILED_PROFILE ? (forcedZero ? zeroed(secondary) : secondary) : {},
      aesthetic: aesthetic.metrics,
    },
    artifacts: effective.artifacts ?? {},
    provenance: {
      skill_version: SKILL_VERSION,
      scored_at: new Date().toISOString(),
      source_revision: identity.source_revision,
      task_sha256: contract.source?.task_sha256 ?? null,
      workspace_exec_sha256: contract.source?.workspace_exec_sha256 ?? null,
    },
  };
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  for (const key of ["task-contract", "score-input", "output"]) {
    if (!args[key]) throw new Error(`必须提供 --${key}`);
  }
  const result = finalize(
    args.manifest ? loadJson(args.manifest) : null,
    loadJson(args["task-contract"]),
    args["execution-record"] ? loadJson(args["execution-record"]) : null,
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
