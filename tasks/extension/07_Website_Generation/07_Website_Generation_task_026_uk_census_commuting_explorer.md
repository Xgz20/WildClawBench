---
id: 07_Website_Generation_task_026_uk_census_commuting_explorer
name: 英国普查通勤方式转移数据浏览
category: 07_Website_Generation
sub_category: 数据分析与决策
task_type: 通勤调查数据浏览页
timeout_seconds: 1200
modality: pure-text
difficulty: L2
grading_type: llm_judge
tags:
  - custom
  - web-site-gen
---

# 英国普查通勤方式转移数据浏览

## Prompt

请在 `/tmp_workspace` 下创建项目。如果启动网站时遇到端口冲突，请自行选择其他可用端口。

题目提供的输入素材已经放在 /tmp_workspace/assets 目录中，请直接使用这些文件，不要用自行编造的数据替代。

 `/tmp_workspace/assets` 目录里有一份学术会议报告的演示稿，讲的是英国用十年一次的人口普查追踪通勤方式变化，以及普查如果取消会怎么样。里面最有价值的是几张交叉表，记录了同一批人十年前后通勤方式怎么变的。我想把它做成一个能让人自己去看数据的网页，而不只是一篇读下来的文章。

内容以原件为准，数字照原样呈现，不要改动，也不要补上原件里没有的数据。

那张十种通勤方式的转移交叉表是重点，格子多、数字密，直接铺成一张表很难看出门道，请用颜色深浅把数值大小区分出来。另外想细看某一种出行方式的去向时，我希望能点开它，单独弹出一层来看那一行的分布，看完能关掉回到表格。原件里还有一张把十类归并成三大类的简表，以及几张关于步行环境的统计表，都请一并放上。

整页内容不短，请让人能在几个部分之间快速跳转。

报告的背景、结论和对普查替代方案的利弊分析也要有，读者得知道这些数字是从哪来的、说明了什么。

视觉上希望像一个正经的数据网页，表格清楚易读。手机上也要能正常看。

这份演示稿以 CC BY 4.0 许可发布，作者是 Jemima Stockton 和 Oli Duke-Williams；其中的统计数据来自英国国家统计局，原件末尾有一段致谢文字，请把出处、许可和这段致谢都保留在页面上。

## Expected Behavior

Agent 应按 Prompt 完成页面内容、交互和视觉要求。

题目素材位于 /tmp_workspace/assets，页面内容必须与素材一致，不得用编造数据替代。

评分由 Playwright 运行时检查（内容与交互类评分点）和基于截图的视觉判分（视觉与布局类评分点）共同完成；每个评分点按“预设状态 → 操作 → 期望结果”独立判定。

## Grading Criteria

本题仅使用 LLM Judge 评分。评分点全部放在 `## LLM Judge Rubric` 中，每个 Criterion 只有 1.0 和 0.0 两档：非视觉类评分点由 Playwright 检查器按 key 给出运行时结果，视觉类评分点由 LLM 依据截图判定。

## Automated Checks

## LLM Judge Rubric

说明：

- 每个 Criterion 都按同一结构书写：`预设状态`、`操作`、`期望结果`。
- `Score 1.0` 表示符合预设状态、操作要求，且结果与期望结果一致。
- `Score 0.0` 表示任一部分不符合。
- 未特别说明时，页面在 1440×900 桌面视口打开；标注 375×812 的评分点在手机视口检查。

### Criterion 1: 查看首屏 (key: c01_information_organization, primary: content_structure, secondary: information_organization, weight: 0.0526)

预设状态：首次打开页面

操作：查看首屏

期望结果：可见报告主题（英格兰和威尔士十年一次的人口普查存废，以及还能不能继续追踪通勤者），两位作者 Jemima Stockton 与 Oli Duke-Williams 姓名完整且没有混入原件之外的名字，并写明所属机构为伦敦大学学院（UCL）。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 2: 查看人口普查的背景说明 (key: c02_detail_display, primary: content_structure, secondary: detail_display, weight: 0.0526)

预设状态：页面已打开背景部分

操作：查看人口普查的背景说明

期望结果：写明英格兰和威尔士首次人口普查是 1801 年、此后每十年一次；2021 年普查耗资 9 亿英镑；作为对照，2023/24 财年英国政府年度赤字为 1210 亿英镑，约相当于 GDP 的 4.4%。三个数字都要与原件一致。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 3: 查看 ONS 纵向研究（LS）的说明 (key: c03_detail_display, primary: content_structure, secondary: detail_display, weight: 0.0526)

预设状态：页面已打开数据来源部分

