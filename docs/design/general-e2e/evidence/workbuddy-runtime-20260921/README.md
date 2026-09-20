# WorkBuddy macOS 运行时证据采集验收

2026-09-21；控制 worktree `feat/e2e-harness-contract`；WorkBuddy 5.5.6 / macOS x86_64 / xopglm52 / default-sandbox。版本只作观察信息，门禁检查应用身份及能力。

全新 canary `workbuddy_canary_runtime_20260921_v3` 一次发送，首次执行直接 `COMPLETED`。会话 `2b043f45-07ed-44d9-aa88-65d4d81676f5`，request `req-1789927966616003`，attempt `c5d03ace-42c0-45bf-9d22-728de681960c`。Prompt 发送至终态观察约 20 秒。Collector 从归档的 runtime API 快照取得 Prompt、完整 cwd、request、工具调用和最终回复，结果 `PASS`。空 usage 的 token/cache/积分保持 `null/unavailable`，不补零。

本轮修复了发送后异步观察尚未结束就关闭 CDP 的问题、编辑器布局变化导致的发送按钮坐标不稳定，以及终态仍引用首次运行中快照的问题。WorkBuddy 焦点测试 45/45 PASS，普通 Node 测试进程正常退出。

失败记录保留：`canary-20260921-01` 因提前关闭 CDP 首次绑定失败，随后同 attempt 恢复完成、未重发；`canary-20260921-02` 点击未触发发送，保留 `NEEDS_ATTENTION/uncertain`，未再点击，只在完整 Prompt 精确匹配后清空本次测试草稿；`canary-20260921-03` 为修复后的独立验证。它们不是同一 attempt 的重置或重发。

本证据只证明运行时单题执行与采集，尚不证明正式 cleanup/finalizer、原数据集规则/语义评分、串行批量或仓库外发行。下一项是补齐正式收口入口和独立 Skill 依赖。

本地原件与 SHA 见 [evidence-index.json](evidence-index.json)。调试文件位于 `/Users/gzx/debug-workspace/e2e-evaluate/workbuddy-macos-general-e2e/`，不进入生产 report-workspace。


## 正式收口入口与独立发行

运行时解析和 cleanup/readiness 迁至版本化 `workbuddy-evidence@0.1.0`，execute 0.9.0 / collect 0.6.0 的 ZIP 各自 vendoring；脱仓加载覆盖 collector 与 WorkBuddy finalizer。状态平台沿用 manifest 的 `macos-x86-64`，起止时间取原生 request.timestamp/completedAt。

canary-03 使用留存 raw snapshot 重新规范化得到 `execution-state-normalized.json`（修正平台元数据和原生完成时间，未改 Prompt、会话或执行产物），原始状态保留。真实 cleanup/finalizer 与 verify-only 均 PASS，候选 SHA `f52bea2db84f04565cb85d62dc3f078b079d762dffa15a29e0f2b296ff7da974`。该回执仍为 partial，因为当时公共评分门禁把未知资源字段当作证据不完整；该事实没有被覆盖或升级。后续固定数据集新 attempt 验证新 collector 的最终回复归档和资源准入。


## 资源可观测性与评分准入

`workbuddy-evidence@0.2.0` 区分原生请求采集完整性与指标可观测性：完整绑定和完整轨迹允许 collect completed，缺失 token/cache 仍为 null/unavailable；部分轨迹、未支持块或非法数值不放行。runtime 保留文本和工具块的原始先后顺序；工具别名优先原生 toolName。新增测试覆盖完整证据与空 usage、非法数值、文本/工具顺序、未知块失败关闭；47/47 WorkBuddy 焦点测试，24/24 布局与独立打包回归。旧 canary partial 回执保留，后续正式数据集新批验证。


## 固定用例暴露的草稿同步修复

首个固定五题批次的 S4 停在 `uncertain/NEEDS_ATTENTION`，未重发且保留旧 unit。只读回读证实 Slate 内容已更新，而 InputBoxStore 的 `draft.content.blocks` 仍为空。真实 `rawKeyDown → Input.insertText → keyUp` 无发送探针能同时更新两者；发送前新增唯一 draft provider、完整 text 和 processing 状态核验，避免仅凭 DOM/按钮启用进入 armed。清理仅作用于精确匹配的本次 S4 草稿，没有改动其他会话。15/15 执行焦点回归通过；新的正式批次继续验证。
