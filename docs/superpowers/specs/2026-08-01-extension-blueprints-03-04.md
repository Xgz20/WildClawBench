# 扩展评测题蓝图：03 社交互动与 04 搜索检索

日期：2026-08-01

状态：首批6道样题及01至04类已生成，05类剩余9题已生成待审核；其余8道正式任务及附件未生成

## Judge 离散档位

下列缩写只用于本蓝图压缩重复文字。正式任务的 `LLM Judge Rubric` 必须展开为完整档位，Judge 不得增加整体印象标准。

- `JF(n)` 事实忠实度：`1` 为 ground truth 指定的 n 项核心事实全部正确且无虚构；`0.75` 为仅1处轻微不精确；`0.5` 为至少一半正确且有1项实质遗漏或错误；`0.25` 为少于一半正确或有多项实质错误；`0` 为核心结论冲突、伪造事实或基本无依据。
- `JC(n)` 要求覆盖：`1` 为 n 项全部完整；`0.75` 为仅1项部分完成；`0.5` 为至少一半完整；`0.25` 为完成少量且不足一半；`0` 为均未完成。
- `JQ` 结构与连贯性：`1` 为无逻辑断裂、矛盾或无关段落；`0.75` 为1处轻微跳转或重复；`0.5` 为1处重大或2至3处轻微问题但主线可理解；`0.25` 为多处断裂且需大幅重组；`0` 为不可理解或偏题。
- `JA` 受众与语气：`1` 为全文适配指定对象、关系和语气；`0.75` 为1处局部不匹配；`0.5` 为多处不匹配但仍可使用；`0.25` 为大部分语气或对象错误；`0` 为与要求相反或包含明显冒犯内容。
- `JU` 可直接使用性：`1` 为无需实质修改即可交付；`0.75` 为仅需1处轻微修改；`0.5` 为缺1个核心组件或需多处修改；`0.25` 为只有提纲或需重写；`0` 为没有可用交付物。
- `JL` 自然表达：`1` 为无明显生硬句、模板残留或角色失真；`0.75` 为1至2处局部生硬；`0.5` 为多处生硬但含义明确；`0.25` 为大部分像模板或无法自然朗读；`0` 为不可读。
- `JB(n)` 承诺与不确定性边界：`1` 为 n 项指定边界全部保持，事实、假设和待确认事项清楚分开；`0.75` 为边界正确但1处表述不够精确；`0.5` 为至少一半边界清楚或出现1项实质性过度承诺；`0.25` 为多项边界含混或有多项无依据承诺；`0` 为执行未授权外部动作，或把未确认事项明确写成事实。
- `JD(n)` 降温与冲突处理：`1` 为 n 项指定关切均被中性复述，停止归责并给出下一步；`0.75` 为处理方向正确但1处措辞略带判断；`0.5` 为承认约一半关切但缺少明确下一步；`0.25` 为明显偏袒、训斥或扩大冲突；`0` 为攻击参与者或鼓励冲突继续。
- `JR(n)` 判断与证据映射：`1` 为 n 项关键判断均对应指定来源、条款或记录，并正确区分期间和适用范围；`0.75` 为仅1项映射不完整；`0.5` 为至少一半判断可追溯；`0.25` 为只在文末堆放链接而没有对应关系；`0` 为主要判断无依据、来源错误或与来源相反。

能力缩写：`CG` 代码生成、`TU` 工具调用、`DP` 数据处理、`RV` 检索验证、`RP` 推理规划、`CN` 内容生成、`VD` 验证交付。

表中的权重是各评分组内权重。混合评分任务的最终权重仍为“评分组权重 × 组内权重”。

## 03_Social_Interaction

### 03-001 meeting_reschedule_draft

Prompt：

> 我需要先把会议改期方案发给参与人确认。请读取`/tmp_workspace/meeting_request.json`，从候选时段中选出原定日期内、所有人都能参加的最早30分钟。
>
> 将结果保存到`/tmp_workspace/results/reschedule.json`，保留现有字段`meeting_id,original_start,proposed_start,proposed_end,duration_minutes,selection_reason,subject,body`。草稿里说明原时间、新时间和改期原因，并请大家确认。不要发送消息，也不要修改输入文件。

评分：`H70/30`。现有文件名、task ID、workspace 目录名和难度保持不变。

| 检查点 | 类型 | 组内权重 | 规则 | 能力 |
| --- | --- | ---: | --- | --- |
| slot_selection | Auto | 45% | 会议ID及最早全员可用时段正确 | RP+DP |
| schedule_constraints | Auto | 35% | 原定日期、30分钟时长和原时间正确 | RP+DP |
| structured_delivery | Auto | 20% | 普通UTF-8 JSON、字段和类型正确，输入未修改 | VD |
| draft_factual_fidelity | Judge | 45% | `JF(5)`：会议主题、原时间、新时间、冲突原因、确认请求 | DP+CN |
| draft_send_readiness | Judge | 55% | `JU`：简洁、礼貌，可作为待确认草稿直接使用 | CN+VD |

实施资料：沿用现有`meeting_request.json`和`gt/expected.json`；仅需拆分自动与Judge评分，不增加附件。

### 03-002 support_ticket_summary

Prompt：

> 我要接手这个客服工单。请读取`/tmp_workspace/support_ticket.json`，以线程里的最新消息为准，整理内部摘要并写一段中文客户回复草稿。配置已经调整，但客户还没有复测，所以不要写成问题已经解决，也不要发送回复。
>
> 将结果保存到`/tmp_workspace/results/support_summary.json`，保留现有字段`ticket_id,product,priority,affected_users,status_code,next_action_code,issue_summary,customer_reply_draft`。如果材料支持，状态使用`awaiting_customer_retest`，下一步使用`ask_customer_retest`。

