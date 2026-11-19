# 账号体系切换计划验收与边界

A01 计划范围与身份
本题只生成离线计划，不连接真实账号或执行切换。所有身份和业务材料为受控构造。保留T01-T14全部工作项，T01-T13为本次可验收范围，T14单列deferred。EMP员工以employee_id为身份关联主键，禁止仅凭相同邮箱合并。VENDOR以vendor_id+contract_id核对，权限随合同到期，不能继承员工权限。SERVICE服务主体不走交互免密，需owner复核，秘密轮换不在本次切换范围。
输入SANDBOX与TRAINING均为隔离演练环境，不能复用生产会话。PROD仅是未来条件性排期标签；材料不授权实际操作。所有计划/演练/培训均不能写成已经执行或验收通过。

A02 日历、资源与偏序
calendar.csv是唯一工作日来源，2027-04-12为公司停工日，不能用现实节假日或猜测补日。resources.xlsx的capacity表逐日列已扣日常事务的团队小时，0表示不可用。不得将总工时平均摊薄跨日期，也不得跨日借用或使用未列角色。工作项每个实际工作日均需至少work_items.csv各角色列的小时；duration_workdays是连续给定工作日数，周末/停工日可跨但不可算时长。非工作日不安排工时。每项一个牵头角色沿用源owner，协作者按小时计入容量。
依赖均为完成后的下一个给定工作日开始，不能同日先后冒充已满足。T04、T05、T06、T07共用唯一SANDBOX租户，任何一天不可同时进行两项，即使角色小时足够也不可并行；TRAINING独立，不占该租户。可给出不同满足全部约束的排期，不要求匹配某份参考。

A03 固定切换窗口与批准
| window_id | date | start_time | end_time |
| --- | --- | --- | --- |
| W0 | 2027-04-20 | 09:00 | 17:00 |
| W1 | 2027-04-22 | 09:00 | 17:00 |
| W2 | 2027-04-27 | 09:00 | 17:00 |

T11只能占用一个完整窗口日。T10评审结束后必须留下1个完整给定工作日作为准备缓冲，评审距切换不超过2个工作日，因此T10应在所选窗口前第2个工作日。需判断全部候选窗口是否存在满足材料的排期，保留不可行原因与约束，不按“列出了窗口”就判可行。
Q1生产切换批准当前unknown，由SEC在T10当日或更早复核。T10可以计划评审，但只有真实前置、快照及批准全部满足才允许go；未知/缺失一律no-go。T11-T13均标conditional并预留全部资源，不能因“待批”而不计工时。备用窗口不是自动切换授权，若改窗口必须重新核对评审新鲜度、资源和缓冲。
window_feasibility的feasible只表示资源/日期/偏序存在条件性排期，不代表Q1已批准；当前执行结论必须current_go=no_go。

A04 切换与回滚门槛
| metric_id | operator | threshold | consecutive_checks |
| --- | --- | --- | --- |
| error_rate | > | 0.01 | 2 |
| privilege_mismatch | > | 0 | 1 |
| login_success | < | 0.99 | 2 |

观察间隔5分钟。遇任一门槛即暂停批次并由OPS决定回滚，不以另两项正常抵销。回滚前必须已有映射/权限快照及旧入口，T07需事先验证恢复可用，目标60分钟内恢复。恢复后由QA按三身份群体重新核验账号/权限、旧入口登录与备用路径，结果未核定不得宣告恢复。免密失败要有MFA/备用登录路径，服务主体不纳入交互免密。
回滚仅在旧身份/旧入口尚保留时成立；解绑旧身份或退役旧入口之后不能承诺一键恢复。Q2退役批准unknown，由IAM与SEC另行确认，不得用Q1替代。

