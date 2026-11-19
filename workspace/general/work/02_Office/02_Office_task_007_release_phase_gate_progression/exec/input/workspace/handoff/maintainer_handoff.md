
# Maintainer handoff notes, current day

- 本轮维护者目标：把 quillship-cli 的本地 release board 从当前 gate 推进到下一步，如果公开本地证据允许。
- “mostly green” 是人工口头描述，不等价于 `local_validation` admitted。
- 如果 docs lookup 只能从本地 records 补齐，就写明 local record source；不要去查真实 registry 或远程 checksum。
- 如果你看到旧板里写 “ready to publish”，请和 `config/release_scope.json` 的 scope_version 核对。旧 scope 的文字不能盖过当前 JSON state。
- 交接摘要需要对维护者有用，但不要把所有字段逐项复制成字段清单；重点说明更新了哪些 artifact role、处理了哪些 category、是否仍有人审或 carry-forward。

## Operator shorthand that may mislead

- “green enough” means the maintainer saw several passed rows, not that all blockers are gone.
- “ship lane” refers to a future lane label; it is not the current phase unless JSON state and audit agree.
- “same docs as last run” was written before the docs bundle patch at `2026-08-05T10:18:00Z`.