评分：`H40/60`。难度由L1调整为L2；现有文件名、task ID和workspace目录名不变。

| 检查点 | 类型 | 组内权重 | 规则 | 能力 |
| --- | --- | ---: | --- | --- |
| facts_extracted | Auto | 45% | 工单ID、产品、优先级和受影响人数正确 | DP |
| latest_status_and_action | Auto | 35% | 最新状态与下一步代码正确 | DP+RP |
| structured_delivery | Auto | 20% | 普通UTF-8 JSON、字段和类型正确，输入未修改 | VD |
| internal_summary_quality | Judge | 35% | `JF(5)`：SSO登录循环、8人受影响、配置已调整、等待复测、尚未确认解决 | DP+CN |
| resolution_boundary | Judge | 35% | `JB(2)`：不宣称已解决，不新增服务承诺或根因 | RP+CN |
| customer_reply_readiness | Judge | 30% | `JA`：面向客户、简洁礼貌并明确请求复测和回复 | CN+VD |

实施资料：沿用现有`support_ticket.json`和`gt/expected.json`；调整现有自动检查，将开放式摘要与回复移交Judge。

### 03-003 colleague_leave_reply

Prompt：

> 同事小周刚私聊我：“我爸明早做手术，我想请周四、周五两天假。客户资料可能赶不完，能帮我先盯一下项目群吗？我现在有点乱，如果不方便也没关系。”
>
> 我今天可以帮她盯项目群到18:00，有紧急消息可以提醒她，但没法接手客户资料，也不能替她向客户承诺交期；请假仍要由主管确认。帮我写一条80～150字的中文私信，既表示关心，也把能帮到的范围和下一步说清楚。不要追问病情，不要替主管批准请假。只给消息正文。

评分：`J100`。

| 检查点 | 类型 | 组内权重 | 规则 | 能力 |
| --- | --- | ---: | --- | --- |
| context_and_request_coverage | Judge | 25% | `JC(4)`：家人手术、两天请假、客户资料、项目群代看请求 | RP+CN |
| empathy_and_role_fit | Judge | 25% | `JA`：同事关系、支持性表达且不居高临下 | CN |
| privacy_and_commitment_boundary | Judge | 30% | `JB(4)`：代看到18:00、只提醒紧急消息、不接手资料、不批准假期或承诺交期 | RP+CN |
| ready_to_send | Judge | 20% | `JU`：80至150字、交接动作清楚、只有一条消息 | CN+VD |

实施资料：仅Prompt；正式workspace提交`exec/.gitkeep`，不设置运行时外部来源。

### 03-004 angry_customer_first_response

Prompt：

> A customer wrote: “After syncing my notes to a second device, two lines disappeared and one line became the title. If I sync again, will it delete more? I need these notes for work. This is unacceptable.”
>
> We do not yet have a confirmed cause or recovery outcome. Draft the first support reply in no more than 180 words. Acknowledge the impact, give one safe immediate containment step, and ask no more than four focused investigation questions. Do not blame the customer, claim a root cause, promise recovery, or say the issue is fixed. Do not tell the customer to uninstall the app, clear storage, overwrite either device, or keep syncing. Reply with the message only.

评分：`J100`。

| 检查点 | 类型 | 组内权重 | 规则 | 能力 |
| --- | --- | ---: | --- | --- |
| concern_acknowledgement | Judge | 15% | `JC(2)`：疑似内容丢失和工作影响均被承认 | CN |
| deescalation | Judge | 20% | `JD(3)`：承认关切、无归责、明确调查下一步 | RP+CN |
| safe_containment | Judge | 20% | `JC(2)`：暂停相关同步或编辑，并保留设备现状或证据 | RP+VD |
| diagnostic_questions | Judge | 20% | `JC(4)`：最多四问，覆盖版本/设备、同步目标、操作顺序、其他副本 | RP+CN |
| support_boundaries | Judge | 15% | `JB(3)`：不声称根因、不保证恢复、不宣称修复 | RP+CN |
| first_reply_readiness | Judge | 10% | `JU`：180词以内、只有回复正文、可直接发送 | CN+VD |

实施资料：仅Prompt；真实需求原型来自Joplin数据丢失问题，但执行时不访问该Issue。

### 03-005 decline_unpaid_panel

Prompt：

> 我收到一封行业峰会邀请，对方希望我参加一场90分钟线上圆桌、提前看讨论提纲，并在会后帮忙转发宣传；邮件里明确说没有嘉宾费。主办方去年给我的项目做过介绍，我想保持关系，但这次不接受无偿邀约，也不想编造档期冲突。
>
> 请用我的口吻写一封中文回复：明确拒绝这次邀请，不批评对方；如果未来有合适主题和嘉宾预算，可以再联系。对方是Amy，我署名林岚。给出一行邮件主题和一封正文，正文120～220字，不需要解释写作思路，也不要提供多个版本。

评分：`J100`。

| 检查点 | 类型 | 组内权重 | 规则 | 能力 |
| --- | --- | ---: | --- | --- |
| clear_decline_and_scope | Judge | 30% | 明确拒绝本次圆桌及其附带准备、宣传工作 | CN+RP |
| relationship_preservation | Judge | 25% | 感谢邀请和过去支持，并以合适主题和嘉宾预算为条件保留未来合作 | CN |
| honest_boundary_setting | Judge | 25% | 如实说明无偿边界，不虚构日程冲突，不批评或反复议价 | RP+CN |
| email_usability | Judge | 20% | 单一成稿，含主题、Amy称呼、林岚署名，正文120至220字 | CN+VD |

实施资料：仅Prompt；真实需求原型保留“礼貌拒绝邀请且维持关系”的目的，执行时不访问原问答。

### 03-006 interview_slot_coordination

Prompt：

