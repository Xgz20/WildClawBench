#!/usr/bin/env node
import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";


function argsFrom(argv) {
  const args = {};
  for (let index = 0; index < argv.length; index += 2) {
    const key = argv[index];
    if (!key?.startsWith("--") || argv[index + 1] === undefined) {
      throw new Error(`非法参数: ${key ?? ""}`);
    }
    args[key.slice(2)] = argv[index + 1];
  }
  for (const key of ["input", "output", "preview-dir"]) {
    if (!args[key]) throw new Error(`缺少 --${key}`);
  }
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


function shown(value) {
  return value === null || value === undefined ? "-" : value;
}


const COLORS = {
  navy: "#16324F",
  blue: "#2F75B5",
  lightBlue: "#D9EAF7",
  pale: "#F4F7FA",
  white: "#FFFFFF",
  text: "#1F2937",
  border: "#D8DEE8",
};
const GROUP_COLORS = {
  content_structure: "#2F75B5",
  interaction_function: "#548235",
  visual_layout: "#8064A2",
  render_integrity: "#2F75B5",
  layout_hierarchy: "#548235",
  color_typography: "#C55A11",
  component_state: "#8064A2",
  responsive: "#008C95",
  tone_fit: "#A64D79",
  other: "#6B7280",
};
const ARTIFACTSBENCH_PROFILE = "artifactsbench-web-v1";


function styleTitle(sheet, row, lastColumn, title) {
  const end = columnName(lastColumn);
  sheet.mergeCells(`A${row}:${end}${row}`);
  const range = sheet.getRange(`A${row}:${end}${row}`);
  range.values = [[title]];
  range.format = {
    fill: COLORS.navy,
    font: { bold: true, color: COLORS.white, size: 16 },
    verticalAlignment: "center",
    horizontalAlignment: "left",
  };
  range.format.rowHeight = 30;
}


function styleSection(sheet, row, lastColumn, title) {
  const end = columnName(lastColumn);
  sheet.mergeCells(`A${row}:${end}${row}`);
  const range = sheet.getRange(`A${row}:${end}${row}`);
  range.values = [[title]];
  range.format = {
    fill: COLORS.lightBlue,
    font: { bold: true, color: COLORS.navy, size: 12 },
    verticalAlignment: "center",
  };
  range.format.rowHeight = 24;
}


function writeTable(sheet, startRow, headers, rows, options = {}) {
  const endColumn = columnName(headers.length);
  sheet.getRange(`A${startRow}:${endColumn}${startRow}`).values = [headers];
  const header = sheet.getRange(`A${startRow}:${endColumn}${startRow}`);
  header.format = {
    fill: COLORS.blue,
    font: { bold: true, color: COLORS.white },
    wrapText: true,
    horizontalAlignment: "center",
    verticalAlignment: "center",
    borders: { preset: "all", style: "thin", color: COLORS.border },
  };
  header.format.rowHeight = 34;
  if (rows.length) {
    const values = rows.map(row => row.map(shown));
    sheet.getRange(`A${startRow + 1}:${endColumn}${startRow + rows.length}`).values = values;
    const dataRange = sheet.getRange(`A${startRow + 1}:${endColumn}${startRow + rows.length}`);
    dataRange.format = {
      font: { color: COLORS.text },
      verticalAlignment: "center",
      borders: {
        insideHorizontal: { style: "thin", color: COLORS.border },
        bottom: { style: "thin", color: COLORS.border },
      },
    };
    if (options.scoreStartColumn) {
      const scoreStart = columnName(options.scoreStartColumn);
      const scoreEnd = columnName(options.scoreEndColumn ?? headers.length);
      const scoreRange = sheet.getRange(`${scoreStart}${startRow + 1}:${scoreEnd}${startRow + rows.length}`);
      scoreRange.format.numberFormat = "0.00";
      scoreRange.conditionalFormats.add("colorScale", {
        thresholds: [0, 50, 100],
        colors: ["#F8696B", "#FFEB84", "#63BE7B"],
      });
    }
  }
  return startRow + rows.length;
}


function groupedColumns(entries, secondaryPrimary, primaryLabels) {
  const groups = [];
  entries.forEach(([key], index) => {
    const primaryKey = secondaryPrimary[key] ?? "other";
    const previous = groups.at(-1);
    if (previous?.key === primaryKey) {
      previous.endColumn = index + 3;
      return;
    }
    groups.push({
      key: primaryKey,
      label: primaryLabels[primaryKey] ?? "其他",
      startColumn: index + 3,
      endColumn: index + 3,
      color: GROUP_COLORS[primaryKey] ?? GROUP_COLORS.other,
    });
  });
  return groups;
}


function groupedHeaderStyle(color) {
  return {
    fill: color,
    font: { bold: true, color: COLORS.white },
    wrapText: true,
    horizontalAlignment: "center",
    verticalAlignment: "center",
    borders: { preset: "all", style: "thin", color: COLORS.border },
  };
}


function writeGroupedTable(sheet, startRow, headers, rows, groups, options = {}) {
  const fixedColumnCount = options.fixedColumnCount ?? 2;
  for (let column = 1; column <= fixedColumnCount; column += 1) {
    const name = columnName(column);
    sheet.mergeCells(`${name}${startRow}:${name}${startRow + 1}`);
    const range = sheet.getRange(`${name}${startRow}:${name}${startRow + 1}`);
    range.values = [[headers[column - 1]]];
    range.format = groupedHeaderStyle(COLORS.blue);
  }
  for (const group of groups) {
    const start = columnName(group.startColumn);
    const end = columnName(group.endColumn);
    if (group.startColumn < group.endColumn) {
      sheet.mergeCells(`${start}${startRow}:${end}${startRow}`);
    }
    const groupRange = sheet.getRange(`${start}${startRow}:${end}${startRow}`);
    groupRange.values = [[group.label]];
    groupRange.format = groupedHeaderStyle(group.color);
    const metricRange = sheet.getRange(`${start}${startRow + 1}:${end}${startRow + 1}`);
    metricRange.values = [headers.slice(group.startColumn - 1, group.endColumn)];
    metricRange.format = groupedHeaderStyle(group.color);
  }
  sheet.getRange(`A${startRow}:${columnName(headers.length)}${startRow}`).format.rowHeight = 24;
  sheet.getRange(`A${startRow + 1}:${columnName(headers.length)}${startRow + 1}`).format.rowHeight = options.headerRowHeight ?? 42;

  if (rows.length) {
    const dataStart = startRow + 2;
    const dataEnd = dataStart + rows.length - 1;
    const endColumn = columnName(headers.length);
    sheet.getRange(`A${dataStart}:${endColumn}${dataEnd}`).values = rows.map(row => row.map(shown));
    const dataRange = sheet.getRange(`A${dataStart}:${endColumn}${dataEnd}`);
    dataRange.format = {
      font: { color: COLORS.text },
      verticalAlignment: "center",
      borders: {
        insideHorizontal: { style: "thin", color: COLORS.border },
        bottom: { style: "thin", color: COLORS.border },
      },
    };
    if (options.scoreStartColumn) {
      const scoreStart = columnName(options.scoreStartColumn);
      const scoreEnd = columnName(options.scoreEndColumn ?? headers.length);
      const scoreRange = sheet.getRange(`${scoreStart}${dataStart}:${scoreEnd}${dataEnd}`);
      scoreRange.format.numberFormat = "0.00";
      scoreRange.conditionalFormats.add("colorScale", {
        thresholds: [0, 50, 100],
        colors: ["#F8696B", "#FFEB84", "#63BE7B"],
      });
    }
  }
  return startRow + 1 + rows.length;
}


function applyWidths(sheet, widths) {
  for (const [column, width] of Object.entries(widths)) {
    sheet.getRange(`${column}:${column}`).format.columnWidth = width;
  }
}


function normalizeAccuracy(value) {
  if (value === null || value === undefined) return null;
  return value <= 1 ? value * 100 : value;
}


function addScoreScale(sheet, rangeAddress) {
  sheet.getRange(rangeAddress).conditionalFormats.add("colorScale", {
    thresholds: [0, 50, 100],
    colors: ["#F8696B", "#FFEB84", "#63BE7B"],
  });
}


function buildArtifactsWebsiteSheet(workbook, data) {
  const sheet = workbook.worksheets.add("站点评测指标");
  sheet.showGridLines = false;
  const headers = [
    "模型", "Harness", "推理强度", "总平均分", "用例数", "正常完成数", "执行错误数", "超时数", "评测异常数",
    "完成率", "总tokens", "总请求数", "总耗时(s)", "总成本(USD)", "工具调用数", "格式准确率",
  ];
  styleTitle(sheet, 1, headers.length, `ArtifactsBench Web 站点端到端评测指标 · ${data.batch_id}`);
  styleSection(sheet, 3, headers.length, "总分与执行概况（无功能和美观度维度）");
  const rows = data.units.map(unit => [
    unit.model, unit.harness, unit.reasoning_effort, unit.total_average_score, unit.case_count,
    unit.completed_count, unit.execution_error_count, unit.timeout_count, unit.evaluation_error_count,
    unit.completion_rate, unit.total_tokens, unit.total_requests, unit.total_duration_seconds,
    unit.total_cost_usd, unit.tool_call_count, unit.format_accuracy,
  ]);
  writeTable(sheet, 4, headers, rows, { scoreStartColumn: 4, scoreEndColumn: 4 });
  if (rows.length) {
    const end = 4 + rows.length;
    sheet.getRange(`D5:D${end}`).format.numberFormat = "0.00";
    sheet.getRange(`E5:I${end}`).format.numberFormat = "#,##0";
    sheet.getRange(`J5:J${end}`).format.numberFormat = "0.00";
    sheet.getRange(`K5:L${end}`).format.numberFormat = "#,##0";
    sheet.getRange(`M5:M${end}`).format.numberFormat = "0.00";
    sheet.getRange(`N5:N${end}`).format.numberFormat = "$0.000000";
    sheet.getRange(`O5:O${end}`).format.numberFormat = "#,##0";
    sheet.getRange(`P5:P${end}`).format.numberFormat = "0.00";
  }
  applyWidths(sheet, { A: 22, B: 18, C: 14, D: 14, E: 11, F: 13, G: 13, H: 11, I: 13, J: 12, K: 14, L: 14, M: 14, N: 16, O: 14, P: 14 });
  sheet.freezePanes.freezeRows(4);
  sheet.freezePanes.freezeColumns(2);
  return sheet;
}


function buildWebsiteSheet(workbook, data) {
  if (data.metric_profile === ARTIFACTSBENCH_PROFILE) {
    return buildArtifactsWebsiteSheet(workbook, data);
  }
  const sheet = workbook.worksheets.add("站点评测指标");
  sheet.showGridLines = false;
  const summaryHeaders = [
    "模型", "Harness", "推理强度", "总平均分", "得分率", "满分率", "美观度总分",
    "用例数", "正常完成数", "执行错误数", "超时数", "评测异常数", "完成率",
    "总tokens", "总请求数", "总耗时(s)", "总成本(USD)", "工具调用数", "格式准确率",
    "平均耗时(s)", "耗时P50(s)", "耗时P90(s)", "平均成本(USD)",
    "平均总Token", "平均输入Token", "平均输出Token",
  ];
  const primaryEntries = Object.entries(data.labels.primary);
  const secondaryEntries = Object.entries(data.labels.secondary);
  const aestheticPrimaryEntries = Object.entries(data.labels.aesthetic_primary ?? {});
  const aestheticSecondaryEntries = Object.entries(data.labels.aesthetic_secondary ?? {});
  const widestTable = Math.max(summaryHeaders.length, secondaryEntries.length + 2, aestheticSecondaryEntries.length + 2);
  styleTitle(sheet, 1, widestTable, `Web 站点端到端评测指标 · ${data.batch_id}`);
  styleSection(sheet, 3, summaryHeaders.length, "结果与效率指标");
  const summaryRows = data.units.map(unit => [
    unit.model, unit.harness, unit.reasoning_effort, unit.total_average_score, unit.score_rate,
    unit.strict_full_score_rate, unit.aesthetic_score,
    unit.case_count, unit.completed_count, unit.execution_error_count,
    unit.timeout_count, unit.evaluation_error_count, unit.completion_rate,
    unit.total_tokens, unit.total_requests, unit.total_duration_seconds,
    unit.total_cost_usd, unit.tool_call_count, unit.format_accuracy,
    unit.average_duration_seconds, unit.duration_p50_seconds, unit.duration_p90_seconds,
    unit.average_cost_usd, unit.average_total_tokens, unit.average_input_tokens,
    unit.average_output_tokens,
  ]);
  let lastRow = writeTable(sheet, 4, summaryHeaders, summaryRows, { scoreStartColumn: 4, scoreEndColumn: 7 });
  const summaryStart = 5;
  const summaryEnd = 4 + summaryRows.length;
  if (summaryRows.length) {
    sheet.getRange(`D${summaryStart}:G${summaryEnd}`).format.numberFormat = "0.00";
    sheet.getRange(`H${summaryStart}:L${summaryEnd}`).format.numberFormat = "#,##0";
    sheet.getRange(`M${summaryStart}:M${summaryEnd}`).format.numberFormat = "0.00";
    sheet.getRange(`N${summaryStart}:O${summaryEnd}`).format.numberFormat = "#,##0";
    sheet.getRange(`P${summaryStart}:P${summaryEnd}`).format.numberFormat = "0.00";
    sheet.getRange(`Q${summaryStart}:Q${summaryEnd}`).format.numberFormat = "$0.000000";
    sheet.getRange(`R${summaryStart}:R${summaryEnd}`).format.numberFormat = "#,##0";
    sheet.getRange(`S${summaryStart}:V${summaryEnd}`).format.numberFormat = "0.00";
    sheet.getRange(`W${summaryStart}:W${summaryEnd}`).format.numberFormat = "$0.000000";
    sheet.getRange(`X${summaryStart}:Z${summaryEnd}`).format.numberFormat = "#,##0.00";
    addScoreScale(sheet, `M${summaryStart}:M${summaryEnd}`);
  }

  let sectionRow = lastRow + 2;
  const primaryHeaders = ["模型@Harness", "总平均分", ...primaryEntries.map(([, label]) => label)];
  styleSection(sheet, sectionRow, primaryHeaders.length, "站点评测一级维度汇总");
  const primaryRows = data.units.map(unit => [
    unit.unit, unit.total_average_score,
    ...primaryEntries.map(([key]) => unit.primary_dimensions[key]),
  ]);
  lastRow = writeTable(sheet, sectionRow + 1, primaryHeaders, primaryRows, { scoreStartColumn: 2 });

  sectionRow = lastRow + 2;
  const secondaryHeaders = ["模型@Harness", "总平均分", ...secondaryEntries.map(([, label]) => label)];
  styleSection(sheet, sectionRow, secondaryHeaders.length, "站点评测二级维度汇总");
  const secondaryRows = data.units.map(unit => [
    unit.unit, unit.total_average_score,
    ...secondaryEntries.map(([key]) => unit.secondary_dimensions[key]),
  ]);
  const secondaryGroups = groupedColumns(
    secondaryEntries,
    data.labels.secondary_primary ?? {},
    data.labels.primary ?? {},
  );
  lastRow = writeGroupedTable(
    sheet,
    sectionRow + 1,
    secondaryHeaders,
    secondaryRows,
    secondaryGroups,
    { scoreStartColumn: 2 },
  );

  sectionRow = lastRow + 2;
  const aestheticPrimaryHeaders = ["模型@Harness", "美观度总分", ...aestheticPrimaryEntries.map(([, label]) => label)];
  styleSection(sheet, sectionRow, aestheticPrimaryHeaders.length, "美观度一级维度汇总");
  const aestheticPrimaryRows = data.units.map(unit => [
    unit.unit, unit.aesthetic_score,
    ...aestheticPrimaryEntries.map(([key]) => unit.aesthetic_primary_dimensions[key]),
  ]);
  lastRow = writeTable(sheet, sectionRow + 1, aestheticPrimaryHeaders, aestheticPrimaryRows, { scoreStartColumn: 2 });

  sectionRow = lastRow + 2;
  const aestheticSecondaryHeaders = [
    "模型@Harness", "美观度总分", ...aestheticSecondaryEntries.map(([, label]) => `${label} 平均分`),
  ];
  styleSection(sheet, sectionRow, aestheticSecondaryHeaders.length, "美观度二级维度汇总（MET=100、PARTIAL=50、UNMET=0，NA 不计入分母）");
  const aestheticSecondaryRows = data.units.map(unit => [
    unit.unit, unit.aesthetic_score,
    ...aestheticSecondaryEntries.map(([key]) => unit.aesthetic_secondary_dimensions[key]?.average_score),
  ]);
  const aestheticSecondaryGroups = groupedColumns(
    aestheticSecondaryEntries,
    data.labels.aesthetic_secondary_primary ?? {},
    data.labels.aesthetic_primary ?? {},
  );
  writeGroupedTable(
    sheet,
    sectionRow + 1,
    aestheticSecondaryHeaders,
    aestheticSecondaryRows,
    aestheticSecondaryGroups,
    { scoreStartColumn: 2, headerRowHeight: 58 },
  );
  applyWidths(sheet, { A: 24, B: 18, C: 14, D: 13, E: 12, F: 12, G: 14, H: 11, I: 13, J: 13, K: 11, L: 13, M: 12, N: 14, O: 14, P: 14, Q: 16, R: 14, S: 14, T: 14, U: 14, V: 14, W: 16, X: 16, Y: 16, Z: 16 });
  for (let column = 27; column <= widestTable; column += 1) {
    const name = columnName(column);
    sheet.getRange(`${name}:${name}`).format.columnWidth = 18;
  }
  sheet.freezePanes.freezeRows(4);
  sheet.freezePanes.freezeColumns(2);
  return sheet;
}


function buildDifficultySheet(workbook, data) {
  const sheet = workbook.worksheets.add("难度对比");
  sheet.showGridLines = false;
  const headers = ["模型@Harness", "总平均分", ...data.difficulty_values.map(difficulty => `${difficulty}平均分`)];
  styleTitle(sheet, 1, headers.length, "Web 站点难度对比");
  const rows = data.difficulty_rows.map(row => [
    row.unit, row.total_average_score,
    ...data.difficulty_values.map(difficulty => row.difficulties[difficulty].score),
  ]);
  writeTable(sheet, 3, headers, rows, { scoreStartColumn: 2 });
  applyWidths(sheet, { A: 30, B: 14, C: 14, D: 14, E: 14, F: 14 });
  sheet.freezePanes.freezeRows(3);
  sheet.freezePanes.freezeColumns(1);
  return sheet;
}


function buildDetailSheet(workbook, data) {
  const sheet = workbook.worksheets.add("用例对比明细");
  sheet.showGridLines = false;
  const primaryEntries = Object.entries(data.labels.primary);
  const secondaryEntries = Object.entries(data.labels.secondary);
  const detailed = data.metric_profile !== ARTIFACTSBENCH_PROFILE;
  const baseHeaders = [
    "用例ID", "用例名称", "难度", "模型", "Harness", "推理强度", "模型@Harness", "执行状态", "评测状态",
    "总分",
  ];
  const resourceHeaders = ["耗时(s)", "总tokens", "请求数", "成本(USD)", "工具调用数", "格式准确率", "输入tokens", "输出tokens"];
  const headers = detailed
    ? [...baseHeaders, "美观度总分", ...resourceHeaders, ...primaryEntries.map(([, label]) => label), ...secondaryEntries.map(([, label]) => label)]
    : [...baseHeaders, ...resourceHeaders];
  styleTitle(sheet, 1, headers.length, "Web 站点用例对比明细");
  const rows = data.detail_rows.map(row => {
    const base = [
      row.task_id, row.task_name, row.difficulty, row.model, row.harness, row.reasoning_effort, row.unit,
      row.execution_status, row.evaluation_status, row.total_score,
    ];
    const resources = [
      row.duration_seconds, row.total_tokens, row.request_count, row.cost_usd,
      row.tool_call_count, normalizeAccuracy(row.format_accuracy), row.input_tokens, row.output_tokens,
    ];
    return detailed
      ? [...base, row.aesthetic_score, ...resources, ...primaryEntries.map(([key]) => row.primary_dimensions[key]), ...secondaryEntries.map(([key]) => row.secondary_dimensions[key])]
      : [...base, ...resources];
  });
  writeTable(sheet, 3, headers, rows);
  if (rows.length) {
    const end = 3 + rows.length;
    sheet.getRange(`J4:${detailed ? "K" : "J"}${end}`).format.numberFormat = "0.00";
    const offset = detailed ? 1 : 0;
    sheet.getRange(`${columnName(11 + offset)}4:${columnName(11 + offset)}${end}`).format.numberFormat = "0.00";
    sheet.getRange(`${columnName(12 + offset)}4:${columnName(13 + offset)}${end}`).format.numberFormat = "#,##0";
    sheet.getRange(`${columnName(14 + offset)}4:${columnName(14 + offset)}${end}`).format.numberFormat = "$0.000000";
    sheet.getRange(`${columnName(15 + offset)}4:${columnName(15 + offset)}${end}`).format.numberFormat = "#,##0";
    sheet.getRange(`${columnName(16 + offset)}4:${columnName(16 + offset)}${end}`).format.numberFormat = "0.00";
    sheet.getRange(`${columnName(17 + offset)}4:${columnName(18 + offset)}${end}`).format.numberFormat = "#,##0";
    addScoreScale(sheet, `J4:J${end}`);
    if (detailed && headers.length >= 20) {
      addScoreScale(sheet, `T4:${columnName(headers.length)}${end}`);
    }
  }
  applyWidths(sheet, { A: 42, B: 24, C: 10, D: 18, E: 18, F: 14, G: 30, H: 16, I: 16, J: 12, K: 14, L: 12, M: 14, N: 12, O: 14, P: 14, Q: 14, R: 14, S: 14 });
  for (let column = detailed ? 20 : 19; column <= headers.length; column += 1) {
    const name = columnName(column);
    sheet.getRange(`${name}:${name}`).format.columnWidth = 13;
  }
  sheet.freezePanes.freezeRows(3);
  sheet.freezePanes.freezeColumns(2);
  return sheet;
}


const args = argsFrom(process.argv.slice(2));
const data = JSON.parse(await fs.readFile(args.input, "utf8"));
if (data.schema_version !== "wildclawbench.web-e2e-report-data/v1") {
  throw new Error(`不兼容的 report data schema: ${data.schema_version}`);
}

const workbook = Workbook.create();
buildWebsiteSheet(workbook, data);
buildDifficultySheet(workbook, data);
buildDetailSheet(workbook, data);

await fs.mkdir(path.dirname(args.output), { recursive: true });
await fs.mkdir(args["preview-dir"], { recursive: true });
for (const sheetName of ["站点评测指标", "难度对比", "用例对比明细"]) {
  const preview = await workbook.render({ sheetName, autoCrop: "all", scale: 1, format: "png" });
  await fs.writeFile(
    path.join(args["preview-dir"], `${sheetName}.png`),
    new Uint8Array(await preview.arrayBuffer()),
  );
}

const inspection = await workbook.inspect({
  kind: "sheet",
  include: "id,name",
  maxChars: 2000,
});
const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 100 },
  summary: "final formula error scan",
});
const keyRanges = [
  ["站点评测指标", data.metric_profile === ARTIFACTSBENCH_PROFILE
    ? `A1:P${4 + data.units.length}`
    : `A1:${columnName(Math.max(26, 2 + Object.keys(data.labels.secondary).length, 2 + Object.keys(data.labels.aesthetic_secondary ?? {}).length))}${18 + 5 * data.units.length}`],
  ["难度对比", `A1:${columnName(2 + data.difficulty_values.length)}${3 + data.difficulty_rows.length}`],
  ["用例对比明细", `A1:${columnName((data.metric_profile === ARTIFACTSBENCH_PROFILE ? 18 : 19) + Object.keys(data.labels.primary).length + Object.keys(data.labels.secondary).length)}${3 + data.detail_rows.length}`],
];
const tableChecks = [];
for (const [sheetId, range] of keyRanges) {
  const check = await workbook.inspect({
    kind: "table",
    sheetId,
    range,
    include: "values,formulas",
    tableMaxRows: 8,
    tableMaxCols: 30,
    maxChars: 5000,
  });
  tableChecks.push(check.ndjson);
}
const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(args.output);
console.log(JSON.stringify({
  status: "PASS",
  output: args.output,
  sheets: inspection.ndjson,
  formula_error_scan: errors.ndjson,
  key_range_checks: tableChecks,
}));
