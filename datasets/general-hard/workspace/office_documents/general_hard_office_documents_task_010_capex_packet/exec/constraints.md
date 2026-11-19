# 澄川装配中心设备升级项目约束

决策时点为2026-10-27。运营负责人向资本委员会申请两阶段设备升级资金。本题为合成离线材料，不实际下单、报批、付款或发消息。金额币种统一为CNY，保留至分、常规四舍五入。按下列口径作申请，不自行引入可抵扣进项税政策、融资折现或资产折旧。

## C01 资产范围与实施窗口

baseline.xlsx的Assets表给出12台实际替换资产及阶段归属；CL共5台、FAN共7台。每个阶段的同类设备由同一供应商供货，不拆组、不挪动阶段。更新全部规定资产，以两阶段含预备费的总现金需求最小为推荐目标；比较另一项可用报价组合，并解释排除报价或未决条件。只允许三个报价供应商。

| phase | order_date | install_start | install_end | blackout_dates | capex_limit | opex_limit |
| --- | --- | --- | --- | --- | ---: | ---: |
| P1 | 2026-11-02 | 2026-12-07 | 2026-12-22 | 2026-12-14,2026-12-15 | 106000 | 6000 |
| P2 | 2027-02-01 | 2027-03-01 | 2027-03-17 | 2027-03-08,2027-03-09 | 75000 | 5000 |

周六、周日和表中停工日均不可施工。交货准备日=下单日期加报价自然日数；当天及以后可施工。每组按供应商规定台天占用同一共享班组，组间不可并行；一组开始后占用连续的允许施工日，可以跳过周末/停工日，不能将空闲允许施工日插入组内。阶段P2以P1验收完成为前置，申请时仅列条件，不声称验收已经完成。排期逐组给出全部工作日期，不仅写起止。

## C02 报价与承诺边界

只有在该阶段order_date仍有效的报价才能进入本次申请的确定预算。不得把未确认的续价/锁价当成已确认。已过期或在该阶段下单前到期的报价可以做带条件的旁列比较，必须标记不可纳入确定申请，不得默默延长有效期。三份报价均不是订单或采购批准。最终供应商批准、P1验收和P2放行均待确认；未授权任何真实操作。

## C03 资本与费用口径

本题企业没有可抵扣进项税，资本申请按含税现金计量。设备报价A/C先乘1.13，B已含税；均按每设备组的总额四舍五入到0.01元。安装费按组数量乘报价未税单价再乘1.06，同样按组取分。运费已含9%税，按每阶段实际选择的不同供应商各一次计入资本，不再乘1.09。

资本基数=设备含税额+安装含税额+阶段运费。资本预备费=资本基数乘0.05取分，计入资本申请；不是费用预备费，也不能从现金预算剔除。资本申请=资本基数+预备费。

保养未税单价为CL每台600元、FAN每台180元，另计6%税；按各组投运首年全额计入所属阶段费用，不摊月、不重复计。P1另有一次含税培训1500元；P2另有数据迁移1600元未税，另计6%税。培训、迁移、保养均不资本化。总现金=资本申请+费用申请。每阶段分别满足上表资本和费用上限，两阶段总现金不得超过190000元；未使用的阶段额度不能互相抵销。

## C04 收益与未知状态

baseline.xlsx的Energy表为原设备过去12个月全组实测电量126000kWh及电价0.82元/kWh。新设备实测/承诺能耗、年度节约额和投资回收期均未提供。不得把原设备电费当作节约额或填0冒充未知。申请写明运行安全/故障维护等已有依据；收益待新设备测试、可比工况、运行小时及测量口径确认。不得凭空给出节能比例、寿命、残值、ROI或确定回收期。

## C05 原生预算与交接契约

交付budget.xlsx为原生公式工作簿，公式要实际依赖可编辑数量、阶梯门槛/单价、税率及费率。不得仅填静态答案或保留未计算缓存。布置、sheet名、行列顺序可变；下列三张逻辑表可分sheet或分区，使用下列列名，前置标题/说明允许。所有数值为数字类型，未知为真正空白或约定null，不以0代替。每组恰一行，phase汇总恰一行。公式表无真实外链、宏、网络或执行内容。

Lines列：line_id,phase,equipment,vendor,quantity,threshold,unit_low,unit_high,equipment_tax_factor,installation_unit,installation_tax_factor,maintenance_unit,maintenance_tax_factor,crew_days_per_unit,equipment_gross,installation_gross,maintenance_gross,crew_days。line_id固定P1-CL、P1-FAN、P2-CL、P2-FAN。数量变动应触发阶梯判断、各组金额和台天变化；tax_factor为1或1加对应税率，不能对含税价再加税。

PhaseTotals列：phase,equipment_gross,installation_gross,freight_a,freight_b,freight_c,freight_gross,contingency_rate,contingency,capex,maintenance_gross,other_opex,opex,total_cash,capex_limit,opex_limit,capex_headroom,opex_headroom。freight_a/b/c为报价含税原额，仅实际选择的供应商计入freight_gross。other_opex的培训/迁移须显示原始税基和计算依据，可另设可编辑输入。推荐P1/P2分别汇总；不得把其他方案金额混入。

Options列：option_id,p1_cl,p1_fan,p2_cl,p2_fan,p1_capex,p1_opex,p2_capex,p2_opex,total_cash,eligible,reason。至少含推荐及另一项有效组合；可以另列条件报价方案，eligible必须为false并说明具体未决项。比较金额按同一资本/费用/阶梯/运费规则计算，不偷换税基。

application.docx沿用approval.docx的业务章节，写清申请阶段金额、总额、对象、依据、排期、报价取舍、收益未知和放行条件。可合理增删空白/重分页，保留原生正文/表格，不以图片代替。plan.html为可直接打开的自包含离线方案，包含同一推荐阶段预算和施工日历，不依赖外部资源或脚本执行。

assumptions.json为机器可核对的交接账本，不能代替实际三份交付。顶层包括：selected_vendors（按line_id映射A/B/C）；phase_totals（P1/P2，字段capex、opex、total_cash，单位CNY数值）；schedule（每组line_id、work_dates数组、source_refs）；quote_exclusions（phase、vendor、reason、source_refs）；unknowns（new_equipment_kwh、annual_savings、payback_years均null及next_checks文字）；gates（supplier_approval、p1_acceptance、p2_release均pending）；evidence（各阶段预算在实际budget.xlsx、application.docx和plan.html的节点定位及引用的源文件/页/表行，必须可回指真实存在内容）。重复JSON键不可用。

application.docx的阶段预算表和plan.html的可见HTML表至少明确列phase、capex、opex、total_cash，可采用中文表头阶段/资本申请/费用申请/总现金。表中金额用CNY元（可千分位、两位小数）；重复阶段/多方案列必须清楚区分推荐。HTML可用data-plan="recommended"标记推荐表，其他方案独立标为alternative。Word表标题明确为推荐申请预算；不能以隐藏内容、机器元数据或账本替代可见交付。审批模板签字为空，提交状态为待审批。

所有源文件原字节保持不变，新输出只写results；不新建任何真实任务或定时任务。必要中间文件留results或系统临时目录。来源标识使用材料真实文件、sheet/row、PDF页/条款编号，不将其他材料链接充作依据。