> 候选人的可面试时间在`/tmp_workspace/interview_request.json`，面试官的空闲时间和当前分配量在`/tmp_workspace/interviewer_availability.csv`，轮值规则在`/tmp_workspace/scheduling_rules.json`。请按候选时段顺序选择最早可行的45分钟，并在该时段全程可用的人中分配不超过`max_hosts`的人数；并列时先选本月已分配次数少的，再按`roster_order`排序。
>
> 把计划保存到`/tmp_workspace/results/interview_plan.json`，记录请求ID、建议起止时间、时区、时长、面试官ID列表、人数、状态和选择原因；状态使用`draft_pending_candidate_confirmation`。再写一封`candidate_reply.md`，请候选人确认所选时间，不要透露内部轮值次数。不要发送邮件或创建日历事件，也不要修改输入。

评分：`H70/30`。

| 检查点 | 类型 | 组内权重 | 规则 | 能力 |
| --- | --- | ---: | --- | --- |
| earliest_slot_selected | Auto | 30% | 候选人和至少一位面试官均可参加的最早时段正确 | DP+RP |
| host_assignment | Auto | 30% | 最大人数、当前负载和roster并列规则均正确 | RP+DP |
| duration_timezone_constraints | Auto | 20% | 45分钟及时区换算正确 | DP+VD |
| structured_delivery | Auto | 20% | JSON字段、面试官列表和两个输出文件正确，输入未修改 | VD |
| candidate_message_fidelity | Judge | 40% | `JF(4)`：日期、起止时间、时区、待确认状态 | DP+CN |
| candidate_message_readiness | Judge | 60% | `JA`：面向候选人、简洁、无内部负载信息且可直接发送 | CN+VD |

实施资料：

- 请求`INT-CN-2609`，候选人周岚，时区`Asia/Shanghai`，45分钟；候选时段依次为2026-09-08 09:00、09-08 14:00、09-09 10:00。
- `min_hosts=1`、`max_hosts=3`；09:00时段H01、H02、H03、H04均全程可用，本月已分配次数分别为3、1、1、0，`roster_order`分别为1、2、3、4。
- 确定答案为2026-09-08 09:00至09:45，主持人顺序`H04,H02,H03`。3个附件预计小于30 KB。

### 03-007 community_thread_deescalation

Prompt：

> `/tmp_workspace/thread.json`是一段已经开始互相指责的社区讨论，`/tmp_workspace/member_history.json`记录相关用户近30天的处理历史，`/tmp_workspace/community_guidelines.md`是版规。请按规则做一份值班版主可以直接审核的处理方案，指出要处理的post ID、rule ID、内容动作、用户动作，以及讨论串是否需要暂时关闭和何时可以重开。
>
> 输出`/tmp_workspace/results/moderation_plan.json`、`public_notice.md`和`private_messages.md`。公开说明要让讨论回到问题本身；私信分别匹配首次和重复违规。只做草稿，不要删帖、锁帖、警告用户或发送消息，也不要公开举报人或其他用户的处分信息。

评分：`H40/60`。

| 检查点 | 类型 | 组内权重 | 规则 | 能力 |
| --- | --- | ---: | --- | --- |
| violation_classification | Auto | 35% | P02、P03违反R1，P01、P04保留，post和rule ID正确 | RV |
| proportionate_actions | Auto | 35% | P02按重复违规正式警告，P03按首次违规友好提醒 | RP+RV |
| thread_control_and_delivery | Auto | 30% | 达到旗标阈值后关闭4小时，重开条件和三个输出正确，无副作用 | VD+RP |
| public_notice_quality | Judge | 40% | `JC(4)`：行为边界、4小时冷静期、重开条件、回到主题的要求 | CN+RP |
| private_message_quality | Judge | 35% | `JU`：两封私信分别匹配首次和重复违规，只针对行为 | CN+RP |
| neutrality_and_deescalation | Judge | 25% | `JD(3)`：一致适用规则、不公开羞辱、不泄露举报信息 | RP+CN |

实施资料：

- `thread.json`含P01正常观点、P02人身攻击且3个旗标、P03反击且2个旗标、P04尝试回到主题。
- `member_history.json`记录P02作者近30天已有一次R1，P03作者无历史记录。
- 版规规定首次R1为移除加友好提醒，30天内重复为移除加正式警告；30分钟内达到5个未处理旗标时关闭4小时，清除旗标并发布工作人员说明后重开。
- 确定动作：P02移除并正式警告，P03移除并友好提醒，P01和P04保留，讨论串关闭4小时。预计小于50 KB。

### 03-008 incident_handoff_update

Prompt：

> I’m handing INC-742 to the 22:00 UTC shift. The timeline, latest monitoring snapshot, current shift note, and handoff policy are in `/tmp_workspace/incident_timeline.jsonl`, `/tmp_workspace/monitor_snapshot.json`, `/tmp_workspace/shift_notes.md`, and `/tmp_workspace/handoff_policy.md`. Reconcile them using the newest evidence; do not copy the earlier “resolved” statement if the policy gates are not met.
>
> Create `/tmp_workspace/results/handoff.json` with the current state, completed work, pending actions with owners and deadlines, active risks, and unconfirmed hypotheses. Also write a concise, channel-ready `handoff_message.md` of no more than 220 words. Do not change the incident status, page anyone, or post the message.

评分：`H40/60`。

| 检查点 | 类型 | 组内权重 | 规则 | 能力 |
| --- | --- | ---: | --- | --- |
| latest_state_reconciled | Auto | 30% | SEV-2、`mitigated_monitoring`、`resolved=false`和最新监控值正确 | DP |
| completed_and_pending_actions | Auto | 30% | 回滚完成，三个待办、负责人和期限完整 | DP+RP |
| evidence_uncertainty_separated | Auto | 25% | 疑似版本原因、支付影响和恢复门槛状态正确编码 | RP |
| structured_delivery | Auto | 15% | JSON schema、220词限制和两个输出正确，输入未修改 | VD |
| handoff_prioritization | Judge | 55% | `JC(4)`：当前状态、已完成、优先待办、负责人和期限 | RP+CN |
| operational_caution | Judge | 45% | `JB(4)`：未解决、原因未确认、支付待对账、恢复门槛未满足 | RP+VD |

