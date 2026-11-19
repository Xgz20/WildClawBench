# round3 缺答复证据导出兼容修复

原生已受理失败的缺答复提取 Profile v1 返回空答复及缺失说明，但没有返回原取证导出器必读的 `event_index`。round3 Info003、Info004 的原 Worker 均因 `KeyError: 'event_index'` 退出，尚无规则组件、Judge 或分数；候选、原规则和原失败原件保留。第二次规则调度实际首次运行 Info004，并非再次运行 Info003；旧日志和 Worker PID 完整保留。

Score0.10.123 为新评分发布独立 v2 Profile，缺答复时明确返回 `event_index=null`，不把末尾工具、部分消息或失败终态伪造成答复事件。业务判定、权重和原数值函数保持；v1 marker 仍重放原 v1 源码与回执字节。新评分从同一冻结执行准备，旧评分 attempt 不改写。

Orchestrate0.11.97 只为已实际出现的 v6 Info003 精确 contract/source/旧 Profile/请求源码及 KeyError 增加退役入口。要求无 Judge、无分数、Worker 已退出且无残留、runtime 未漂移，锁定全部旧审计。原编排可由新读取器登记未评分失败，其他题仍使用其原冻结 Score；修复评分另建独立项目/聊天，并通过完整范围显式选择合入。

全70项冻结契约扫描确认同一 v1 Profile 直接索引 event_index 的范围只有 Info003、Info004。Orchestrate0.11.98 为已实际失败的 Info004 增加独立 contract/source 精确注册；Info003 的原留证结果及 v1 字节重放保持，0.11.97 原发行继续保留。

验证覆盖缺答复时访问必需索引字段的真实受管 Worker、v1/v2 源码重放差别、原数值规则不变，以及错误类型、key、请求、线程和阶段反例。原生失败准入回放及独立发行测试共37项通过；本机正式失败原件的只读验证通过，布局与差异检查通过。不推送远端。
