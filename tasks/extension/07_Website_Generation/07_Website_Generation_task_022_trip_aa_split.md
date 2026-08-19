---
id: 07_Website_Generation_task_022_trip_aa_split
name: 出行 AA 分账
category: 07_Website_Generation
sub_category: 自然语言页面构建
task_type: 多人费用分摊结算工具
timeout_seconds: 900
modality: pure-text
difficulty: L1
grading_type: llm_judge
tags:
  - custom
  - web-site-gen
---

# 出行 AA 分账

## Prompt

请在 /tmp_workspace 下从空目录创建一个可运行的中文多人费用分摊结算工具网页项目。项目根目录需要提供 package.json，并支持 npm install、npm run build，以及 npm run start -- --host 127.0.0.1 --port 4173 启动网站。页面运行时不要依赖外部图片、字体、接口或其他网络资源；不要接入真实支付或发送真实请求。

上次几个人出去玩，路上的钱都是这个垫一笔那个垫一笔，比如小王给我和小周买了冰淇淋，我给所有人付了酒店钱，想要个页面算清楚最后谁该给谁多少。

## Expected Behavior

Agent 应从空目录生成可运行的前端网站，按 Prompt 完成页面内容、交互和视觉要求；项目应能在本地 npm install、npm run build 并通过 npm run start 启动，且不依赖外部网络资源。

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

### Criterion 1: 检查页面提供的入口和分区 (key: c01_information_organization, primary: content_structure, secondary: information_organization, weight: 0.0909)

预设状态：首页已在 1440×900 视口打开

操作：检查页面提供的入口和分区

期望结果：页面能看出这是给一群人分摊出行花销用的，提供了确定参与的人和录入一笔垫付的入口。录入一笔时至少能指定这笔钱是谁垫的、金额是多少，以及这笔由哪些人分摊。页面另有展示已录入款项和最终结算结果的区域。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 2: 按页面提供的方式把参与的人确定为四位 (key: c02_content_editing, primary: interaction_function, secondary: content_editing, weight: 0.0909)

预设状态：首页已打开，尚未录入任何款项

操作：按页面提供的方式把参与的人确定为四位，分别记作阿明、小林、阿德、晓晓

期望结果：四个人都出现在页面上并被视为本次分账的参与者，后续录入垫付时可以指定其中任意一人作为垫付人，也可以指定他们中的任意几人来分摊某一笔。参与者不多不少正好四位，没有残留的占位成员。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 3: 录入一笔由阿明垫付的酒店费 1200 元 (key: c03_content_editing, primary: interaction_function, secondary: content_editing, weight: 0.0909)

预设状态：参与的人已设为阿明、小林、阿德、晓晓四位，尚未录入任何款项

操作：录入一笔由阿明垫付的酒店费 1200 元，指定这笔由四个人一起分摊

期望结果：这笔款项出现在已录入的款项中，显示的垫付人是阿明、金额是 1200 元，与录入的内容一致。从这条记录上还能看出这笔是由四个人一起分摊的。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 4: 再录入一笔由小林垫付的冰淇淋 60 元 (key: c04_content_editing, primary: interaction_function, secondary: content_editing, weight: 0.0909)

预设状态：参与的人为阿明、小林、阿德、晓晓，已录入阿明垫付、四人分摊的 1200 元酒店费

操作：再录入一笔由小林垫付的冰淇淋 60 元，这一笔只指定阿德和晓晓两个人分摊，阿明和小林都不参与

期望结果：这笔款项出现在列表中，垫付人是小林、金额是 60 元，并且能看出分摊的只有阿德和晓晓两个人，与录入时的选择一致。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 5: 查看每个人各自应摊的金额 (key: c05_rule_settlement, primary: interaction_function, secondary: rule_settlement, weight: 0.0909)

预设状态：参与的人为阿明、小林、阿德、晓晓，已录入两笔：阿明垫付、四人分摊的 1200 元；小林垫付、只由阿德和晓晓分摊的 60 元

操作：查看每个人各自应摊的金额

