// Report views do not mutate frozen totals or treat missing observations as zero.
const validNumber = value => typeof value === 'number' && Number.isFinite(value) && value >= 0;
const tie = (a, b) => String(a.unit ?? '').localeCompare(String(b.unit ?? ''));

export function numericOrder(a, b, value, descending = false) {
  const av = value(a), bv = value(b);
  if (!validNumber(av)) return validNumber(bv) ? 1 : tie(a, b);
  if (!validNumber(bv)) return -1;
  return (descending ? bv - av : av - bv) || tie(a, b);
}

export function scoreOrder(rows) {
  return [...rows].sort((a, b) => numericOrder(a, b, row => row.total_average_score, true));
}

export function metricDisplay(unit, key, fallback = null) {
  const metric = unit.resource_metrics?.[key];
  if (metric) {
    if (validNumber(metric.total)) return { value: metric.total, partial: false };
    if (validNumber(metric.known_subtotal) && (metric.covered_cases > 0 || metric.partial_cases > 0)) {
      return { value: metric.known_subtotal, partial: true };
    }
    return { value: null, partial: false };
  }
  return { value: validNumber(fallback) ? fallback : null, partial: false };
}

function rowMetric(row, key) {
  const collection = row.resource_collection;
  const status = collection?.metrics?.[key]?.status ?? 'legacy';
  if (!['legacy', 'observed', 'inferred', 'partial'].includes(status)) return null;
  const raw = row.resource_metrics?.[key] ?? row[key];
  const value = validNumber(raw) ? raw : status === 'partial' ? collection?.known_subtotals?.[key] : null;
  return validNumber(value) ? { value, partial: status === 'partial' } : null;
}

export function pairedTokens(unit, detailRows, keys, ratio = false) {
  const rows = detailRows.filter(row => row.unit === unit.unit);
  if (!rows.length) return { value: null, partial: false };
  const totals = keys.map(() => 0);
  let known = 0, partial = false;
  for (const row of rows) {
    const parts = keys.map(key => rowMetric(row, key));
    if (parts.some(part => part === null)) continue;
    const values = parts.map(part => part.value);
    if (values.slice(1).reduce((sum, value) => sum + value, 0) > values[0]) continue;
    known += 1;
    partial ||= parts.some(part => part.partial);
    values.forEach((value, index) => { totals[index] += value; });
  }
  if (!known || (ratio && totals[0] === 0)) return { value: null, partial: false };
  return {
    value: ratio ? totals[1] / totals[0] : totals[0] - totals.slice(1).reduce((sum, value) => sum + value, 0),
    partial: partial || known !== unit.case_count,
  };
}

export const TOKEN_HEADERS = ['模型@Harness', '总 Token', '平均 Token', '输入 Token（含缓存）', '普通输入 Token', '缓存命中输入 Token', '缓存写入输入 Token', '输出 Token', '缓存命中率'];
export const TIMING_HEADERS = ['模型@Harness', '流程耗时(s)', '平均流程耗时(s)', '流程耗时P50(s)', '流程耗时P90(s)'];

export function tokenComparison(data) {
  const units = [...data.units].sort((a, b) => numericOrder(a, b, unit => metricDisplay(unit, 'total_tokens', unit.total_tokens).value));
  const cells = units.map(unit => {
    const total = metricDisplay(unit, 'total_tokens', unit.total_tokens);
    const input = metricDisplay(unit, 'input_tokens', unit.total_input_tokens);
    const read = metricDisplay(unit, 'cache_read_input_tokens', unit.total_cache_read_input_tokens);
    const write = metricDisplay(unit, 'cache_creation_input_tokens', unit.total_cache_creation_input_tokens);
    const output = metricDisplay(unit, 'output_tokens', unit.total_output_tokens);
    return [total, { ...total, value: total.value !== null && unit.case_count > 0 ? total.value / unit.case_count : null },
      input, pairedTokens(unit, data.detail_rows ?? [], ['input_tokens', 'cache_read_input_tokens', 'cache_creation_input_tokens']),
      read, write, output, pairedTokens(unit, data.detail_rows ?? [], ['input_tokens', 'cache_read_input_tokens'], true)];
  });
  return { units, cells, rows: units.map((unit, index) => [unit.unit, ...cells[index].map(cell => cell.value)]) };
}

export function timingComparison(data) {
  const units = [...data.units].sort((a, b) => numericOrder(a, b, unit => unit.total_duration_seconds));
  return { units, rows: units.map(unit => [unit.unit, unit.total_duration_seconds, unit.average_duration_seconds, unit.duration_p50_seconds, unit.duration_p90_seconds]) };
}