A05 保留期与不完整未来日历
T14必须在T12完整通过、T13移交后，至少再保留5个完整给定工作日，且Q2明确确认才可考虑。按任一可行切换窗口，满足该保留期后的首个可用日期均超出本题给定日历；因此T14标deferred、日期留空、无本期工时，earliest_date_status=after_supplied_calendar_unknown。可以列“待补充后续工作日日历及Q2确认”，不能从真实日历推一个可执行退役日。T14不并入本次完成日及关键路径时长。

A06 关键路径、缓冲与数据交接
关键路径采用T01-T13原始工作项DAG的持续时间CPM，单位为工作日偏移：ES从0开始，EF=ES+duration，LF从项目最早完成时刻向后推，LS=LF-duration，total_float=LS-ES，critical为0/1。分别说明该无资源CPM与实际角色/租户/窗口约束的区别，不能把CPM的偏移当成实际日期。保留全部13项CPM表和至少一条真实关键路径，不强制只有一条。
cutover_plan.xlsx有三个有表头的原生表（可同页/多页，页名、列序不限，中文/英文列名均可）：
schedule: task_id,summary,owner,environment,cohorts,start_date,end_date,status,dependencies,acceptance,source_ref。
loads: task_id,date,role,hours；以task_id+date+role唯一，小时非负，不能漏掉源材料要求的角色。T14不安排日期/本期工时。
cpm: task_id,duration,es,ef,ls,lf,total_float,critical；必须是可计算的数值，duration改变后相关前后推及关键标记应更新。允许不同公式实现，不能写死当前结果。
schedule.status用planned（T01-T10）、conditional（T11-T13）、deferred（T14）。dependencies用源任务ID，多个可逗号/分号/空格分隔；可增加真实前置但不得删源依赖或造循环。source_ref用work_items.csv#Txx、resources.xlsx#capacity@YYYY-MM-DD、calendar.csv#YYYY-MM-DD或acceptance.md#A01到A07，可多条。
risks.json为object，至少包含下列可读字段；JSON顺序、中文/英文键、数字/百分数等价可归一化：
mode=plan_only；current_go=no_go；selected_window；window_feasibility（每窗口window_id/feasible/reason）；ready_buffer_workdays（T10与T11间完整工作日数）；completion_buffer_workdays（T13后至给定日历末完整工作日数）；critical_paths（至少一条task_id数组）；approval（id=Q1,status=unknown,owner=SEC,review_by）；retirement（task_id=T14,status=deferred,approval_id=Q2,approval_status=unknown,minimum_full_workdays=5,earliest_date_status=after_supplied_calendar_unknown）；rollback（max_minutes=60,interval_minutes=5,scope=before_retirement_only,snapshot_required=true,owner=OPS,validation_task=T07,triggers按A04各行metric_id/operator/threshold/consecutive_checks）；identity_controls按A01分EMP/VENDOR/SERVICE列对应主键与权限边界；unresolved列条件和下一步责任。不能把未来窗口列成已执行，不能把unknown写成approved或以0替代。
identity_controls中EMP保留join_key=employee_id、forbid_email_only_merge=true；VENDOR保留join_key=vendor_id+contract_id、expires_on_contract=true、inherit_employee_access=false；SERVICE保留interactive_passwordless=false、owner_review_required=true、secret_rotation=not_in_this_plan。正文怎样解释和组织自由，不要求参考措辞。

A07 文档与事实交接
runbook.docx解释准备、前置未满足时的no-go、条件性切换、三类门槛、回滚执行顺序与恢复验证、T14不可逆/需确认边界，以及角色/共享租户/日期取舍与备选窗口。不得只把“必要时回滚”当门槛。
附简短fact_id/value事实核对表，列selected_window、cutover_date、Q1_status、T14_status、ready_buffer_workdays、completion_buffer_workdays、cpm_duration（无资源DAG时长）。这些事实与实际表格及risks.json一致；文案质量与取舍合理性由独立审阅判断，不能用结构字段冒充已验证的业务效果。
所有新交付仅results，原输入只读。离线、不访问账号、不联网安装、不发送消息或调用付费接口；只读本题材料，不读GT或真实用户文件。
