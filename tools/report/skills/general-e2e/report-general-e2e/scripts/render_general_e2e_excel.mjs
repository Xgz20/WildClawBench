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
  if (typeof value === "string" && value.startsWith("=")) return "'" + value;
  return value === null || value === undefined ? "-" : value;
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


function scoreScale(sheet, address, maximum = 1) {
  sheet.getRange(address).conditionalFormats.add("colorScale", {
    thresholds: [0, maximum / 2, maximum],
    colors: ["#F8696B", "#FFEB84", "#63BE7B"],
  });
}


function buildView(workbook, name, view) {
  const sheet = workbook.worksheets.add(name);
  sheet.showGridLines = false;
  const end = table(sheet, 1, view.headers, view.rows);
  const last = columnName(view.headers.length);
  sheet.getRange(`A1:${last}${Math.max(end, 1)}`).format.font.name = "Arial";
  sheet.getRange(`A1:${last}${Math.max(end, 1)}`).format.font.size = 11;
  sheet.getRange(`A1:${last}1`).format.rowHeight = 38;
  sheet.getRange("A:A").format.columnWidth = 31;
  for (let i = 1; i < view.headers.length; i++) {
    const col = columnName(i + 1);
    sheet.getRange(`${col}:${col}`).format.columnWidth = view.headers[i].includes("Cache Write") ? 24 : 18;
    if (view.rows.length) {
      sheet.getRange(`${col}2:${col}${end}`).format.numberFormat = view.formats[String(i)] || "#,##0";
      sheet.getRange(`${col}2:${col}${end}`).format.horizontalAlignment = view.rows.some(row => typeof row[i] === "string") ? "left" : "right";
    }
  }
  if (view.rows.length) {
    sheet.getRange(`A2:${last}${end}`).format.rowHeight = 26;
    if (["总览", "分类对比", "难度对比", "Agent能力对比", "模态对比"].includes(name)) {
      const scoreLast = name === "总览" ? "B" : last;
      scoreScale(sheet, `B2:${scoreLast}${end}`, 100);
    }
  }
  const noteLast = columnName(Math.min(view.headers.length, 7));
  view.notes.forEach((note, i) => {
    const row = end + 3 + i;
    sheet.mergeCells(`A${row}:${noteLast}${row}`);
    sheet.getRange(`A${row}`).values = [[note]];
    sheet.getRange(`A${row}:${noteLast}${row}`).format = {
      font: { size: 10, color: COLORS.text }, wrapText: true, verticalAlignment: "center",
    };
    const textWidth = [...note].reduce((sum, char) => sum + (char.codePointAt(0) > 127 ? 2 : 1), 0);
    const width = 31 + 18 * (Math.min(view.headers.length, 7) - 1);
    sheet.getRange(`A${row}:${noteLast}${row}`).format.rowHeight = Math.max(26, Math.ceil(textWidth / width) * 16);
  });
  sheet.freezePanes.freezeRows(1);
  sheet.freezePanes.freezeColumns(1);
  return sheet;
}


function buildDetails(workbook, data) {
  const headers = ["模型@Harness", "用例名称", "分类", "难度", "模态", "得分", "执行状态", "评分状态",
    "总token", "模型请求数", "任务耗时(s)", "流程耗时(s)", "工具调用数", "运行ID"];
  const rows = data.tasks.map(row => [
    data.presentation.unit_labels[row.unit_id], row.task_name, row.category, row.difficulty, row.modality,
    row.total_score === null ? null : row.total_score * 100, row.execution_status, row.score_status,
    ...["total_tokens", "request_count", "agent_duration_seconds", "duration_seconds", "call_count"].map(key => row.resource[key].complete ? row.resource[key].value : null),
    row.run_id,
  ]);
  const sheet = buildView(workbook, "用例明细", { headers, rows, formats: {"5": "0.00", "10": "#,##0.000", "11": "#,##0.000"},
    notes: ["各资源仅展示完整观测值；部分值和证据来源见资源覆盖与异常。"] });
  widths(sheet, { B: 36, C: 27, N: 62 });
  if (rows.length) scoreScale(sheet, `F2:F${rows.length + 1}`, 100);
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
  const exceptions = data.tasks.filter(row => row.score_status !== "valid" || row.execution_status !== "completed").map(row => [
    row.run_id, row.execution_status, row.score_status, row.invalid_reason,
    row.evidence_completeness, row.judge?.protocol, row.scoring_attempt_id,
    "不进入有效均分，不补零",
  ]);
  end = table(sheet, exceptionRow + 1,
    ["运行ID", "执行状态", "评分状态", "无效原因", "证据完整性", "裁判协议", "评分attempt", "分母处理"],
    exceptions,
  );
  const lineageRow = end + 2;
  section(sheet, lineageRow, 6, "输入谱系（哈希显示前12位，完整值见报告JSON）");
  end = table(sheet, lineageRow + 1,
    ["Unit", "Package ID", "归档SHA", "Package manifest SHA", "Submission SHA", "导入回执SHA"],
    data.lineage.selected_imports.map(row => [row.unit_id, ...[row.package_id, row.archive_sha256, row.package_manifest_sha256, row.submission_sha256, row.import_receipt_sha256].map(value => value?.slice(0, 12) || null)]),
  );
  section(sheet, end + 2, 5, "维度有效样本覆盖");
  end = table(sheet, end + 3, ["模型@Harness", "对比表", "维度", "有效样本数", "涉及样本数"], data.presentation.dimension_coverage);
  section(sheet, end + 2, 5, "单元身份与裁判协议");
  const metadataStart = end + 4;
  end = table(sheet, end + 3, ["Unit", "模型@Harness", "配置模型", "Harness 身份", "裁判分组"], data.presentation.unit_metadata);
  if (data.presentation.unit_metadata.length) {
    sheet.getRange(`C${metadataStart}:E${end}`).format.wrapText = true;
    sheet.getRange(`A${metadataStart}:E${end}`).format.rowHeight = 110;
  }
  section(sheet, end + 2, 2, "公共报告字典来源");
  table(sheet, end + 3, ["文件", "SHA-256（前12位）"], Object.entries(data.presentation.reference_sources).map(([name, hash]) => [name, hash.slice(0, 12)]));
  widths(sheet, { A: 58, B: 28, C: 24, D: 16, E: 16, F: 16, G: 14, H: 14, I: 14, J: 16, K: 58, L: 16, M: 16 });
  if (data.presentation.unit_metadata.length) sheet.getRange(`C${metadataStart}:E${end}`).format.autofitRows();
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
  for (const name of data.presentation.sheet_order) buildView(workbook, name, data.presentation.tables[name]);
  buildDetails(workbook, data);
  buildCoverage(workbook, data);
  workbook.recalculate();

  await fs.mkdir(path.dirname(args.output), { recursive: true });
  await fs.mkdir(args["preview-dir"], { recursive: true });
  const sheetNames = [...data.presentation.sheet_order, "用例明细", "资源覆盖与异常"];
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
    ...data.presentation.sheet_order.map(name => [name, `A1:${columnName(data.presentation.tables[name].headers.length)}${data.presentation.tables[name].rows.length + 1}`]),
    ["用例明细", `A1:N${1 + data.tasks.length}`],
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
