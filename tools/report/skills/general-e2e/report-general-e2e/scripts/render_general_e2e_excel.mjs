#!/usr/bin/env node
import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";


function parseArgs(argv) {
  const args = {};
  for (let index = 0; index < argv.length; index += 2) {
    const key = argv[index];
    const value = argv[index + 1];
    if (!key?.startsWith("--") || value === undefined) throw new Error(`非法参数: ${key ?? ""}`);
    args[key.slice(2)] = value;
  }
  for (const key of ["input", "output", "preview-dir", "skip-preview"]) {
    if (args[key] === undefined) throw new Error(`缺少 --${key}`);
  }
  if (!["true", "false"].includes(args["skip-preview"])) throw new Error("--skip-preview 只接受 true 或 false");
  return args;
}


function columnName(number) {
  let value = number;
  let result = "";
  while (value > 0) {
    value -= 1;
    result = String.fromCharCode(65 + (value % 26)) + result;
    value = Math.floor(value / 26);
  }
  return result;
}


function display(value) {
  return value === null || value === undefined ? "n.a." : value;
}


const COLORS = {
  navy: "#17365D",
  blue: "#2F75B5",
  paleBlue: "#D9EAF7",
  paleGray: "#F3F6F9",
  white: "#FFFFFF",
  text: "#1F2937",
  border: "#D7DEE8",
  green: "#E2F0D9",
  amber: "#FFF2CC",
  red: "#FCE4D6",
};


function title(sheet, row, columns, text) {
  const end = columnName(columns);
  sheet.mergeCells(`A${row}:${end}${row}`);
  const range = sheet.getRange(`A${row}:${end}${row}`);
  range.values = [[text]];
  range.format = {
    fill: COLORS.navy,
    font: { bold: true, color: COLORS.white, size: 16 },
    verticalAlignment: "center",
    horizontalAlignment: "left",
  };
  range.format.rowHeight = 30;
}


function section(sheet, row, columns, text) {
  const end = columnName(columns);
  sheet.mergeCells(`A${row}:${end}${row}`);
  const range = sheet.getRange(`A${row}:${end}${row}`);
  range.values = [[text]];
  range.format = {
    fill: COLORS.paleBlue,
    font: { bold: true, color: COLORS.navy, size: 12 },
    verticalAlignment: "center",
  };
  range.format.rowHeight = 24;
}


function table(sheet, row, headers, rows) {
  const end = columnName(headers.length);
  const header = sheet.getRange(`A${row}:${end}${row}`);
  header.values = [headers];
  header.format = {
    fill: COLORS.blue,
    font: { bold: true, color: COLORS.white },
    wrapText: true,
    horizontalAlignment: "center",
    verticalAlignment: "center",
    borders: { preset: "all", style: "thin", color: COLORS.border },
  };
  header.format.rowHeight = 32;
  if (rows.length) {
    const body = sheet.getRange(`A${row + 1}:${end}${row + rows.length}`);
    body.values = rows.map(values => values.map(display));
    body.format = {
      font: { color: COLORS.text },
      verticalAlignment: "center",
      borders: {
        insideHorizontal: { style: "thin", color: COLORS.border },
        bottom: { style: "thin", color: COLORS.border },
      },
    };
  }
  return row + rows.length;
}


function widths(sheet, values) {
  for (const [column, width] of Object.entries(values)) {
    sheet.getRange(`${column}:${column}`).format.columnWidth = width;
  }
}


function scoreScale(sheet, address) {
  sheet.getRange(address).conditionalFormats.add("colorScale", {
    thresholds: [0, 0.5, 1],
    colors: ["#F8696B", "#FFEB84", "#63BE7B"],
  });
}


