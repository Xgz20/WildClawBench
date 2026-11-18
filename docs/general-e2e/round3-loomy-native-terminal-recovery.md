# round3 Loomy 已受理中断与 other 终态恢复

原队列已首次受理40题，38题可信终态；Office017在问题工具未获答复后，原生主助手
以精确 `MessageAbortedError / Aborted` 结束，问题工具同时记录 error、interrupted 和
结束时间。Office018以已完成的 `finish=other` 结束，全部工具已终态。原后端随后退出，
同一GUI主进程使用相同随包二进制、版本和数据库启动新后端。旧适配器只认可 stop、
HTTP5xx及length，因而未能跨后端更换收口这两个已结束请求。

共享组件0.1.15增加 `loomy-native-terminal-failure/v1`。仅接纳上述两个精确终态，
独立核验唯一原Prompt、主用户与全部主助手Spark/High、完整会话子树、消息完成字段、
全部工具及子会话结束、同一安装和新鲜空闲。只有原会话本身已有完整结束证据才可
重新绑定后端，不能用新后端空闲替代旧请求结束。

MessageAbortedError保留为LOOMY_NATIVE_ABORTED，other保留为LOOMY_NATIVE_OTHER_FINISH。
它们都是原已受理attempt的执行失败，原候选和所有已存在文本/轨迹保持，沿原Rubric
交独立规则和Judge，不重发、不改权重、不自动整题零分。最近助手文本若只是确认问题
或前段内容，只作为原始内容保留，不能宣称已完成主答案交付。

未答问题必须具备原生error及精确中断元数据、无output、已结束时间和对应原JSON列SHA，
并生成逐call ID的aborted-without-answer来源回执。待答、已答、未知返回或缺失工具结果
仍拒绝；本修复不会选择PPT风格或替用户回答。原生中断来源未给出操作人，人工操作数与
语义介入总数保留null，不推定为0。通用契约组件1.3.3允许这两个计数字段显式null，仍
要求字段存在，已知值必须是非负整数；布尔、负值、字符串及小数继续拒绝。原执行模式
automatic仅保留派发计划，不代表已证明没有人工操作。

Collector、离线trace/resource重放、正式finalizer与Score独立准入共同复核新证明，包含
后端谱系、未答问题原件、未知计数与失败类型。Token/缓存/请求数原语义保持unavailable，
原生耗时仍标inferred，不从观察空档猜测模型纯耗时。原自动技能和历史合同字节不修改；
新发行分别为Prepare0.3.6、Execute0.15.20、Collect0.12.28、Orchestrate0.11.96、
Score0.10.122、Report0.8.68、Run0.7.33。本轮原正式batch仍使用原Prepare材料和身份，
不重新prepare或重新发送已受理任务。

恢复只沿原队列及原run-config，通过新的SHA绑定source-repair manifest明确冻结40个
已armed attempt与30个未开始任务，旧状态/journal/队列及关键UI源字节留证。已终态题不
重跑，两道旧请求只观察并收口，未发送题按冻结顺序首次派发。正常停机已释放owner锁，
不需删除或恢复未知锁。执行全单元终态、全部collector、逐题finalize、全单元verify-only
与后置评分屏障保持。

专项验证覆盖两个真实session的只读证明与合成回归：后端更换、完整身份、未答问题
中断回执、人工计数null；已答问题、待执行工具、忙碌状态、不同二进制、错误消息头、
HTTP402伪装及伪造零计数均拒绝。历史HTTP5xx和长度截断回放保持。
