# 发布筹备门槛与裁决顺序

G01 有效变更与最新范围
先按changes.jsonl的seq升序折叠，不按文件行次或时间猜测。baseline须approved且含PM签署；scope须approved且同时含PM、SEC；budget须approved且含FIN。其他事件保留为rejected，不得覆盖有效状态。只更新该有效事件明确列出的字段，其余保留；无权跨kind改预算或资源。E02的范围审批不等于Q_RELEASE发布执行批准。
work_breakdown.csv共18项。保留所有mandatory，DELIVERY_ONE中T09A/T09B恰选一个，其余明确not_selected且日期空白、无本期工时/费用。T12按最终有效变更决定必须性和时长。源prerequisite_groups中分号为全需、竖线为组内至少一个已选前置；未选项不作已完成前置。

G02 给定日历、资源与场地
resources.xlsx的capacity表是唯一给定工作日历，18日的day_id与原生日期对应；不能从真实节假日补日。每项duration_workdays是连续给定工作日，开始/结束均需在表中。依赖必须在前项结束后的下一个给定工作日开始，不能同日假装先后完成。每项每个占用日均需CSV所列各角色小时，不按总工时平均、跨日借用、增加未列角色或假设加班。DEV在D07为0是不可用。
HALL与STUDIO各只有一个场地槽，1表示当天可用，0表示不可用；相同场地同日不能安排两项。T15的PATH_VENUE随所选T09路径：A用HALL、B用STUDIO。场地0不能当未知；现场路径场地批准Q_VENUE仍unknown，远程路径不需该项额外批准。

G03 窗口、预算与事实范围
窗口表见resources.xlsx#windows。T15恰在一个完整窗口日，T16/T17需在剩余给定日历内；每项固定费用只计一次，不按工期逐日重复。全部选中项费用相加，不能遗漏T12或把未批准预算9000当事实。有效总预算由G01事件折叠得到，不能用原8500或平均月费替代。场地费已含于相应彩排费用，无隐藏真实支付。
分别对W0/W1/W2和A/B两路径核算：schedule_feasible只指满足范围/依赖/逐日资源/场地/日历的排期存在性；within_budget指固定费用不超最终预算；conditional_feasible二者同时为真。可行只代表未来条件性计划，不代表当前获得执行批准。需要给一个预算内可排的备选窗口完整排程，不能因原目标不可行就只交no-go。

G04 发布执行门槛与最小阻塞集
Q_RELEASE当前unknown，由LEGAL在T14或更早核对真实前置证据并请求有权人明确批准；没有批准一律current_go=no_go。若A路径，Q_VENUE当前unknown，由OPS另核场地许可。不得把计划评审、事件scope批准、场地有槽、预算可行当作执行批准。
本题“最小阻塞集”指原目标窗口在当前证据下、跨可选路径取最小基数的未满足硬门槛集，不是最小不可满足子公式：每路径逐项列G_TIME（不存在给定日历资源内排程）、G_BUDGET（固定总费超有效预算）、G_APPROVAL（Q_RELEASE未批准）；A还列G_VENUE_APPROVAL。只列该路径实际未满足的门槛；不把一般风险或已满足门槛塞入集合。原目标最小集选其基数最小者，允许多个并列；每项须有依据和可复核原因。去掉其中任一项就会漏掉一个仍必要且未满足的门槛。备选方案只提出后移、明确追加预算/批准等条件，不承诺能获得批准，不通过删强制验收或加班绕过门槛。

G05 关键路径与可计算交付
release_plan.xlsx保留以下有表头原生记录，可同页/多页，页名和列序自由（同排表用空白列隔开），中文或英文表头等价：
schedule: task_id,summary,owner,venue,start_date,end_date,status,dependencies,acceptance,source_ref。全部18项；未选彩排status=not_selected、日期空白，其他T01-T14=planned、T15-T17=conditional。T12不能因基础CSV可选而漏掉；日期可原生日期或ISO文本。
loads: task_id,date,role,hours；task_id+date+role唯一，只含选中项，小时非负。每项每个占用日不得漏掉源最低小时。
cpm: task_id,duration,es,ef,ls,lf,total_float,critical；对所选17项及源有效先修做无资源DAG的CPM，ES从0，EF=ES+duration，LF向后推、LS=LF-duration、total_float=LS-ES，critical用0/1。这是无资源下界，不等同实际日期；工期改变后前后推和关键标记须更新，允许不同公式实现。
costs: task_id,selected,fixed_cost,extended_cost；全部18项，selected为0/1，extended_cost=selected*fixed_cost。budget: key,value，含budget_cap,total_cost,budget_remaining；费用或选中项改变时总费与余额联动，不能写死结果。
依据可用work_breakdown.csv#Txx、resources.xlsx#capacity@day_id、resources.xlsx#windows、resources.xlsx#budget、changes.jsonl#Exx、gates.md#G01至G07。工时单位小时，费用合成预算元。数值误差<=1e-8。可增加真实前置，不能删源必要前置或造循环。

G06 备选与风险交接
alternatives.json为object：mode=plan_only；effective_events（event_id/status，status用applied/rejected）；effective_scope（T12_required、T12_duration、budget_cap、target_window）；selected_path（A/B）、selected_window；current_go=no_go；window_paths六行含path/window_id/schedule_feasible/within_budget/conditional_feasible/blockers（G04代码数组）/reason；minimum_blocker_sets（path/window_id/blockers，至少一个最小集）；critical_paths（至少一条真实关键路径task_id数组）；approvals两项（id/status/owner/next_action，Q_RELEASE=unknown/LEGAL，Q_VENUE=unknown/OPS，即使B也交接现场备选未决项）；fallbacks（path/window_id/conditions/trigger/total_cost，至少B后移和A追加预算+场地批准）；risks（id/trigger/owner/response/source_ref，至少3项，包括范围未通过、资源变动、批准未到）；unresolved（condition/owner/next_action）；scope_limit=offline_proposal。代码值按材料；JSON键可英文，顺序与BOM自由；不把false和unknown当0互换。
G04最小集评价原目标W0，而不是所选备选窗口。blockers的G_APPROVAL始终表示真实执行证据未知，不因规划可排而消失。A的预算条件须给实际差额，不用“未来找钱”作预算内结论。两条可行后移B路径均可选，不要求某份参考日期或文案。

G07 文档、停止条件与权限
decision.docx说明当前no-go、原目标最小阻塞集、最新有效范围与被拒变更、无资源关键路径与实际资源/窗口区别、预算取舍、方案触发/停止条件、风险与下一步责任。不能仅列字段声称已批准/已执行。附fact_id/value表：selected_path、selected_window、launch_date、total_cost、budget_cap、budget_remaining、T12_duration、current_go、Q_RELEASE_status、cpm_duration；与实际工作簿/JSON一致。自然语言取舍及风险说明由独立语义审阅判断，结构字段不证明业务效果。
所有新交付仅results，原输入只读。只做离线计划，不访问真实账号、不实际发布、不投递/发消息、不支付、不联网或安装依赖，不创建提醒/自动任务。不读GT或真实用户目录。事实、计划与未知分开，不编造批准、演练、完成或现场许可证据。
