---
id: 07_Website_Generation_task_007_neon_snake_game
name: 霓虹贪吃蛇
category: 07_Website_Generation
sub_category: 自然语言页面构建
task_type: 双人街机小游戏
timeout_seconds: 1200
modality: pure-text
difficulty: L2
grading_type: llm_judge
tags:
  - custom
  - web-site-gen
---

# 霓虹贪吃蛇

## Prompt

请在 /tmp_workspace 下从空目录创建一个可运行的中文双人街机小游戏网页项目。项目根目录需要提供 package.json，并支持 npm install、npm run build，以及 npm run start -- --host 127.0.0.1 --port 4173 启动网站。页面运行时不要依赖外部图片、字体、接口或其他网络资源；不要接入真实支付或发送真实请求。

我想把“霓虹贪吃蛇”做成一个适合两个人共用一台电脑玩的对战小游戏。打开页面先看到游戏名、简单的胜负规则和两位玩家的操作方式，中间放一个醒目的“开始游戏”按钮。左边玩家用 W、A、S、D 控制，右边玩家用键盘的上下左右键控制。

点击“开始游戏”后，左右并排出现两个棋盘。每个棋盘里各有一条蛇、一个能量果和一个爆炸果，两条蛇同时开始自动前进。两边分别显示玩家名称、按键提示、分数、长度和当前状态，让人一眼就能分清自己该看哪边、用哪套按键。

两套按键只控制各自的蛇，不能互相影响，蛇也不能直接反向掉头。吃到能量果后要加分、变长，并在同一个棋盘的空位置生成新的能量果；爆炸果要和普通能量果明显区分，蛇吃到后会立即炸死出局。任意一方撞到墙、自己的身体或爆炸果后就停在出局状态，另一方继续玩，等两边都结束后再结算。先比较分数，分数相同时由存活更久的一方获胜；如果分数和存活时间都一样，就算平局。

一局结束后，页面明确告诉玩家本局结果、双方得分和存活时间，并提供“再来一局”。页面还要累计两边的胜场和胜率，方便连续玩几局时看谁占上风。重新开局时只重置本局的分数、长度和状态，对战统计继续保留。

视觉上做成深色的霓虹街机风，棋盘网格要清楚，两位玩家用两套明显不同的亮色区分。开始前的准备页要有对战氛围，开始后的两个棋盘在桌面端保持左右对称，比分和操作提示清晰但不要抢过游戏本身。屏幕窄的时候两个棋盘也要完整看得见，不用左右拉。

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

### Criterion 1: 检查准备页的标题、规则、操作说明和主要入口 (key: c01_information_organization, primary: content_structure, secondary: information_organization, weight: 0.0666)

预设状态：首次打开页面，尚未开始游戏

操作：检查准备页的标题、规则、操作说明和主要入口

期望结果：页面显示“霓虹贪吃蛇”的双人对战主题，说明一方出局后另一方继续、最终先比分再比存活时间的规则，并清楚标出左边玩家使用 W、A、S、D，右边玩家使用上下左右键；页面提供醒目的“开始游戏”按钮。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 2: 先确认游戏棋盘尚未显示 (key: c02_information_organization, primary: content_structure, secondary: information_organization, weight: 0.0666)

预设状态：页面停留在尚未开始的准备状态

操作：先确认游戏棋盘尚未显示，再点击“开始游戏”

期望结果：开始前以准备信息为主，没有提前展示正在进行的棋盘；点击后左右出现两个彼此独立的棋盘，分别标明左边玩家和右边玩家，并各自显示按键提示、分数、长度和当前状态；页面还显示双方的胜场和胜率。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 3: 记录两边蛇头位置并等待一小会儿 (key: c03_realtime_auto_progress, primary: interaction_function, secondary: realtime_auto_progress, weight: 0.0666)

预设状态：刚刚点击“开始游戏”，两位玩家均未改变方向

操作：记录两边蛇头位置并等待一小会儿

期望结果：两条蛇都处于进行中状态，并在各自棋盘里同时自动前进；两边初始分数相同、长度相同，每个棋盘各有一个能量果和一个爆炸果。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 4: 按下 W 键 (key: c04_operation_feedback, primary: interaction_function, secondary: operation_feedback, weight: 0.0666)

预设状态：游戏正在进行，两条蛇均朝右移动

操作：按下 W 键，观察下一次移动后两个棋盘的变化

期望结果：左边玩家的蛇转向上方，左侧方向提示同步变化；右边玩家的方向和移动轨迹不受影响。A、S、D 也能分别控制左边玩家向左、向下、向右。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 5: 按下键盘上方向键 (key: c05_operation_feedback, primary: interaction_function, secondary: operation_feedback, weight: 0.0666)

预设状态：重新开始一局，游戏正在进行，两条蛇均朝右移动

操作：按下键盘上方向键，观察下一次移动后两个棋盘的变化

期望结果：右边玩家的蛇转向上方，右侧方向提示同步变化；左边玩家的方向和移动轨迹不受影响。其余三个方向键也能分别控制右边玩家向下、向左、向右。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 6: 立即按下该玩家对应的向左按键并等待下一次移动 (key: c06_rule_settlement, primary: interaction_function, secondary: rule_settlement, weight: 0.0666)

