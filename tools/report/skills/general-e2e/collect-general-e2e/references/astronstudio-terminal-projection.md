# 已完成 turn 的历史 running 投影

仅当旧执行 state 的 phase/business_status 已完成、唯一终态观察记录的 turn_state=completed、精确终稿来自 completed-turn.assistant_message_id，但 session.native_status 仍为 running 时使用。新执行器分别记录 turn 终态和会话投影；不能直接修改历史 state。

以 `archive_astronstudio_trace.mjs --state-file ABS --source-policy bound-native-sdk --output-dir NEW_ABS` 创建新的归档目录，保留旧归档与 SHA。归档器重新验证原始 SDK 中唯一 session/start/Prompt/目标 turn 完成事件、最终助手消息和完整标准轨迹；取消、歧义、错 turn、终稿冲突及完成后的内容均拒绝。新归档通过 binding_evidence 保存原 state 原字节与不含正文的元数据证明。

对该新 trace 重新采集 resource metrics，再通过标准 finalize 生成正式收据。finalize 和 verify-only 重新计算证明，评分 prepare/verify/archived 也独立重算并冻结原 state SHA。证明不改变候选、评分规则、权重、时间或资源口径，不代表答案正确。

多题 unit 的中间 finalize 可以返回 receipt_path=null；完整批次回执要等待所有题目收口。先完成所有 finalize，再逐题 verify-only 并登记该标准回执。不得为取得回执跳题、手写完成状态或重发已受理的 Prompt。