function buildOverview(workbook, data) {
  const sheet = workbook.worksheets.add("总览");
  sheet.showGridLines = false;
  title(sheet, 1, 10, `${data.title} · ${data.batch_id}`);
  section(sheet, 3, 10, "范围与评分分母");
  const score = data.overall.score;
  table(sheet, 4,
    ["唯一任务", "任务运行", "单元", "有效评分", "评测异常", "未评分", "有效0分", "有效均分", "分数合计", "有效分母"],
    [[data.scope.unique_task_count, data.scope.task_run_count, data.scope.unit_count,
      score.valid_score_count, score.evaluation_error_count, score.unscored_count,
      score.valid_zero_score_count, score.mean_score, score.score_sum, score.score_denominator]],
  );
  sheet.getRange("H5:I5").format.numberFormat = "0.0000";
  scoreScale(sheet, "H5:H5");

  section(sheet, 7, 10, "执行状态");
  const statusRows = Object.entries(score.execution_status_counts).map(([status, count]) => [status, count]);
  table(sheet, 8, ["状态", "数量"], statusRows);

  const resourceRow = 11 + statusRows.length;
  section(sheet, resourceRow, 10, "资源总览（未知不补零）");
  const resourceRows = Object.entries(data.overall.resources).map(([key, item]) => [
    key, item.label, item.status, item.total, item.known_subtotal,
    item.coverage.known, item.coverage.total, item.partial_case_count,
    Object.entries(item.status_counts).map(([status, count]) => `${status}:${count}`).join("; "),
    item.source_coverage.total === null
      ? `${item.source_coverage.known}/?`
      : `${item.source_coverage.known}/${item.source_coverage.total}`,
  ]);
  const resourceEnd = table(sheet, resourceRow + 1,
    ["字段", "指标", "聚合状态", "完整总量", "已知小计", "完整覆盖数", "任务运行分母", "部分记录", "来源状态", "原生覆盖"],
    resourceRows,
  );
  if (resourceRows.length) {
    sheet.getRange(`D${resourceRow + 2}:E${resourceEnd}`).format.numberFormat = "#,##0.000";
    sheet.getRange(`F${resourceRow + 2}:H${resourceEnd}`).format.numberFormat = "0";
  }

  const timingRow = resourceEnd + 2;
  section(sheet, timingRow, 10, "耗时口径");
  table(sheet, timingRow + 1,
    ["批次壁钟(s)", "壁钟覆盖", "任务耗时完整总量(s)", "任务耗时已知小计(s)", "说明"],
    [[data.overall.timing.batch_wall_clock_seconds,
      `${data.overall.timing.batch_wall_clock_coverage.known}/${data.overall.timing.batch_wall_clock_coverage.total}`,
      data.overall.resources.duration_seconds.total,
      data.overall.resources.duration_seconds.known_subtotal,
      data.overall.timing.note]],
  );
  sheet.getRange(`A${timingRow + 2}:D${timingRow + 2}`).format.numberFormat = "#,##0.000";
  sheet.getRange(`E${timingRow + 2}:E${timingRow + 2}`).format.wrapText = true;
  widths(sheet, { A: 20, B: 24, C: 16, D: 16, E: 18, F: 14, G: 16, H: 14, I: 40, J: 16 });
  sheet.freezePanes.freezeRows(4);
  return sheet;
}


function buildGroups(workbook, data) {
  const sheet = workbook.worksheets.add("分类与难度");
  sheet.showGridLines = false;
  title(sheet, 1, 8, "分类、难度与裁判协议");
  section(sheet, 3, 8, "六类能力");
  const categoryRows = data.overall.categories.map(row => [
    row.category, row.frozen_task_run_count, row.valid_score_count, row.mean_score,
    row.valid_zero_score_count, row.evaluation_error_count, row.unscored_count,
    `${row.valid_score_count}/${row.frozen_task_run_count}`,
  ]);
  let end = table(sheet, 4,
    ["分类", "冻结运行", "有效分母", "有效均分", "有效0分", "评测异常", "未评分", "有效覆盖"],
    categoryRows,
  );
  if (categoryRows.length) {
    sheet.getRange(`D5:D${end}`).format.numberFormat = "0.0000";
    scoreScale(sheet, `D5:D${end}`);
  }

  const difficultyRow = end + 2;
  section(sheet, difficultyRow, 8, "难度");
  const difficultyRows = data.overall.difficulties.map(row => [
    row.difficulty, row.frozen_task_run_count, row.valid_score_count, row.mean_score,
    row.valid_zero_score_count, row.evaluation_error_count, row.unscored_count,
    `${row.valid_score_count}/${row.frozen_task_run_count}`,
  ]);
  end = table(sheet, difficultyRow + 1,
    ["难度", "冻结运行", "有效分母", "有效均分", "有效0分", "评测异常", "未评分", "有效覆盖"],
    difficultyRows,
  );
  if (difficultyRows.length) {
    sheet.getRange(`D${difficultyRow + 2}:D${end}`).format.numberFormat = "0.0000";
    scoreScale(sheet, `D${difficultyRow + 2}:D${end}`);
  }

  const judgeRow = end + 2;
  section(sheet, judgeRow, 9, "裁判协议分组（协议、模型、推理强度不静默合并）");
  const judgeRows = data.overall.judge_groups.map(row => [
    row.protocol, row.model, row.reasoning_effort, row.frozen_task_run_count,
    row.valid_score_count, row.mean_score, row.evaluation_error_count,
    row.unscored_count, row.valid_zero_score_count,
  ]);
  end = table(sheet, judgeRow + 1,
    ["协议", "模型", "推理强度", "冻结运行", "有效分母", "有效均分", "评测异常", "未评分", "有效0分"],
    judgeRows,
  );
  if (judgeRows.length) {
    sheet.getRange(`F${judgeRow + 2}:F${end}`).format.numberFormat = "0.0000";
    scoreScale(sheet, `F${judgeRow + 2}:F${end}`);
  }
  widths(sheet, { A: 32, B: 24, C: 16, D: 14, E: 14, F: 14, G: 14, H: 14, I: 14 });
  sheet.freezePanes.freezeRows(4);
  return sheet;
}


