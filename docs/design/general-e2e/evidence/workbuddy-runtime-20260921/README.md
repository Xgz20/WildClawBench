# WorkBuddy macOS 运行时证据采集验收

2026-09-21；控制 worktree `feat/e2e-harness-contract`；WorkBuddy 5.5.6 / macOS x86_64 / xopglm52 / default-sandbox。版本只作观察信息，门禁检查应用身份及能力。

全新 canary `workbuddy_canary_runtime_20260921_v3` 一次发送，首次执行直接 `COMPLETED`。会话 `2b043f45-07ed-44d9-aa88-65d4d81676f5`，request `req-1789927966616003`，attempt `c5d03ace-42c0-45bf-9d22-728de681960c`。Prompt 发送至终态观察约 20 秒。Collector 从归档的 runtime API 快照取得 Prompt、完整 cwd、request、工具调用和最终回复，结果 `PASS`。空 usage 的 token/cache/积分保持 `null/unavailable`，不补零。

本轮修复了发送后异步观察尚未结束就关闭 CDP 的问题、编辑器布局变化导致的发送按钮坐标不稳定，以及终态仍引用首次运行中快照的问题。WorkBuddy 焦点测试 45/45 PASS，普通 Node 测试进程正常退出。

失败记录保留：`canary-20260921-01` 因提前关闭 CDP 首次绑定失败，随后同 attempt 恢复完成、未重发；`canary-20260921-02` 点击未触发发送，保留 `NEEDS_ATTENTION/uncertain`，未再点击，只在完整 Prompt 精确匹配后清空本次测试草稿；`canary-20260921-03` 为修复后的独立验证。它们不是同一 attempt 的重置或重发。

本证据只证明运行时单题执行与采集，尚不证明正式 cleanup/finalizer、原数据集规则/语义评分、串行批量或仓库外发行。下一项是补齐正式收口入口和独立 Skill 依赖。

本地原件与 SHA 见 [evidence-index.json](evidence-index.json)。调试文件位于 `/Users/gzx/debug-workspace/e2e-evaluate/workbuddy-macos-general-e2e/`，不进入生产 report-workspace。
