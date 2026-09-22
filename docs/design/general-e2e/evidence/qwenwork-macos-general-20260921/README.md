# QwenWork macOS General 集成 canary

日期：2026-09-22（Asia/Shanghai）。本证据覆盖 QwenWorkCN 1.0.6 / macOS x86_64 的单题 live integration canary，不是 5 题或 60 题正式评测。

## 已完成

- 只读 probe：安装身份、CDP `9250`、`agents.db` WAL/SHM 快照可读；21 个历史会话初始均有稳定 session/conversation/sub_chat/project/cwd 绑定，token profile 保持 `unverified-null`。
- 离线回归：Qwen Driver 20/20、Probe/Collector/metadata 相关 Node 38/38；锁定 `playwright-core@1.55.0`。
- 代码修复：活动 WAL/SHM 快照复制、原生 Open Panel 选择器、contenteditable 段落读回、发送按钮语义选择、attempt 项目唯一命名、Qwen 真实 metadata 行分类、Qwen 终态页面标题绑定、Qwen CB-B finalizer 和精确平台写入。
- live 单题：`03_Social_Interaction_task_003_colleague_leave_reply` 只发送一次；原生 session `6abb322e-7317-4084-be89-473c1dd4cefe`，conversation `mubwakktv6s6s8x4`，sub-chat `mubwakktuana6t3r`，cwd 和 local project 一致；恢复 3 次后终态 `completed`，`target_session_verified=true`、`stop_confirmed=true`、`binding_consistent=true`。
- 资源观测：请求数 1、工具调用 0、流程耗时 577.406s、原生 turn 耗时 11.563s；Token/cache 因 1.0.6 语义未验证保持 unavailable。
- CB-B collector 能处理真实 transcript 的系统注入行：`runtime-config`、`workspace-directories`、`active-leaf`、`last-prompt` 记录 metadata coverage，不把缺失 cwd 伪造成内容证据；正式 trace completeness 可达到 complete。

## 当前边界

本轮 live 目录 `/Users/gzx/debug-workspace/e2e-evaluate/qwenwork-macos-general-20260921-v5` 是调试证据，期间为修复平台身份、日志 metadata 和 trace 谱系多次重建 collection，不能直接发布为正式回传包。评分 thread 遇到 Codex 容量错误，未创建替代评分会话。

下一步必须从最新提交重新构建一个干净 release/batch，重新执行 1 题（一次发送），再执行 collector → Qwen finalizer → `run-general-e2e` execution/collect receipt → score/orchestration → report。正式发布前必须验证 `execution_record.evidence.completeness`、trace-index v2 schema、resource provenance 和回传包哈希全部同源。

QwenWork 当前 runtime 的 Token/cache profile 仍为 `null/unavailable`，不阻断内容评分；不把历史日志推断为 Token。Windows、Apple Silicon、三路并发和 60 题全量不在本 canary 范围。