操作：查看 ONS 纵向研究（LS）的说明

期望结果：说明这是英格兰和威尔士人口 1% 的样本，成员的入选规则是生日落在一年中四个特定日期（4/365 约等于 1%），个人的普查表从 1971 年一直链接到 2011 年，从而可以追踪同一批人随时间的变化。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 4: 核对 1991、2001、2011 三个普查年的样本筛选人数 (key: c04_lists_tables, primary: content_structure, secondary: lists_tables, weight: 0.0526)

预设状态：页面已打开样本筛选部分

操作：核对 1991、2001、2011 三个普查年的样本筛选人数

期望结果：全部 LS 成员为 543,884、540,068、585,895；其中在业者为 236,598、244,173、279,207；同时具有有效通勤方式记录的为 232,638、244,168、279,206。九个数字与原件一致，三个年份分列可辨。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 5: 抽查表中若干格子的数值 (key: c05_lists_tables, primary: content_structure, secondary: lists_tables, weight: 0.0526)

预设状态：页面已显示 2001 至 2011 年十种通勤方式的转移交叉表

操作：抽查表中若干格子的数值

期望结果：样本量标注为 N=132,789；2001 年开车（Car/van driver）的人到 2011 年仍开车的比例为 86.3；2001 年骑自行车的人到 2011 年改为开车的比例为 43.5、仍骑车的为 30.8；2001 年乘地铁的人到 2011 年仍乘地铁的比例为 35.9。数值与原件一致，且行（2001 年方式）与列（2011 年方式）的方向没有弄反。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 6: 查看交叉表格子的呈现方式 (key: c06_data_visualization, primary: content_structure, secondary: data_visualization, weight: 0.0526)

预设状态：页面已显示十种通勤方式的转移交叉表

操作：查看交叉表格子的呈现方式

期望结果：格子按数值大小做了全表统一映射的颜色深浅（或等价的色阶、热力）区分，数值越大颜色越深或越突出：「转向开车（Car/van driver）」整列的底色整体明显深于其余各列，其中开车→开车（86.3）是全表最深的一格。全部格子同一种底色、仅靠数字区分不算。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 7: 核对简表中的数值 (key: c07_lists_tables, primary: content_structure, secondary: lists_tables, weight: 0.0526)

预设状态：页面已打开三大类归并后的转移简表

操作：核对简表中的数值

期望结果：样本量标注为 N=131,803；公共交通出发的一行为 47.5、41.3、11.1（分别转向公共交通、私人机动、主动出行）；私人机动出发的一行中保持私人机动为 88.0；主动出行出发的一行中保持主动出行为 38.7、转向私人机动为 49.6。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 8: 查看步行环境指数（walkability）的定义与分级 (key: c08_detail_display, primary: content_structure, secondary: detail_display, weight: 0.0526)

预设状态：页面已打开步行环境部分

操作：查看步行环境指数（walkability）的定义与分级

期望结果：说明步行环境指数衡量一个地方对步行（及骑行）的支持程度，由居住密度、街道连通性（交叉口密度）和土地利用混合度三部分构成；伦敦的分析单元是 Census Area Statistics ward，共 633 个；分级为 1 分最低、4 分最高。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 9: 查看「转向步行」那组结果（若页面把几组结果做成可切换的 (key: c09_lists_tables, primary: content_structure, secondary: lists_tables, weight: 0.0526)

预设状态：页面已打开步行环境与通勤方式的比值比统计部分

操作：查看「转向步行」那组结果（若页面把几组结果做成可切换的，先切换过去）

期望结果：该组样本量为 N=3,093；步行环境 1 分组为参照组；4 分组的比值比为 3.01，置信区间 1.99-4.53，p 值小于 0.001。若采用切换形式，切过去后不残留上一组的数值；若几组并排铺开，各组同时可见且能分辨归属。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 10: 查看研究结论 (key: c10_detail_display, primary: content_structure, secondary: detail_display, weight: 0.0526)

预设状态：页面已打开结论部分

操作：查看研究结论

期望结果：列出影响通勤方式及其稳定性的六项重要因素：年龄、性别、汽车可获得性、社会经济阶层、居住地稳定性、工作地稳定性；并给出结论——居住地的步行环境可能促进步行通勤，既包括继续步行，也包括转向步行。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 11: 查看以手机运营商 GPS 数据替代普查的利弊分析 (key: c11_detail_display, primary: content_structure, secondary: detail_display, weight: 0.0526)

预设状态：页面已打开普查替代方案部分

操作：查看以手机运营商 GPS 数据替代普查的利弊分析