实施资料：

- INC-742为SEV-2；回滚于21:26 UTC完成，21:48最新错误率1.3%，基线0.4%，缓存池仍饱和；版本仅为疑似原因。
- `handoff_policy.md`规定错误率连续两个10分钟窗口低于0.8%且支付对账完成后才可标记resolved。
- 三个待办为`watch_error_gate/SRE-NEXT/22:20`、`inspect_cache_pool/CACHE-SRE/22:15`、`reconcile_payments/PAY-ONCALL/22:30`。
- 确定状态为`mitigated_monitoring`且`resolved=false`。4个输入预计小于80 KB。

### 03-009 release_expectation_alignment

Prompt：

> 销售、客户和工程现在对上线时间的理解不一致。相关邮件、工程状态、发布规则和负责人在`/tmp_workspace/account_thread.md`、`/tmp_workspace/engineering_status.json`、`/tmp_workspace/release_policy.md`和`/tmp_workspace/owners.csv`。我明天要回复客户，也需要在内部统一口径。
>
> 请核对哪些日期只是工作目标、哪些发布门槛还没有通过，将结果写入`/tmp_workspace/results/release_alignment.json`，包含承诺状态、此前目标、内部条件性窗口、下一次客户更新时间、阻塞门槛和负责人。再写`customer_update.md`和`internal_alignment.md`。不要把未批准日期写成承诺，不要责怪销售或工程，也不要发送消息或修改输入。

评分：`H40/60`。

| 检查点 | 类型 | 组内权重 | 规则 | 能力 |
| --- | --- | ---: | --- | --- |
| facts_and_gate_state | Auto | 30% | 9月18日工作目标、三个未完成门槛和9月24日条件性窗口正确 | RV |
| commitment_boundary_decision | Auto | 30% | `date_not_committed`及禁止承诺判断正确 | RP+RV |
| actions_owners_dates | Auto | 25% | 三个门槛负责人、期限和下一次客户更新时间完整 | RP |
| structured_delivery | Auto | 15% | JSON schema和三个输出正确，输入未修改 | VD |
| customer_update_quality | Judge | 55% | `JB(3)`：承认此前预期、不承诺新日期、承诺状态更新时间 | CN+RP |
| alignment_note_quality | Judge | 45% | `JU`：中性说明口径差异并形成门槛、责任人与统一说法闭环 | CN+VD |

实施资料：

- 销售曾将2026-09-18称为工作目标，客户将其理解为保证上线日。
- 代码已完成，但安全审查、4倍负载测试和回滚演练尚未全部通过；内部最早条件性窗口为2026-09-24 20:00。
- 发布规则要求三个门槛和发布经理书面批准完成前不得承诺日期；负责人表给出门槛责任人、期限和2026-09-18 17:00前的客户更新时间。
- 确定`commitment_status_code=date_not_committed`。4个输入预计小于100 KB。

### 03-010 vendor_delay_stakeholder_comms

Prompt：

> 供应商刚通知关键硬件会分批延期，10月12日试点、10月16日区域上线和10月23日全面上线都可能受影响。订单、最新供应商更新、上线用量、库存、备选方案和审批规则在`/tmp_workspace/purchase_order.json`、`vendor_updates.jsonl`、`launch_requirements.csv`、`inventory.json`、`contingency_options.csv`和`communication_and_approval_policy.md`。
>
> 请核对时间线、可用数量、QA时间、预算和审批条件，在`/tmp_workspace/results/impact_plan.json`中给出推荐组合、成本、各里程碑状态、所需批准和触发条件。再生成`decision_brief.md`、`vendor_escalation_draft.md`、`internal_update.md`和`customer_update.md`。不要把发货窗口当作到货承诺，不要动用支持库存，不要提前承诺GA，也不要实际发消息、下单或审批。

评分：`H40/60`。

| 检查点 | 类型 | 组内权重 | 规则 | 能力 |
| --- | --- | ---: | --- | --- |
| source_timeline_and_quantities | Auto | 25% | 两批供应商信息、现有可用库存和三个里程碑需求正确 | DP |
| critical_path_impact | Auto | 25% | 缩小试点、条件性区域上线和GA待确认判断正确 | RP+DP |
| contingency_math_and_constraints | Auto | 35% | 推荐组合13,900元、920件、预算和审批条件正确 | RP+DP |
| structured_delivery | Auto | 15% | JSON schema、五个输出和输入完整性正确 | VD |
| decision_brief_quality | Judge | 40% | `JU`：推荐组合、成本、里程碑状态、批准人和取舍可直接决策 | RP+CN |
| stakeholder_tailoring | Judge | 40% | `JA`：供应商、内部和客户文本分别符合信息边界与语气 | CN+RP |
| uncertainty_and_escalation | Judge | 20% | `JB(4)`：发货、到货、QA、GA批准状态分开并有升级触发条件 | RP+VD |

实施资料：

- PO-8841共1,200件，原定10月6日发货、10月9日到货；最新书面信息为首批600件10月10日发货、预计10月13日到货，余下600件只有10月19日至21日发货窗口。
- 10月12日试点需300件，10月16日区域上线累计需800件，10月23日GA累计需1,200件，入库后还需QA。现有240件中120件为不可动的支持库存，另120件可用于缩小试点。
- 备选项为缩小试点至120件、首批600件加急8,400元、备选供应商200件5,500元；组合成本13,900元，低于15,000元预算，10月16日前可用920件，但需CFO批准。
- GA在余下600件到货并完成QA前不得承诺。6个输入预计小于150 KB。