期望结果：阿明应摊 300 元、小林应摊 300 元，两人都没有被摊到那笔与自己无关的冰淇淋钱；阿德和晓晓各应摊 330 元，即 1200 元的四分之一再加上 60 元的一半。四人应摊之和等于两笔总额 1260 元，每一笔都完整摊出去、没有少算或重复。应摊金额以页面任一处可读出为准，是否单独展示总花销、垫付净额等中间量不作要求。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 6: 查看页面给出的最终转账方案 (key: c06_rule_settlement, primary: interaction_function, secondary: rule_settlement, weight: 0.0909)

预设状态：参与的人为阿明、小林、阿德、晓晓，已录入两笔：阿明垫付、四人分摊的 1200 元；小林垫付、只由阿德和晓晓分摊的 60 元

操作：查看页面给出的最终转账方案，核对每一条转账的付款人、收款人和金额

期望结果：页面明确列出谁该给谁多少钱，按这份方案付完之后四个人的收支全部归零（例如小林付 240 元、阿德和晓晓各付 330 元给阿明，或其它金额等价、同样能让四人归零的方案）。方案里不包含把钱付给自己的条目，也不包含金额为 0 或负数的条目。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 7: 删除小林垫付的那笔 60 元冰淇淋 (key: c07_content_editing, primary: interaction_function, secondary: content_editing, weight: 0.0909)

预设状态：参与的人为阿明、小林、阿德、晓晓，已录入两笔：阿明垫付、四人分摊的 1200 元；小林垫付、只由阿德和晓晓分摊的 60 元，页面已给出结算结果

操作：删除小林垫付的那笔 60 元冰淇淋，然后重新查看总额、各人应摊、各人收支和转账方案

期望结果：该笔款项从列表中消失，阿德和晓晓不再多摊那 30 元；结算结果随之重新计算，变为小林、阿德、晓晓各付 300 元给阿明（或等价的、仍能让四人全部归零的方案）。没有任何一处还停留在删除前的旧数据。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 8: 先在金额留空的情况下提交一次 (key: c08_form_validation, primary: interaction_function, secondary: form_validation, weight: 0.0909)

预设状态：参与的人已设好，页面处于可以录入款项的状态

操作：先在金额留空的情况下提交一次，再填入一个负数金额提交一次

期望结果：两次提交都被拦下，页面给出可见的提示说明问题所在，款项列表中不会多出空白或负数金额的记录，总额和结算结果也不受影响。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 9: 把分摊这笔钱的人全部取消 (key: c09_form_validation, primary: interaction_function, secondary: form_validation, weight: 0.0909)

预设状态：参与的人已设好，页面处于可以录入款项的状态，金额已填好一个正常数值

操作：把分摊这笔钱的人全部取消，一个都不选，然后提交

期望结果：提交被拦下，页面给出可见的提示说明至少要选一个人来分摊，款项列表中不会多出这条无人分摊的记录，总额和结算结果也不受影响。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 10: 检查录入区、款项列表和结算结果三部分的排布 (key: c10_page_layout, primary: visual_layout, secondary: page_layout, weight: 0.0909)

预设状态：参与的人已设好并录入了上述两笔款项，页面在 1440×900 视口打开

操作：检查录入区、款项列表和结算结果三部分的排布

期望结果：录入入口、已录入款项、结算结果三部分各自有可辨认的独立区域；谁该给谁多少这一结论在结算区域直接可见，不需要从明细里自行推算。每笔款项由哪些人分摊也能在列表里看清楚。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 11: 在窄屏下确定参与的人、录入一笔只由其中两人分摊的垫付 (key: c11_responsive_layout, primary: visual_layout, secondary: responsive_layout, weight: 0.091)

预设状态：浏览器视口已调整为 375×812 并打开首页（视口 375×812）

操作：在窄屏下确定参与的人、录入一笔只由其中两人分摊的垫付，并查看款项列表和结算结果

期望结果：页面没有横向滚动，没有任何元素宽度超出视口。录入表单的字段、分摊人选择和按钮都能正常操作，款项列表与结算结果中的姓名和金额完整可读，没有被截断或互相重叠。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

## Workspace Path

workspace/extension/07_Website_Generation/task_022_trip_aa_split

## Skills

## Env

## Warmup