期望结果：优点写明数据获取成本低于调查、精度更高；缺点写明不具代表性、数据噪声大需要大量处理、个人特征信息被去除、不是纵向数据。优缺点都要有，不能只列一侧。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 12: 查看出处、许可与致谢 (key: c12_detail_display, primary: content_structure, secondary: detail_display, weight: 0.0526)

预设状态：页面已加载完成

操作：查看出处、许可与致谢

期望结果：页面上能读到 CC BY 4.0 许可与作者署名，并保留了原件要求的致谢内容：使用 ONS 纵向研究已获英国国家统计局许可，CeLSIUS 由 ESRC 资助（项目号 ES/V003488/1），且相关统计数据属于英国皇家版权（Crown Copyright）。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 13: 打开「2001 年骑自行车」这一行的去向明细层 (key: c13_popup_overlay, primary: interaction_function, secondary: popup_overlay, weight: 0.0526)

预设状态：页面已显示十种通勤方式的转移交叉表，尚未打开任何明细层

操作：打开「2001 年骑自行车」这一行的去向明细层，看过之后再关闭它

期望结果：明细层打开后覆盖或叠加在页面上并显示该行内容，且提供可见的关闭入口（关闭按钮、遮罩点击或 Esc 任一种即可）；执行关闭后明细层消失，交叉表重新完整可见，页面没有停留在被遮挡的状态。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 14: 在十类明细表与三大类归并表之间切换查看（若页面把两张表并排铺开 (key: c14_lists_tables, primary: content_structure, secondary: lists_tables, weight: 0.0526)

预设状态：转移数据部分已显示其中一张表

操作：在十类明细表与三大类归并表之间切换查看（若页面把两张表并排铺开，则直接查看归并表）

期望结果：两张表的内容确实不同：明细表为十行十列、标注 N=132,789，归并表为三行三列、标注 N=131,803。若采用切换形式，切过去后不残留上一张表的行列；若并排展示，两张表同时可见且能分辨各是哪一张。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 15: 通过页面内的导航跳转到结论部分 (key: c15_page_navigation, primary: interaction_function, secondary: page_navigation, weight: 0.0526)

预设状态：页面停留在顶部

操作：通过页面内的导航跳转到结论部分

期望结果：页面滚动到结论部分，且该部分的标题实际停留在可视区域内、没有被顶部导航条压住或遮挡，能直接读到结论正文的开头。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 16: 从上到下滚动浏览全页 (key: c16_page_layout, primary: visual_layout, secondary: page_layout, weight: 0.0526)

预设状态：在 1440×900 桌面视口打开页面

操作：从上到下滚动浏览全页

期望结果：内容分区呈现，背景、样本筛选、转移数据、步行环境、结论、替代方案各成一块且次序合理；区块之间没有重叠或互相遮挡，十列的交叉表完整可见或在自己的容器内横向滚动，未被页面截断。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 17: 对比交叉表中数值最高的格子与数值最低的格子 (key: c17_component_style, primary: visual_layout, secondary: component_style, weight: 0.0526)

预设状态：在 1440×900 桌面视口打开页面，交叉表已显示

操作：对比交叉表中数值最高的格子与数值最低的格子

期望结果：高值格子与低值格子在底色深浅上有明显区别，且两者格子中的数字在各自底色上都保持清晰可读——不出现深底深字或浅底浅字这类读不清的搭配。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 18: 只看页面外观 (key: c18_component_style, primary: visual_layout, secondary: component_style, weight: 0.0526)

预设状态：在 1440×900 桌面视口打开页面，交叉表已显示，未打开任何明细层

操作：只看页面外观，找出打开某一行去向明细的入口

期望结果：该入口带有可见的可供性标记——按钮外观、下划线、箭头或图标等任一种，使它与周围的纯文本明显不同，仅凭截图就能判断它可以点。整行与普通文字毫无区别、只能靠悬停或读源码才发现可点，不算通过。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 19: 滚动浏览全页 (key: c19_responsive_layout, primary: visual_layout, secondary: responsive_layout, weight: 0.0532)

预设状态：在 375×812 手机视口打开页面（视口 375×812）

操作：滚动浏览全页，查看交叉表并打开一次某一行的去向明细

期望结果：页面没有横向溢出，主内容区块不再左右并排；十列的交叉表在自己的容器内横向滚动查看而不被截断，明细层在窄屏下完整可见且关闭入口仍可点到。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

## Workspace Path

workspace/extension/07_Website_Generation/task_026_uk_census_commuting_explorer

## Skills

## Env

## Warmup
