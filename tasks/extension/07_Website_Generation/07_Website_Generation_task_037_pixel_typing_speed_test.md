---
id: 07_Website_Generation_task_037_pixel_typing_speed_test
name: 像素打字测速
category: 07_Website_Generation
sub_category: 学习与知识
task_type: 打字速度测试
timeout_seconds: 900
modality: pure-text
difficulty: L1
grading_type: llm_judge
tags:
  - custom
  - web-site-gen
---

# 像素打字测速

## Prompt

请在 `/tmp_workspace` 下创建项目。如果启动网站时遇到端口冲突，请自行选择其他可用端口。

题目提供的输入素材已经放在 /tmp_workspace/assets 目录中，请直接使用这些文件，不要用自行编造的数据替代。

我想要一个打字测速的网页，用来练打字。要打的那段文章放在 `/tmp_workspace/assets` 目录里，直接用就行，原文放在上面，下面留出打字的地方。

点开始就计时 60 秒，一边打一边能看到速度和正确率，打错的字要标出来。速度按实际用掉的时间算，停下来发呆它就会往下掉。时间到了自动停下，给我看这一轮的成绩，还能再来一次。

整个页面做成像素游戏那种风格。手机上也要能打。

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

### Criterion 1: 检查整页由哪几部分组成 (key: c01_information_organization, primary: content_structure, secondary: information_organization, weight: 0.1)

预设状态：页面刚打开，这一轮还没有开始

操作：检查整页由哪几部分组成

期望结果：页面上能看到要照着打的原文、一个用来打字的输入区、开始这一轮的入口，以及倒计时、速度和正确率三项指标。开始之前倒计时显示完整的一轮时长（“60”“60s”“01:00”等写法均可），速度和正确率显示的是尚未开始的占位值（0、--、0% 或 100% 均可），不反映任何本轮输入。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 2: 通读页面上给出的原文 (key: c02_detail_display, primary: content_structure, secondary: detail_display, weight: 0.1)

预设状态：页面刚打开

操作：通读页面上给出的原文；原文若放在内部滚动区域里，以页面上的文字为准，不必逐屏滚到底

期望结果：原文分成两段完整呈现，与素材中的文章一致：第一段以“那刘姥姥入了坐，拿起箸来，沉甸甸的不伏手”开头，中间有“这个叉巴子，比我们那里的铁锨还沉”；第二段有“老刘，老刘，食量大如牛：吃个老母猪，不抬头！”，并以“独有凤姐鸳鸯二人掌着，还只管让刘姥姥。”结尾。文字没有被改写、删节，也没有换成别的段落。若原文分段或逐屏推进呈现，以整轮内能读到全文为准。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 3: 先把测试时钟推进 5 秒并查看倒计时 (key: c03_realtime_auto_progress, primary: interaction_function, secondary: realtime_auto_progress, weight: 0.1)

预设状态：页面刚打开，这一轮还没有开始

操作：先把测试时钟推进 5 秒并查看倒计时；再开始这一轮，推进 10 秒后又看一次倒计时

期望结果：开始之前推进时间，倒计时纹丝不动，仍是 60 秒；开始之后同样推进 10 秒，倒计时减少到 50 秒上下，说明计时是从开始那一刻才走的，而且不需要用户做任何操作就会自己往下走。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 4: 先把测试时钟推进 10 秒 (key: c04_realtime_auto_progress, primary: interaction_function, secondary: realtime_auto_progress, weight: 0.1)

预设状态：这一轮已经开始，输入区还是空的

操作：先把测试时钟推进 10 秒，再在输入区打入原文开头的“那刘姥姥入了坐，拿起箸来，沉甸甸的不伏手”，接着把测试时钟推进 2 秒并记下这时的速度和正确率；随后不再输入任何内容，把测试时钟又推进 30 秒，再看一次这两项

期望结果：打完之后速度是一个大于 0 的数值。之后只让时间流逝、不再输入，速度明显下降——同样多的字被摊到更长的时间上；正确率不会因为时间流逝而改变。速度不是一个从头到尾不动的固定数字。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 5: 把测试时钟推进到这一轮满 60 秒 (key: c05_realtime_auto_progress, primary: interaction_function, secondary: realtime_auto_progress, weight: 0.1)

预设状态：这一轮已经开始，并且已经打入了一句话

操作：把测试时钟推进到这一轮满 60 秒

期望结果：时间一到就自动停下，不需要用户再点任何东西：倒计时停在 0 并不再变化，输入区无法继续输入，页面显示这一轮的成绩，其中至少包含速度和正确率，同时给出可以再来一次的入口。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 6: 在输入区打入“那刘姥姥入了座 (key: c06_rule_settlement, primary: interaction_function, secondary: rule_settlement, weight: 0.1)

预设状态：这一轮已经开始，输入区还是空的

操作：在输入区打入“那刘姥姥入了座，拿起筷来，沉甸甸的不伏手”，其中把原文的“坐”打成了“座”、“箸”打成了“筷”；随后把测试时钟推进 2 秒，再看正确率和原文上的标记

期望结果：正确率低于 100%，能看出是拿输入逐字和原文比对算出来的；页面把打错的这两个字明确标了出来，和打对的字在样式上有清楚区别，没有把整句都判成错的。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 7: 点击再来一次 (key: c07_rule_settlement, primary: interaction_function, secondary: rule_settlement, weight: 0.1)

预设状态：这一轮已经结束并显示了成绩

操作：点击再来一次

期望结果：再来一次之后进入可以重新计时的干净状态：输入区已清空，上一轮的速度和正确率不再作为当前轮的读数，要打的原文仍然是同一段文章。倒计时要么回到完整的 60 秒等待再次开始，要么直接从 60 秒开始新一轮的走动，两种都可以；上一轮成绩可以作为历史记录留着，但不能被当成当前轮的状态。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 8: 观察整页的字体、配色和方块边角 (key: c08_visual_style, primary: visual_layout, secondary: visual_style, weight: 0.1)

预设状态：页面已在 1440×900 视口打开

操作：观察整页的字体、配色和方块边角

期望结果：页面是一眼能认出的像素游戏风格：容器、按钮和指标块的边角是直角或极小圆角，没有大圆角，阴影是不带模糊的硬投影或干脆不用阴影；配色是少量高对比的纯色块，不是柔和渐变。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 9: 检查原文区、输入区和三项指标的位置关系 (key: c09_page_layout, primary: visual_layout, secondary: page_layout, weight: 0.1)

预设状态：页面已在 1440×900 视口打开

操作：检查原文区、输入区和三项指标的位置关系

期望结果：原文区在上、打字的输入区在下，两者不重叠也不互相遮挡；速度和正确率与输入区能同时看到，打字时不必来回滚动才能看到自己的速度。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 10: 检查整页是否出现横向滚动 (key: c10_responsive_layout, primary: visual_layout, secondary: responsive_layout, weight: 0.1)

预设状态：浏览器视口已调整为 375×812 并打开首页（视口 375×812）

操作：检查整页是否出现横向滚动，然后在窄屏下开始这一轮，把测试时钟推进 10 秒后打入“那刘姥姥入了坐”，再推进 2 秒查看速度和正确率

期望结果：页面没有横向滚动，没有元素把页面撑破。原文、输入区和三项指标在窄屏下都完整可读，没有被截断或互相重叠；开始入口能正常点击，输入区能正常打字，打完之后速度和正确率照常更新。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

## Workspace Path

workspace/extension/07_Website_Generation/task_037_pixel_typing_speed_test

## Skills

## Env

## Warmup