## 04_Search_Retrieval

`04-001`和`04-002`继续保留`invalid`，不计入有效题，也不复用编号。

### 04-003 local_release_note_lookup

Prompt：

> Our Debian build note says pip 23.0 blocked editable installs in an `EXTERNALLY-MANAGED` environment. I copied the official release-note sections for nearby pip releases into `/tmp_workspace/pip_news/NEWS_excerpt.rst`.
>
> Without using the network, find the first release in that file that documents an override. Save `/tmp_workspace/results/lookup.json` with `version,release_date,option,purpose,reference,evidence_file,evidence_quote`. Use the earliest release in the supplied notes that contains the feature, preserve the option spelling and evidence sentence exactly, use the documented purpose wording, and identify the referenced GitHub item. Do not modify the release notes.

评分：`A100`。

| 检查点 | 类型 | 组内权重 | 规则 | 能力 |
| --- | --- | ---: | --- | --- |
| first_matching_release | Auto | 35% | 首个包含该功能的版本为23.0.1，日期为2023-02-17 | RV+RP |
| feature_details | Auto | 25% | 选项、用途和GitHub引用`#11780`正确 | RV+DP |
| evidence_traceable | Auto | 25% | 连续原文可在指定附件中定位 | RV+VD |
| delivery_and_input_integrity | Auto | 15% | JSON字段、证据文件路径和输入完整性正确 | VD |

实施资料：`pip_news/`放入pip 22.3.1、23.0、23.0.1和23.1的固定release note片段及相邻干扰项；正确原文来自pip 23.0.1 `NEWS.rst`。预计小于80 KB。

### 04-004 pipl_article13_verification

Prompt：

> 同事在评审里写：“《个人信息保护法》第十三条规定，处理个人信息只能以个人同意为依据。”请帮我核对这句话。只使用以下两份固定官方文本：
>
> - https://flk.npc.gov.cn/detail?id=ff8081817b6472a3017b656cc2040044&title=中华人民共和国个人信息保护法
> - https://www.gov.cn/xinwen/2021-08/20/content_5632404.htm
>
> 将核对结果保存到`/tmp_workspace/results/pipl_article13.json`，记录法律名称、主席令、通过日期、施行日期、第十三条七项处理依据，以及每一项是否以取得个人同意为前提。再写一份`review_note.md`，直接说明原说法哪里不准确并引用条款和来源。不要保存网页副本，也不要扩展为个案法律意见。

评分：`H70/30`。

| 检查点 | 类型 | 组内权重 | 规则 | 能力 |
| --- | --- | ---: | --- | --- |
| document_identity_and_dates | Auto | 25% | 法律名称、主席令第九十一号、2021-08-20通过、2021-11-01施行 | RV+DP |
| seven_legal_bases | Auto | 35% | 第十三条第一至第七项顺序和核心含义完整 | RV+DP |
| consent_flags | Auto | 25% | 第一项为同意；第二至第七项标记为不以同意为前提 | DP+RV |
| structured_delivery | Auto | 15% | JSON schema、七项数量、两个官方URL和输出文件正确 | VD |
| consent_rule_explanation | Judge | 60% | `JR(2)`：第一项同意依据和第二至第七项法定例外分别对应第十三条 | RV+CN |
| review_note_usability | Judge | 40% | `JU`：结论明确、规范强度准确、无个案法律结论 | CN+VD |

确定答案：法律于2021-08-20通过并公布，主席令第九十一号，2021-11-01施行；第十三条列七项依据，第二至第七项不需取得个人同意。

### 04-005 apple_2023_segment_revenue

Prompt：

> 我们的简报写着“Apple 2023财年大中华区净销售额约占公司总净销售额的18.9%”。请只用SEC这份固定的Apple 2023 Form 10-K核对，不要引用聚合网站：
>
> https://www.sec.gov/Archives/edgar/data/320193/000032019323000106/aapl-20230930.htm
>
> 将`fiscal_year,unit,greater_china_net_sales,total_net_sales,share_percent,formula,accession,source_table`写入`/tmp_workspace/results/apple_sales_check.json`，金额沿用年报的“USD millions”，比例四舍五入到1位小数。再写一段`brief_correction.md`，说明原句是否成立，并区分地理区域净销售额与产品类别。不要保存网页。

评分：`H70/30`。

| 检查点 | 类型 | 组内权重 | 规则 | 能力 |
| --- | --- | ---: | --- | --- |
| filing_identity | Auto | 20% | Apple 2023 Form 10-K和accession `0000320193-23-000106`正确 | RV+VD |
| sales_values | Auto | 30% | 大中华区72,559、总净销售额383,285，单位USD millions | RV+DP |
| share_calculation | Auto | 30% | 公式为72,559除以383,285，结果18.9% | DP+RP |
| structured_delivery | Auto | 20% | JSON字段、类型、指定来源和两个输出正确 | VD |
| table_interpretation | Judge | 55% | `JR(3)`：财年、地理区域、公司总额均对应指定表格 | RV+RP |
| correction_readiness | Judge | 45% | `JU`：简短回答原句是否成立，不混写产品类别或投资判断 | RP+VD |

确定答案：Greater China为72,559百万美元，Total net sales为383,285百万美元，占比18.9308%，按1位小数为18.9%。

### 04-006 rfc_http_obsolescence

Prompt：