预设状态：任意一位玩家的蛇正在朝右移动

操作：立即按下该玩家对应的向左按键并等待下一次移动

期望结果：这条蛇不会直接反向掉头，也不会因为一次相反方向输入立刻撞到自己的身体；方向提示和实际移动方向保持一致。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 7: 让这条蛇吃到能量果 (key: c07_rule_settlement, primary: interaction_function, secondary: rule_settlement, weight: 0.0666)

预设状态：游戏正在进行，其中一位玩家的蛇即将吃到自己棋盘里的能量果

操作：让这条蛇吃到能量果

期望结果：该玩家的分数增加、蛇身变长，并且新能量果出现在同一棋盘未被占用的位置；另一位玩家的分数、长度和能量果不受这次得分影响。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 8: 控制这条蛇吃到爆炸果 (key: c08_rule_settlement, primary: interaction_function, secondary: rule_settlement, weight: 0.0666)

预设状态：游戏正在进行，其中一位玩家的蛇可以移动到自己棋盘里的爆炸果

操作：控制这条蛇吃到爆炸果

期望结果：爆炸果的外观与普通能量果容易区分；蛇吃到后立即炸死并显示为已出局，分数不会因爆炸果增加，另一位玩家仍然可以继续游戏。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 9: 让其中一条蛇先撞墙 (key: c09_rule_settlement, primary: interaction_function, secondary: rule_settlement, weight: 0.0666)

预设状态：游戏正在进行，两位玩家均未出局

操作：让其中一条蛇先撞墙，同时继续控制另一条蛇移动

期望结果：先碰撞的玩家显示为已出局并停止移动，但本局不会立刻结算；另一位玩家仍可移动和得分，页面提示正在等待另一方结束。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 10: 让仍在游戏中的玩家也结束本局 (key: c10_rule_settlement, primary: interaction_function, secondary: rule_settlement, weight: 0.0666)

预设状态：一位玩家已经出局，另一位玩家的本局分数更高且仍在游戏中

操作：让仍在游戏中的玩家也结束本局

期望结果：两边都结束后才显示结算结果；分数更高的一方获胜，页面展示双方的分数和存活时间，并提供“再来一局”。总局数增加 1，获胜方的胜场增加 1，双方胜率随胜场更新且与胜场方向一致（平局是否计入分母按页面自身口径，两边保持一致）。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 11: 让存活更久的玩家也结束本局 (key: c11_rule_settlement, primary: interaction_function, secondary: rule_settlement, weight: 0.0666)

预设状态：新一局中双方最终分数相同，其中一位玩家比另一位更早出局

操作：让存活更久的玩家也结束本局

期望结果：页面将存活时间更长的玩家判为获胜方，并据此更新双方胜场和胜率；只有分数和存活时间都相同时才显示平局，平局会计入总局数但不会增加任何一方的胜场。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 12: 点击“再来一局” (key: c12_rule_settlement, primary: interaction_function, secondary: rule_settlement, weight: 0.0666)

预设状态：至少完成一局，页面正在显示结算结果和双方累计胜率

操作：点击“再来一局”

期望结果：结算提示消失，左右两个棋盘都重置并开始新一局；双方本局分数归零、蛇身恢复为相同的初始长度、状态重新变为进行中，已经累计的总局数、胜场和胜率继续保留。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 13: 观察页面背景、棋盘、蛇、能量果、爆炸果和双方标识 (key: c13_visual_style, primary: visual_layout, secondary: visual_style, weight: 0.0666)

预设状态：已经点击“开始游戏”，两个棋盘正在显示

操作：观察页面背景、棋盘、蛇、能量果、爆炸果和双方标识

期望结果：整体呈现深色霓虹街机风，棋盘网格清楚，蛇、能量果和爆炸果在深色背景上容易辨认，普通能量果与爆炸果有明显区别；左右玩家使用两套明显不同的亮色，玩家身份和各自棋盘不会混淆。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 14: 检查两个棋盘、比分和操作提示的整体排布 (key: c14_page_layout, primary: visual_layout, secondary: page_layout, weight: 0.0666)

预设状态：页面已在 1440×900 视口打开并开始游戏

操作：检查两个棋盘、比分和操作提示的整体排布

期望结果：两个棋盘在桌面端左右并排且大小接近，双方信息各自贴近对应棋盘，比分和操作提示清楚但不遮挡游戏区域，主要对战内容在当前视口中可见。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 15: 检查准备页的呈现 (key: c15_responsive_layout, primary: visual_layout, secondary: responsive_layout, weight: 0.0676)

预设状态：浏览器视口已调整为 375×812 并打开准备页（视口 375×812）

操作：检查准备页的呈现，点击“开始游戏”，再查看两个棋盘和两边的比分区域

期望结果：页面没有横向滚动，没有元素宽度超出视口。准备页的游戏名、胜负规则和两位玩家的操作说明完整可读，“开始游戏”能正常点击；开始后两个棋盘都完整可见，没有被裁切也没有互相重叠，两边的玩家名称、分数、长度和状态都清楚可读。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

## Workspace Path

workspace/extension/07_Website_Generation/task_007_neon_snake_game

## Skills

## Env

## Warmup
