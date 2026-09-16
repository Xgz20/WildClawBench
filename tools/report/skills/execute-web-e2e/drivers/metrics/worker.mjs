import { collectLocalMetrics } from "./collect.mjs";
import { empty } from "./parsers.mjs";

let input = "";
for await (const chunk of process.stdin) {
  input += chunk;
  if (input.length > 32768) throw new Error("INPUT_TOO_LARGE");
}
try {
  process.stdout.write(JSON.stringify(await collectLocalMetrics(JSON.parse(input))));
} catch (error) {
  // 只输出枚举式原因，JSON/SQL 错误可能包含原始日志正文或凭证，不透传。
  const reason = /^[A-Z_]+$/u.test(error.message || "") ? error.message : "SOURCE_READ_FAILED";
  process.stdout.write(JSON.stringify(empty(reason)));
}