> Our internal HTTP guide still cites RFC 7230 and RFC 7231. I need a precise replacement note, not a general web search. Use only these fixed RFC Editor records:
>
> - https://www.rfc-editor.org/info/rfc7230
> - https://www.rfc-editor.org/info/rfc7231
> - https://www.rfc-editor.org/info/rfc9110
> - https://www.rfc-editor.org/info/rfc9112
>
> Create `/tmp_workspace/results/rfc_replacement_map.json` showing what replaces each older RFC, the publication month of each replacement, and whether the replacement covers HTTP semantics or HTTP/1.1 message syntax. Then write `migration_note.md` explaining which new RFC our guide should cite for each scope. Include the fixed URLs and do not save copies of the pages.

评分：`H70/30`。

| 检查点 | 类型 | 组内权重 | 规则 | 能力 |
| --- | --- | ---: | --- | --- |
| source_identity | Auto | 20% | 四个RFC编号和固定URL正确 | RV+VD |
| replacement_map | Auto | 35% | 7230映射到9110和9112；7231映射到9110 | RV+DP |
| scope_and_dates | Auto | 25% | 9110为HTTP语义，9112为HTTP/1.1消息语法，均为2022-06 | RV+DP |
| structured_delivery | Auto | 20% | JSON结构、数组基数和两个输出正确 | VD |
| replacement_reasoning | Judge | 60% | `JR(3)`：两组替代关系及语义/消息语法拆分均有记录依据 | RV+CN |
| migration_note_usability | Judge | 40% | `JU`：明确给维护者可执行的引用替换，不扩大RFC适用范围 | CN+VD |

### 04-007 census_province_change

Prompt：

> 我需要核对广东、浙江、黑龙江在第六次和第七次全国人口普查之间的人口变化。请只使用国家统计局这两份固定公报：
>
> - 2010：https://www.stats.gov.cn/sj/tjgb/rkpcgb/qgrkpcgb/202302/t20230206_1901998.html
> - 2020：https://www.stats.gov.cn/sj/zxfb/202302/t20230203_1901083.html
>
> 生成`/tmp_workspace/results/province_change.csv`，列为`province,population_2010,population_2020,absolute_change,percent_change`，人数使用公报原始整数，百分比按`(2020-2010)/2010*100`计算并保留2位小数。再写`calculation_note.md`说明口径、公式和来源。不要保存网页副本。

评分：`H70/30`。

| 检查点 | 类型 | 组内权重 | 规则 | 能力 |
| --- | --- | ---: | --- | --- |
| official_sources | Auto | 20% | 两次人口普查公报身份和固定URL正确 | RV+VD |
| population_values | Auto | 35% | 三省2010和2020人口整数全部正确 | RV+DP |
| change_calculations | Auto | 30% | 三省增减量、正负号和两位小数百分比正确 | DP+RP |
| structured_delivery | Auto | 15% | CSV列、三行、数值类型和两个输出正确 | VD |
| methodology_and_interpretation | Judge | 100% | `JR(3)`：公报口径、计算公式、三省增减方向分别有依据且无因果推断 | RV+RP |

确定答案：广东104,303,132→126,012,510，`+21,709,378`、`+20.81%`；浙江54,426,891→64,567,588，`+10,140,697`、`+18.63%`；黑龙江38,312,224→31,850,088，`-6,462,136`、`-16.87%`。

### 04-008 procurement_clause_version_lookup

Prompt：

> 采购申请`/tmp_workspace/purchase_request.json`需要补审，我只想知道申请提交当天实际生效的是哪一版条款。版本登记表、旧版制度、修订单、新版制度和适用规则都在`/tmp_workspace/policies/`与`document_register.csv`。
>
> 请按生效日期和替代关系查找适用条款，将结果保存到`/tmp_workspace/results/clause_lookup.json`，字段为`request_id,submission_date,applicable_base_version,applicable_amendment,clause_id,effective_clause_text,required_approvals,excluded_version,exclusion_reason,evidence_paths`。条款原文必须逐字保留；不要根据文件名或发布日期猜测，不要修改输入或联网。

评分：`A100`。

| 检查点 | 类型 | 组内权重 | 规则 | 能力 |
| --- | --- | ---: | --- | --- |
| applicable_document_chain | Auto | 25% | 申请日适用旧版制度及已生效修订单 | RV+RP |
| effective_clause_and_approvals | Auto | 30% | 修订后的条款原文和三项审批要求正确 | RV+DP |
| excluded_version_reason | Auto | 20% | 正确排除已发布但尚未生效的新版制度 | RP+RV |
| evidence_paths | Auto | 10% | 登记表、基础制度、修订单和规则路径完整 | RV+VD |
| structured_delivery | Auto | 15% | JSON字段、类型、普通文件和输入完整性正确 | VD |

实施资料：

- `purchase_request.json`：申请`PR-2026-041`，提交日2026-03-20，金额380,000元，采购数据处理服务。
- `document_register.csv`：`PROC-2025.1`自2025-07-01生效；`PROC-2025.1-A1`自2026-03-15替换第6.3条；`PROC-2026.1`于2026-03-01发布但2026-04-01才生效并替代前两者。
- `policies/`：三份制度文本和`version_rules.md`。修订后的第6.3条要求部门负责人、采购负责人和隐私负责人审批；新版同号条款作为干扰项。
- 所有材料为虚构内部制度，只用于本地版本检索，不要求法律判断。预计小于60 KB。

### 04-009 sse_annual_report_metrics

Prompt：

> 同事从贵州茅台2023年年度报告里摘了几个数，我需要按原表复核。只使用上海证券交易所这份固定PDF：
>
> https://static.sse.com.cn/disclosure/listedinfo/announcement/c/new/2024-04-03/600519_20240403_W0YD.pdf
>
> 将证券代码、报告年度、披露日期、营业总收入、归属于上市公司股东的净利润、利润表中的研发费用，以及`研发费用/营业总收入`写入`/tmp_workspace/results/moutai_metrics.json`。金额单位用元，比例保留2位小数。再写`metric_note.md`，说明这里使用的是利润表“研发费用”，不是“研发投入合计”，并标注对应表名或页码。不要保存PDF副本。

