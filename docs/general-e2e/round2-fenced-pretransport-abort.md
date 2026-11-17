# AStudio发送前中止竞态证明

Office013的原生用户消息和请求命令已受理；客户端随后记录20秒提交失败、rejected/not-sent、preparationTerminal。没有模型turn、待交互、open turn或排队提升，预热游标仍为emptyPrewarm；但投递账本保留possibly-submitted-v1。旧收口器正确拒绝直接把该账本当作not-submitted。

本机已安装server入口的完整SHA256为`a4d6617fed907d07ca23ffc65b0052a938be0e08d6580476ea58027d38aa0413`。只读ASAR提取已按归档完整性字段复核；归档修改时间早于同一原生主进程启动，进程启动早于本题发送。该唯一版本的超时分支只有在本地submitted仍为false时才产生这个特定错误；onSubmit先持久化保守账本，再设置本地标记。请求在实际RPC写入前检查中止信号，并在该检查后才清除emptyPrewarm。因此，账本可先变为possibly-submitted，而超时仍在发送前中止。

`bound-native-fenced-pretransport-abort/v1`是基于已核验实现和原生记录的独立边界推导，不是假称客户端账本已明确not-submitted。它同时要求唯一指纹、安装/进程时序、完整已受理Prompt与配置、原生拒绝活动及回执、已结算投递、明确空预热和无任何模型/交互/待派发活动。原账本、原state/record、原生快照和源指纹一并保留；未知安装或不满足任一条件继续阻断。

Execute0.15.13/Driver0.4.32仅在显式resume/observe/resolve入口将同一attempt派生为原生启动失败，不发送、不取消、不重启、不改原生数据库。Collect0.12.19与Report0.8.63离线重放证明，SDK/模型耗时等缺失值保持未知。已受理失败随后由独立裁判按原Rubric逐项评分，本Profile不分配分数或策略零分。旧Profile按原逻辑回放。

验证：91项Node回归（含原件逐字节保留、两种Profile的收口/不可变校验、未知源/活动/时序拒绝）及15项组件/布局检查通过；真实Office013快照的纯只读推导通过。候选、Rubric、权重、执行范围与已有发行不变。

0.15.13实机resolver在持久化前被FAILURE_BINDING拒绝：原生源码读取使用了不存在的config.app.path，缺少指纹后严格退回旧Profile。0.15.14/Driver0.4.33改为正式run-config的harness.app_path并校验配置Profile，新增真实配置形状及未知Profile拒绝回归；保留旧失败日志、发行和题目状态，不改变证明条件。
