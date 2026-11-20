# 用户D1流失复算定义

本题为合成练习，不连接真实账号。分析发生时点固定截至2026-09-15T23:59:59+08:00，业务日统一Asia/Shanghai（此窗口UTC+08:00）。汇总基准日为2026-09-01至2026-09-15，含两端。CSV是事后抽取，故含少量9月16日事件；不能用它们把9月15日的D1窗口补为完成。全部历史起点已覆盖本题人群首次有效活动，无须猜测更早注册或引入外部数据。

## R-clean 基础格式与重传

record_id唯一，格式R加四位数字。user_id与event_id先去首尾空白并转大写；received_at是接收元数据，不用于按业务日分桶、选择用户首次日或判断观察窗口。occurred_at必须是有明确时区偏移的合法ISO日期时间；无时区、非法日历、空用户/事件ID、不支持event_type或payment金额非有限数字均为基础格式无效。支持login/payment/deactivate三种事件；非payment的amount须空白，payment可有0或负数，但不一定是有效活动。

先剔除基础格式无效行和发生时点晚于截止的行。其余按规范化event_id分组，规范化payload为规范化用户、event_type、UTC发生秒、去空白小写status及payment数值amount（非payment为空）。同ID出现不同payload时整组隔离，不任意挑成功记录。相同payload仅保留record_id数值最小的规范记录，其余标duplicate_transport并关联规范record_id；不能按CSV物理第一行决定。相同用户同一天的不同event_id可以都是有效事件，但活动人数仍按用户去重。

## R-active 有效活动与注销

在规范事件中，login且status=success，或payment且status=settled且amount>0，才可能构成有效活动。失败登录、退款/待支付、支付0或负数均不算活动。deactivate且status=success记录注销，单独不算活动。以每用户最早成功注销时点为永久截止，活动必须严格早于注销；同一秒注销优先，不推断用户重新开户。

## R-cohort 基准日集合与D1

first_active_date是全部给定历史中最早有效活动的上海业务日，必须在去重、冲突和注销规则之后确定。对基准日d：新用户集合是当天有效活跃且first_active_date=d；老用户集合是当天有效活跃且first_active_date<d。两集合互斥，合并等于当天有效活跃用户集合；新增不等于老用户活跃存量，注销、接收或首次支付日不能替代首次有效活跃日。

D1流失分母为该日该集合唯一用户数；分子为其中次日没有任何有效活动的用户数。不比较事件条数，也不从次日用户数直接相减。次日是否活跃仍按上海日和相同清洗/注销规则。只有完整次日落在观测截止内才可计算：2026-09-15的分母已知，分子与流失率均待观察；不能补0。已完成观察但分母为0时，分子为0、率不适用，和未完成观察不同。允许用户隔天回归，不能把更早流失永久从以后活跃集合删除。

## R-dashboard 旧看板凭证

old_dashboard.xlsx为旧系统导出的冻结数据，含新/老曲线计数及一张老用户图。计数凭证Sheet记录三个待核点的完整base、denominator、lost和return_evidence列表。各行weight为该旧点实际计数权重，旧分子/分母分别求lost/denominator权重；base代表该点的原始基准集合。return_evidence是日过滤前留存的次日证据，其day_used是旧任务真正使用的日期，不保证正确。每行trace_id和record_id均可回查原CSV；这些是旧处理结果，不是给你的新口径。勿仅因曲线同形就认定同一原因，也勿把新曲线真实变化一并修平。

## R-output 交付与复核

cohorts.xlsx可用公式或完整明细复算，不要求交付代码，也不强制所有计数写公式。需有30条日期×new/old汇总（metric_date,cohort,denominator,numerator,rate,observable,reason），rate以比率数值存储。不可适用显示n/a或不适用，原因区分empty_cohort与unobserved；未观察分子留空，完成且空队列分子0。

底稿至少能回查全部1200原记录的record_id/source_row（CSV含表头的物理行）/decision/canonical_record_id、全部有效user-day的user_id/activity_date/first_active_date/event_ids/record_ids，以及每个基准日集合成员的metric_date/cohort/user_id/first_active_date/returned_next/lost/base_event_ids/next_event_ids。列表可用JSON数组或清楚分隔的ID集合。未观察成员returned_next/lost为空，次日证据不使用9月16日。允许Sheet、布局、行列序及语义等价中文表头，不能只交一张正确比例图而缺少真实分子分母和成员。输入原文件保持只读。

anomalies.json定位旧看板与正确复算不同的日期/队列，给出旧/新分子分母与率、可核验的直接机制、受影响用户、trace_id及实际record_id/event_id等证据。机制必须由旧凭证和真实事件共同支持，不因曲线相似推断营销、系统停机或用户行为原因。report.html离线展示复算的新老曲线、同源可见每日数值表、三项异常依据及口径/观察限制，数据点应可回查日期、队列和分子分母。不引入CDN、远程脚本、外部字体或真实访问；可用内嵌SVG/Canvas等合理图表。不要只在隐藏脚本JSON里放正确数据而让可见表/图不一致。

所有交付写results，每份不超过5MiB。可重新核对或排序，不能覆盖events.csv、definitions.md或old_dashboard.xlsx，不发送消息、不联网或执行真实业务。输入图片理解不是必要条件，曲线数据与计数凭证均可从原生表格提取。