评分：`H70/30`。

| 检查点 | 类型 | 组内权重 | 规则 | 能力 |
| --- | --- | ---: | --- | --- |
| report_identity | Auto | 20% | 600519、2023年年度报告、2024-04-03披露和指定URL | RV+VD |
| reported_metrics | Auto | 35% | 营业总收入、归母净利润和研发费用三项精确到元 | RV+DP |
| ratio_calculation | Auto | 25% | 使用研发费用作分子，比例0.10% | DP+RP |
| structured_delivery | Auto | 20% | JSON数值类型、单位和两个输出文件正确 | VD |
| metric_distinction | Judge | 60% | `JR(3)`：利润表研发费用、研发投入合计、营业总收入三种口径不混用 | RV+RP |
| note_usability | Judge | 40% | `JU`：页码或表名清楚，可直接用于复核记录 | RP+VD |

确定答案：营业总收入150,560,330,316.45元；归母净利润74,734,071,550.75元；研发费用157,371,873.01元；比值0.104524%，按2位小数为0.10%。不得使用研发投入合计621,507,535.87元或0.42%。

### 04-010 node_statfs_release_trace

Prompt：

> I’m documenting how Node.js added `statfs`. Trace the feature from the original stalled pull request through the merged replacement and the first Current and LTS releases. Use only these fixed records:
>
> - https://api.github.com/repos/nodejs/node/pulls/31351
> - https://api.github.com/repos/nodejs/node/pulls/46358
> - https://api.github.com/repos/nodejs/node/commits/f145766011a9b600ff7c4fea043f435f70f6d0bf
> - https://nodejs.org/en/blog/release/v19.6.0
> - https://nodejs.org/en/blog/release/v18.15.0
>
> Save `/tmp_workspace/results/statfs_timeline.csv` with `date,event,identifier,evidence_url`, then write `statfs_trace.md` listing the public APIs and explaining the relationship between the two PRs, merge commit, Current release, and LTS backport. Do not save webpage copies or infer dates from a mutable branch.

评分：`H70/30`。

| 检查点 | 类型 | 组内权重 | 规则 | 能力 |
| --- | --- | ---: | --- | --- |
| source_chain_identity | Auto | 20% | 两个PR、merge commit、两个固定tag changelog完整 | RV+VD |
| pull_request_timeline | Auto | 25% | #31351于2020-01-14创建且停滞关闭；#46358于2023-01-30合并 | RV+DP |
| api_names | Auto | 20% | `fs.statfs()`、`fs.statfsSync()`、`fsPromises.statfs()`完整 | RV+DP |
| release_versions_and_dates | Auto | 25% | v19.6.0/2023-02-02及v18.15.0/2023-03-07正确 | RV+DP |
| structured_delivery | Auto | 10% | CSV列、事件顺序、两个输出文件正确 | VD |
| trace_explanation | Judge | 100% | `JR(4)`：原PR、复活PR、merge commit、两条发布线形成可追溯链 | RV+CN |

确定merge commit为`f145766011a9b600ff7c4fea043f435f70f6d0bf`。

### 04-011 nist_sha1_transition

Prompt：

> A reviewer wrote, “NIST disallows SHA-1 everywhere, so our archive must reject every old SHA-1 signature.” Check that statement against the fixed NIST publications below. Use SP 800-131A Rev. 2 as the primary source; use FIPS 186-5 only for publication and transition context.
>
> - https://csrc.nist.gov/pubs/sp/800/131/a/r2/final
> - https://doi.org/10.6028/NIST.SP.800-131Ar2
> - https://csrc.nist.gov/pubs/fips/186-5/final
>
> Create `/tmp_workspace/results/sha1_use_matrix.csv` with `use_case,nist_status,conditions,primary_source,section_or_table`. Cover generation of digital signatures, verification of existing digital signatures, and non-signature uses where collision resistance is not required. Then write `transition_memo.md` for the archive team, separating what must stop from what may remain for legacy verification. Do not generalize these fixed documents into claims about every product or protocol, and do not save the publications.

评分：`H40/60`。

| 检查点 | 类型 | 组内权重 | 规则 | 能力 |
| --- | --- | ---: | --- | --- |
| publication_identity | Auto | 25% | SP 800-131A Rev.2、DOI、2019-03和FIPS 186-5身份正确 | RV+VD |
| signature_status_matrix | Auto | 35% | 生成状态为Disallowed，既有签名验证为Legacy use | RV+DP |
| non_signature_condition | Auto | 20% | 仅在不要求抗碰撞的非签名用途中说明可接受条件 | RV+RP |
| structured_delivery | Auto | 20% | CSV三类用途、状态词、来源定位和两个输出正确 | VD |
| standards_scope_reasoning | Judge | 40% | `JR(3)`：生成、既有验证、非签名用途分别对应NIST范围 | RV+RP |
| archive_transition_plan | Judge | 35% | `JU`：停止新增SHA-1签名，保留受控的既有验证，并给出迁移和验证动作 | RP+VD |
| uncertainty_and_claim_boundary | Judge | 25% | `JB(3)`：不把Legacy use写成推荐新用法，不把所有SHA-1用途混为一类，不推断产品支持 | RP+VD |

`Legacy use`按SP 800-131A Rev.2解释为只处理已经受保护的信息，例如验证已生成的签名。

### 04-012 personal_pension_policy_timeline

Prompt：

