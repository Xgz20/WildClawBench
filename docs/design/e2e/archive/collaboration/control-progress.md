# 控制进度入口已合并

> 历史档案：保留迁移前的日期、版本、结果和失败记录。“当前/下一步”、旧派发和桌面时段要求仅属当时快照。现行集成要求及各 Harness 进度只维护在[统一集成契约](../../端到端自动化评测Harness接入契约.md)。

当前进度、未完成项和新会话 Prompt 统一见 [General E2E 开发接续入口](../../端到端自动化评测Harness接入契约.md#integration-progress)。不再另维护控制进度、平台任务卡、交接接收三份状态。

2026-09-19 至 20 日 SLOT01–05 均已在历史记录中释放；当前没有桌面时段申请制度。历史进程、端口、草稿、未收口 attempt 只能作为恢复线索，操作前必须刷新真实现场。

完整历史控制记录可用 `git show e29a7c8:docs/design/e2e/archive/collaboration/control-progress.md` 查询；它包括 WorkBuddy 草稿恢复、QwenWork send=0/关闭库 error 14、DoubaoWork NEEDS_ATTENTION/候选进程残留和旧提交映射，不应据此重发旧任务。
