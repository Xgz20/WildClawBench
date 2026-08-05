# Sanitization policy

Before importing a CSV into spreadsheet software, treat any cell whose first non-space character is `=`, `+`, `-`, or `@` as formula injection risk.

Sanitize only risky cells by prefixing the original cell text with a single quote (`'`). Preserve all other cell text, headers, row order, column order, commas, and UTF-8 encoding. Do not open Excel and do not evaluate formulas.
