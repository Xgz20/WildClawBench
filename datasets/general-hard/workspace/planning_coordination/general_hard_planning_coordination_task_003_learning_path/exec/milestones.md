# 作品验收与计划结构

M01 作品与能力证据
| activity_id | criteria | proof |
| --- | --- | --- |
| P1 | R01,R02,R03 | 数据口径与样本边界；可重现清洗/SQL；缺失/重复/异常的检查记录 |
| P2 | R04,R05,R06 | 固定划分与评估口径；至少两条基线；无泄漏检查、失败及局限 |
| P3 | R07,R08,R09 | 有对照的实验；版本化复现及交付；不确定性解释与失败恢复 |
| J1 | R10,R11 | 作品索引与个人贡献边界；模拟反馈及改进记录 |
| L1 | R12 | 对作品与实践证据的复核记录、未达项与下一步 |

这些是未来验收要求，不是本题要求现在完成课程/项目。各里程碑的acceptance可自由组织，但criteria编号要对应源要求，必须有明确可核验产物/判定和调整条件。evidence_status当前统一not_assessed，capability_status为not_yet_verified；安排课程不能自动变成能力已证实。实际作品是否能证明目标能力由独立语义审阅判断，不能只靠编号得结论。

M02 调整与费用规则
单周超时或考试周空档不足时先减并行、移动未开始的活动，保持先修顺序及项目/实习前里程碑；费用超月/年度/总上限时换可支持资源或后移付费开始月，不能涂改预算。诊断显示基础不足、作品未达验收或I1条件未确认时，列具体触发、受影响活动、复核人和下一步。不得承诺固定就业/激活增长。若改为F1，须保留相同时间预算和实习准备，但不能称已获得实习。

M03 可导入的原生计划表
learning_plan.xlsx包含下列有表头记录，可同页/多页，页名和列序不限，中文/英文列名均可，编号保持源代码：
activities: activity_id,name,kind,first_week,last_week,hours_required,planned_hours,fee,status,prerequisites,acceptance,source_ref。
allocations: week_id,activity_id,hours；以week_id+activity_id唯一，0.5小时为最小单位，所有正时间都要计入。
weekly: week_id,month,hours_cap,planned_hours,remaining_hours,overload_hours；全部96个规划周，有值0不是空缺。planned_hours从allocations加总，remaining=cap-planned，overload=MAX(0,planned-cap)，需随小时变化更新。
monthly: month,hours_cap,planned_hours,remaining_hours,fee,year_fee,cumulative_fee,total_fee_remaining,focus,source_ref；完整24个月，即便考试/缓冲月0投入也不省略。月小时从weekly汇总，费用按activities第一次投入所在月一次记入；year_fee为当年累计至本月，cumulative_fee跨两年累计，total_fee_remaining=900-cumulative_fee，均需可计算并随小时/费用变化更新。
milestones: activity_id,criteria,acceptance,evidence_status,capability_status,adjustment_trigger,next_action,source_ref；覆盖M01五项。可与activities同页，不能把说明文档当唯一计算数据。
settings为两列表key/value，含practice_path=I1或F1、Q1_status=unknown、Q2_status=unknown、review_by=2028-05、planning_scope=offline_proposal、reminders=not_created。这里只是计划声明，不替代正式实际工具轨迹证据。activities.status除I1及其依赖L1为conditional外，其余为planned；选F1则F1/L1为planned。first_week/last_week从实际分配推导，可用给定周ID或1至96的全局规划周序号；无正时间时显示unknown，不能把缺失当第0周。allocations可增加week_order辅助列，activities可增加charge_month计算列。planned_hours从allocations汇总，不能写死。
source_ref可定位profile.md#P01至P05、courses.csv#活动ID、availability.xlsx#weekly@周ID或#monthly@月份、milestones.md#M01至M04。

M04 文档交接
portfolio.docx解释学习、作品、实习/备选如何衔接，先修与周预算取舍，五个里程碑怎样验收、何时调整，未知资格和机会如何处置。不创建提醒，也不能声称已验证能力或已获得实习。
附简短fact_id/value事实核对表：practice_path、model_resource（C06A或C06B）、total_fee、total_planned_hours、P3_last_month、practice_status、Q1_status、Q2_status。事实与实际工作簿一致。正文措辞、项目形式和合理排期自由；不要求复刻参考月份。