function buildDetails(workbook, data) {
  const sheet = workbook.worksheets.add("用例明细");
  sheet.showGridLines = false;
  const resourceKeys = [
    "input_tokens", "output_tokens", "total_tokens", "cache_read_input_tokens",
    "cache_creation_input_tokens", "reasoning_output_tokens", "request_count",
    "request_attempt_count", "call_count", "duration_seconds", "agent_duration_seconds",
  ];
  const headers = [
    "运行ID", "用例ID", "用例名称", "分类", "难度", "Unit", "Harness", "平台",
    "模型", "推理强度", "执行模式", "执行状态", "证据完整性", "评分状态", "总分",
    "裁判协议", "裁判模型", "裁判推理强度", "执行attempt", "评分attempt",
    ...resourceKeys.map(key => data.overall.resources[key].label),
    "Package ID", "Submission SHA", "Score SHA", "Resource SHA",
  ];
  title(sheet, 1, headers.length, "用例明细");
  const rows = data.tasks.map(row => [
    row.run_id, row.task_id, row.task_name, row.category, row.difficulty, row.unit_id,
    row.harness.id, row.harness.platform, row.model.actual_id ?? row.model.requested_id,
    row.model.reasoning_effort, row.execution_mode, row.execution_status,
    row.evidence_completeness, row.score_status, row.total_score,
    row.judge?.protocol, row.judge?.model, row.judge?.reasoning_effort,
    row.execution_attempt_id, row.scoring_attempt_id,
    ...resourceKeys.map(key => row.resource[key].value ?? row.resource[key].known_subtotal),
    row.lineage.package_id, row.lineage.submission_sha256, row.lineage.score_sha256,
    row.lineage.resource_metrics_sha256,
  ]);
  const end = table(sheet, 3, headers, rows);
  if (rows.length) {
    sheet.getRange(`O4:O${end}`).format.numberFormat = "0.0000";
    scoreScale(sheet, `O4:O${end}`);
    sheet.getRange(`U4:AE${end}`).format.numberFormat = "#,##0.000";
    sheet.getRange(`A4:${columnName(headers.length)}${end}`).format.rowHeight = 34;
  }
  widths(sheet, { A: 58, B: 58, C: 28, D: 26, E: 10, F: 24, G: 18, H: 18, I: 20, J: 14, K: 16, L: 18, M: 16, N: 18, O: 12, P: 22, Q: 24, R: 18, S: 36, T: 36 });
  for (let column = 21; column <= 31; column += 1) sheet.getRange(`${columnName(column)}:${columnName(column)}`).format.columnWidth = 18;
  for (let column = 32; column <= headers.length; column += 1) sheet.getRange(`${columnName(column)}:${columnName(column)}`).format.columnWidth = 36;
  sheet.freezePanes.freezeRows(3);
  sheet.freezePanes.freezeColumns(2);
  return sheet;
}


