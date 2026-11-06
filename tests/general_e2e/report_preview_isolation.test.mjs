import assert from "node:assert/strict";
import test from "node:test";
import { renderIsolatedPreview } from "../../tools/report/skills/general-e2e/report-general-e2e/scripts/isolated_workbook_preview.mjs";

test("a right-hand preview cannot carry its viewport into later sheets", async () => {
  const source = Object.freeze({ marker: "one exported workbook" });
  const sessions = [];
  const importWorkbook = async file => {
    assert.equal(file, source);
    const session = { viewport: null };
    sessions.push(session);
    return {
      render: async options => {
        // Reusing a renderer would retain the previous right-hand viewport.
        const actualRange = session.viewport || options.range;
        session.viewport = options.range;
        return { sheetName: options.sheetName, range: actualRange };
      },
    };
  };
  const ranges = [
    { sheetName: "总览", range: "C1:N14" },
    { sheetName: "难度对比", range: "A1:F6" },
    { sheetName: "评分详情", range: "P1:AA8" },
    { sheetName: "资源覆盖与异常", range: "A116:H124" },
  ];
  for (const options of ranges) {
    assert.deepEqual(await renderIsolatedPreview(source, options, importWorkbook), options);
  }
  assert.equal(new Set(sessions).size, ranges.length);
});

test("render errors propagate and the next attempt starts with a clean viewport", async () => {
  const source = Object.freeze({ marker: "frozen" });
  let attempts = 0;
  const importWorkbook = async () => {
    const first = ++attempts === 1;
    return { render: async options => {
      options.range = "mutated renderer viewport";
      if (first) throw new Error("renderer failed");
      return "image";
    } };
  };
  const options = { sheetName: "难度对比", range: "A1:F6" };
  await assert.rejects(renderIsolatedPreview(source, options, importWorkbook), /renderer failed/);
  assert.equal(options.range, "A1:F6");
  assert.equal(await renderIsolatedPreview(source, options, importWorkbook), "image");
  assert.equal(options.range, "A1:F6");
  assert.equal(attempts, 2);
});