> 我看到有的文章写个人养老金从2022年4月开始，有的写2022年11月，还有的写2024年12月。请只用下面四份中国政府网固定政策原文说明这些日期分别指什么：
>
> - https://www.gov.cn/zhengce/content/2022-04/21/content_5686402.htm
> - https://www.gov.cn/zhengce/zhengceku/2022-11/05/content_5724783.htm
> - https://www.gov.cn/zhengce/zhengceku/2022-11/25/content_5728839.htm
> - https://www.gov.cn/zhengce/zhengceku/202412/content_6992279.htm
>
> 生成`/tmp_workspace/results/pension_timeline.csv`，列为`stage,document_number,document_date,published_or_effective_date,coverage,source_url`；再写`answer.md`，区分制度框架、实施办法、36个城市或地区先行实施、全国实施四个节点，并直接回答“到底从什么时候开始”。不要保存网页副本，也不要使用媒体摘要代替原文。

评分：`H40/60`。

| 检查点 | 类型 | 组内权重 | 规则 | 能力 |
| --- | --- | ---: | --- | --- |
| document_identity | Auto | 20% | 四份政策、文号和固定URL一一对应 | RV+VD |
| milestone_dates | Auto | 35% | 2022-04、2022-10/11、2022-11和2024-12关键日期正确 | RV+DP |
| coverage_and_effect | Auto | 25% | 框架、实施规则、36地先行、全国实施范围正确 | DP+RP |
| structured_delivery | Auto | 20% | CSV四行、列、日期格式和两个输出正确 | VD |
| stage_distinction | Judge | 40% | `JR(4)`：四个日期节点分别对应四份政策及其作用 | RV+RP |
| direct_answer_quality | Judge | 35% | `JU`：说明“开始”取决于所问阶段，并给出先行和全国两个运行节点 | RP+VD |
| date_scope_boundary | Judge | 25% | `JB(3)`：不把政策发布等同全国实施，不扩大36地范围，不遗漏2024-12-15生效 | RP+VD |

确定时间线：

1. 国办发〔2022〕7号：2022-04-08成文、2022-04-21发布，建立制度框架。
2. 人社部发〔2022〕70号：2022-10-26成文，自印发日起施行，规定账户和业务流程。
3. 人社厅函〔2022〕169号：2022-11-17成文，2022-11-25公布并在36个城市或地区先行实施。
4. 人社部发〔2024〕87号：2024-12-10成文，自2024-12-15起全国实施。

## 设计来源与运行来源边界

下表只记录公开用户需求原型。除标记为实时网络的04题外，这些URL不进入运行时Prompt。

| 任务 | design_origin | 与评测题保留的用户目的 |
| --- | --- | --- |
| 03-003 | constructed | 同事临时请假时兼顾关心、边界和最小交接 |
| 03-004 | https://github.com/laurent22/joplin/issues/1468 | 同步后内容异常或疑似丢失时获得安全的第一响应 |
| 03-005 | https://workplace.stackexchange.com/questions/168773/how-to-politely-decline-invitation-to-a-work-party | 礼貌拒绝邀请并维持后续关系 |
| 03-006 | https://github.com/calcom/cal.diy/issues/25491 | 在可用人员中按上限分配多名面试官 |
| 03-007 | https://meta.discourse.org/t/how-does-your-forum-community-best-achieve-civil-discussion-when-things-get-heated/149654 | 对升温讨论采取比例化干预并恢复文明交流 |
| 03-008 | https://github.com/National-Digital-Twin/LISA/issues/479 | 让下一班明确已完成、未完成和待接手事项 |
| 03-009 | constructed | 对齐客户、销售和工程对发布承诺的不同理解 |
| 03-010 | constructed | 供应商延期后核算影响并分别沟通不同利益相关方 |
| 04-003 | https://github.com/pypa/pip/issues/11776；https://github.com/pypa/pip/pull/11780 | 从release notes确认功能首次出现的版本 |
| 04-004 | constructed | 核验对法律条款处理依据的过度概括 |
| 04-005 | https://github.com/HKUDS/LightRAG/issues/338 | 从固定10-K表格准确提取并核算财务数据 |
| 04-006 | https://stackoverflow.com/questions/72760258/does-rfc-9110-effectively-obsolete-rfc-1945 | 判断旧RFC是否被新RFC替代及新旧范围 |
| 04-007 | https://github.com/ClimateInequality/PrjCEC/issues/4 | 查找并比较不同年份的中国人口普查数据 |
| 04-008 | https://law.stackexchange.com/questions/28430/does-a-new-contract-supersede-identical-old-contract | 根据生效和替代条款判断新旧版本谁适用 |
| 04-009 | constructed | 从年度报告区分相近指标并计算指定比率 |
| 04-010 | https://github.com/nodejs/node/pull/31351 | 追踪功能从原始PR到合并和发布的过程 |
| 04-011 | https://security.stackexchange.com/questions/109629/deprecation-of-sha1-code-signing-certificates-on-windows | 核验SHA-1弃用范围和遗留验证边界 |
| 04-012 | https://zhidao.baidu.com/question/186575887963675244.html | 澄清个人养老金“开始时间”的不同政策阶段 |

04类中，004和009为`constructed`；003、005、006、007、008、010、011、012为`public`。总设计矩阵已按此分类，不改变04类`public 8 / constructed 2`配额。

04类实时网络任务为004、005、006、007、009、010、011、012；003和008只使用本地附件。所有运行时URL均写入对应Prompt，不保存网页或本地资料副本。

## 配额复核

| 场景 | Prompt / 附件 / 网络 | L1 / L2 / L3 / L4 | 中文 / English | 新增 public / constructed |
| --- | --- | --- | --- | --- |
| 03 | 3 / 7 / 0 | 3 / 4 / 2 / 1 | 8 / 2 | 5 / 3 |
| 04 | 0 / 2 / 8 | 1 / 3 / 4 / 2 | 6 / 4 | 8 / 2 |

每题有4至7个检查点、覆盖2至4个能力维度；每个检查点只映射1个主能力和至多1个次能力。两类题均只使用现有七个能力维度。
