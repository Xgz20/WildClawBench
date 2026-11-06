// Each render gets an independent viewport; the exported workbook stays read-only.
export const PREVIEW_PROFILE = "fresh-import-per-preview/v1";

export async function renderIsolatedPreview(workbookFile, options, importWorkbook) {
  const previewWorkbook = await importWorkbook(workbookFile);
  return previewWorkbook.render({ ...options });
}