function buildCoverage(workbook, data) {
  const sheet = workbook.worksheets.add("资源覆盖与异常");
  sheet.showGridLines = false;
  title(sheet, 1, 13, "资源覆盖、异常与谱系");
  section(sheet, 3, 13, "逐用例资源覆盖");
  const rows = [];
  for (const task of data.tasks) {
    for (const [field, observation] of Object.entries(task.resource)) {
      rows.push([
        task.run_id, field, data.overall.resources[field].label, observation.status,
        observation.value, observation.known_subtotal, observation.complete,
        observation.coverage.known, observation.coverage.total,
        observation.coverage.unit, observation.basis,
        task.resource_collection_status, task.score_status,
      ]);
    }
  }
  let end = table(sheet, 4,
    ["运行ID", "字段", "指标", "来源状态", "完整值", "已知小计", "完整覆盖", "原生已知", "原生分母", "原生单位", "依据", "采集状态", "评分状态"],
    rows,
  );
  if (rows.length) {
    sheet.getRange(`E5:F${end}`).format.numberFormat = "#,##0.000";
    sheet.getRange(`A5:M${end}`).format.rowHeight = 32;
    sheet.getRange(`K5:K${end}`).format.wrapText = true;
  }
  const exceptionRow = end + 2;
  section(sheet, exceptionRow, 8, "评测异常与未评分");
  const exceptions = data.tasks.filter(row => row.score_status !== "valid").map(row => [
    row.run_id, row.execution_status, row.score_status, row.invalid_reason,
    row.evidence_completeness, row.judge?.protocol, row.scoring_attempt_id,
    "不进入有效均分，不补零",
  ]);
  end = table(sheet, exceptionRow + 1,
    ["运行ID", "执行状态", "评分状态", "无效原因", "证据完整性", "裁判协议", "评分attempt", "分母处理"],
    exceptions,
  );
  const lineageRow = end + 2;
  section(sheet, lineageRow, 6, "输入谱系");
  table(sheet, lineageRow + 1,
    ["Unit", "Package ID", "归档SHA", "Package manifest SHA", "Submission SHA", "导入回执SHA"],
    data.lineage.selected_imports.map(row => [row.unit_id, row.package_id, row.archive_sha256, row.package_manifest_sha256, row.submission_sha256, row.import_receipt_sha256]),
  );
  widths(sheet, { A: 58, B: 28, C: 24, D: 16, E: 16, F: 16, G: 14, H: 14, I: 14, J: 16, K: 58, L: 16, M: 16 });
  // Native timing adds explicit lifecycle/queue semantics; fit its source text.
  rows.forEach((row, index) => {
    if (["duration_seconds", "agent_duration_seconds"].includes(row[1]) && row[3] === "observed") {
      sheet.getRange(`K${index + 5}`).format.autofitRows();
    }
  });
  sheet.freezePanes.freezeRows(4);
  sheet.freezePanes.freezeColumns(1);
  return sheet;
}


async function main() {
  const args = parseArgs(process.argv.slice(2));
  const data = JSON.parse(await fs.readFile(args.input, "utf8"));
  if (data.schema_version !== "wildclawbench.general-e2e-report-data/v1") {
    throw new Error(`不兼容的报告数据 schema: ${data.schema_version}`);
  }
  const workbook = Workbook.create();
  buildOverview(workbook, data);
  buildGroups(workbook, data);
  buildDetails(workbook, data);
  buildCoverage(workbook, data);
  workbook.recalculate();

  await fs.mkdir(path.dirname(args.output), { recursive: true });
  await fs.mkdir(args["preview-dir"], { recursive: true });
  const sheetNames = ["总览", "分类与难度", "用例明细", "资源覆盖与异常"];
  if (args["skip-preview"] !== "true") {
    for (const sheetName of sheetNames) {
      const image = await workbook.render({ sheetName, autoCrop: "all", scale: 1, format: "png" });
      await fs.writeFile(path.join(args["preview-dir"], `${sheetName}.png`), new Uint8Array(await image.arrayBuffer()));
    }
  }
  const sheetInspection = await workbook.inspect({ kind: "sheet", include: "id,name", maxChars: 3000 });
  const formulaErrors = await workbook.inspect({
    kind: "match",
    searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
    options: { useRegex: true, maxResults: 100 },
    summary: "General E2E report formula error scan",
  });
  const rangeChecks = [];
  for (const [sheetId, range] of [
    ["总览", "A1:J20"],
    ["分类与难度", "A1:I30"],
    ["用例明细", `A1:AI${3 + data.tasks.length}`],
    ["资源覆盖与异常", `A1:M${10 + data.tasks.length * 11}`],
  ]) {
    const inspection = await workbook.inspect({
      kind: "table", sheetId, range, include: "values,formulas",
      tableMaxRows: 8, tableMaxCols: 16, maxChars: 6000,
    });
    rangeChecks.push(inspection.ndjson);
  }
  const file = await SpreadsheetFile.exportXlsx(workbook);
  await file.save(args.output);
  const validationPath = path.join(args["preview-dir"], "excel-validation.json");
  await fs.writeFile(validationPath, JSON.stringify({
    schema_version: "wildclawbench.general-e2e-excel-validation/v1",
    status: "PASS",
    workbook: path.basename(args.output),
    sheets: sheetInspection.ndjson,
    formula_error_scan: formulaErrors.ndjson,
    key_range_checks: rangeChecks,
    previews: args["skip-preview"] === "true" ? [] : sheetNames.map(name => `${name}.png`),
  }, null, 2) + "\n");
  process.stdout.write(JSON.stringify({
    status: "PASS",
    output: args.output,
    preview_status: args["skip-preview"] === "true" ? "SKIPPED" : "COMPLETED",
    sheet_count: sheetNames.length,
    formula_error_scan: formulaErrors.ndjson,
    key_range_check_count: rangeChecks.length,
    validation: validationPath,
  }));
}


const keepAlive = setInterval(() => {}, 1000);
try {
  await main();
} finally {
  clearInterval(keepAlive);
}
