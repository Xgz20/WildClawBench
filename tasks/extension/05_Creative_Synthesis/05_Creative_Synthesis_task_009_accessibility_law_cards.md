---
id: 05_Creative_Synthesis_task_009_accessibility_law_cards
name: 无障碍环境建设法社区科普卡
category: 05_Creative_Synthesis
timeout_seconds: 600
modality: pure-text
attachment_size_limit_mb: 5
difficulty: L3
grading_type: hybrid
grading_weights:
  automated: 0.4
  llm_judge: 0.6
tags:
  - custom
---

# 无障碍环境建设法社区科普卡

## Prompt

我想给社区公众号做6张《无障碍环境建设法》科普卡。只使用中国政府网这份正式文本：

https://www.gov.cn/yaowen/liebiao/202306/content_6888910.htm

6张分别讲设施建设、设施维护、信息交流、公共服务、监督反馈和法律责任。每张包括标题、60～90个中文字符的正文、对应条款号和上面的来源链接。写给普通居民看，不要写成法律论文，也不要把“鼓励”“应当”“可以”“有权”改成同一种强制程度。

请依次使用`### 卡片1｜设施建设`至`### 卡片6｜法律责任`作为标题，每张下面依次写`正文：`、`条款：`和`来源：`。直接回复6张卡片，不要保存网页或添加其他说明。

## Expected Behavior

Agent应只依据指定正式文本生成六张结构完整的卡片，分别准确解释建设标准、维护责任、信息无障碍、公共服务、投诉举报和违法责任。正文应面向居民且保留法律规范强度，条款可定位，指定URL在每张卡中出现，不扩展为个案法律意见。

## Grading Criteria

### Automated group

- [ ] `six_card_structure`：六张卡片、固定标题、字段和正文长度正确 — 25%
- [ ] `citation_shape`：每张均有条款号和指定官方URL — 50%
- [ ] `theme_coverage`：六个指定主题按顺序各出现一次 — 25%

### Judge group

- [ ] `legal_factuality`：六个主题的含义和规范强度忠实于正式文本 — 50%
- [ ] `plain_language_fit`：表达适合普通居民且不写成法律论文 — 25%
- [ ] `card_actionability`：每张信息聚焦、可理解并便于社区传播 — 25%

## Automated Checks

```python
def grade(**kwargs) -> dict:
    import re

    keys = ["six_card_structure", "citation_shape", "theme_coverage"]
    scores = {key: 0.0 for key in keys}

    def final_text(transcript):
        candidates = []
        for entry in transcript or []:
            if not isinstance(entry, dict):
                continue
            message = entry.get("message", entry)
            if not isinstance(message, dict) or message.get("role") != "assistant":
                continue
            content = message.get("content", message.get("text", ""))
            blocks = content if isinstance(content, list) else [content]
            parts = []
            for block in blocks:
                if isinstance(block, str):
                    parts.append(block)
                elif isinstance(block, dict) and block.get("type") in {
                    "text", "output_text", "message", "assistant_text"
                }:
                    value = block.get("text", block.get("content", ""))
                    if isinstance(value, str):
                        parts.append(value)
                    elif isinstance(value, dict) and isinstance(value.get("value"), str):
                        parts.append(value["value"])
            joined = "\n".join(part for part in parts if part.strip()).strip()
            if joined:
                candidates.append(joined)
        return candidates[-1] if candidates else ""

    text = final_text(kwargs.get("transcript", []))
    if not text or "```" in text:
        return {**scores, "overall_score": 0.0}

    themes = ["设施建设", "设施维护", "信息交流", "公共服务", "监督反馈", "法律责任"]
    heading_pattern = re.compile(r"^###\s*卡片([1-6])｜([^\n]+)\s*$", flags=re.M)
    headings = list(heading_pattern.finditer(text))
    cards = []
    for index, match in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        cards.append((int(match.group(1)), match.group(2).strip(), text[match.end():end].strip()))

    fields_ok = []
    lengths_ok = []
    citation_flags = []
    url = "https://www.gov.cn/yaowen/liebiao/202306/content_6888910.htm"
    for number, theme, card in cards:
        body_match = re.search(r"^正文：\s*(.+?)\s*^条款：", card, flags=re.M | re.S)
        article_match = re.search(r"^条款：\s*(第[一二三四五六七八九十百零]+条(?:\s*[、,，]\s*第[一二三四五六七八九十百零]+条)*)\s*$", card, flags=re.M)
        source_match = re.search(r"^来源：\s*(https://\S+)\s*$", card, flags=re.M)
        fields_ok.append(bool(body_match and article_match and source_match))
        body = body_match.group(1).strip() if body_match else ""
        lengths_ok.append(60 <= len(re.findall(r"[\u4e00-\u9fff]", body)) <= 90)
        citation_flags.append(bool(article_match and source_match and source_match.group(1).rstrip("。") == url))

    structure_identity = (
        len(cards) == 6
        and [item[0] for item in cards] == list(range(1, 7))
    )
    scores["six_card_structure"] = round(sum([
        1.0 if structure_identity else 0.0,
        sum(1.0 if flag else 0.0 for flag in fields_ok) / 6 if len(fields_ok) == 6 else 0.0,
        sum(1.0 if flag else 0.0 for flag in lengths_ok) / 6 if len(lengths_ok) == 6 else 0.0,
    ]) / 3, 6)
    scores["citation_shape"] = round(
        sum(1.0 if flag else 0.0 for flag in citation_flags) / 6 if len(citation_flags) == 6 else 0.0,
        6,
    )
    actual_themes = [item[1] for item in cards]
    scores["theme_coverage"] = round(
        sum(1.0 if index < len(actual_themes) and actual_themes[index] == theme else 0.0 for index, theme in enumerate(themes)) / 6,
        6,
    )
    scores["overall_score"] = round(
        0.25 * scores["six_card_structure"]
        + 0.50 * scores["citation_shape"]
        + 0.25 * scores["theme_coverage"],
        6,
    )
    return scores
```

## LLM Judge Rubric

Judge只使用指定中国政府网正式文本和最终六张卡片，不增加整体印象分，不提供个案法律判断。允许不同的准确通俗表达。每项只能使用`1.0 / 0.75 / 0.5 / 0.25 / 0.0`。

### Criterion 1: 法律事实与规范强度 (key: legal_factuality, weight: 0.5)

判据：六张卡是否分别准确说明第十二条设施建设、第二十六条设施维护、第三十二条信息交流、第三十九条公共服务、第六十二条监督反馈和第六十五条法律责任，并保留原文的“应当”“逐步”“鼓励”“有权”及处罚前提。

**Score 1.0**: 六个主题、条款含义和规范强度全部准确；法律责任卡明确先责令限期改正、逾期未改正才适用相应罚款；无虚构义务或处罚。

**Score 0.75**: 六个主题总体准确，仅一处次要概括不够精确，未改变核心义务、权利或责任强度。

**Score 0.5**: 至少三个主题准确，但有一项实质误读、两项重要遗漏，或混淆一处“鼓励”和“应当”。

**Score 0.25**: 少于三个主题准确，多处条款错配或把不同规范强度统一改写，但仍与该法相关。

**Score 0.0**: 核心内容与正式文本冲突、伪造条款或处罚、依赖其他来源，或没有可评价卡片。

### Criterion 2: 居民通俗表达 (key: plain_language_fit, weight: 0.25)

判据：内容是否面向普通社区居民，解释具体、克制，避免法律论文腔，同时不牺牲准确性。

**Score 1.0**: 六张均使用清楚日常语言，必要法律词有自然解释，没有内部术语堆叠、说教或过度简化。

**Score 0.75**: 整体通俗准确，仅一张略正式、句子稍密或有一个未解释术语。

**Score 0.5**: 基本能理解，但多张像条文摘抄或法律摘要，需要多处口语化编辑。

**Score 0.25**: 大部分难懂、论文腔明显，或为了简化而造成多项含义模糊。

**Score 0.0**: 面向错误受众、不可理解，或内容与法律科普无关。

### Criterion 3: 卡片传播可用性 (key: card_actionability, weight: 0.25)

判据：每张是否聚焦一个主题，让居民知道该条款关注什么、可观察什么或可采取何种合规行动，并适合公众号卡片使用。

**Score 1.0**: 六张主题聚焦、信息独立完整、标题与正文一致，给出准确可理解的观察或行动方向，无需实质修改即可发布。

**Score 0.75**: 全部可用，仅一张略泛、信息密度稍高或行动指向不够清楚。

**Score 0.5**: 结构完整但多张主要复述条文，实用解释不足，需要多处编辑。

**Score 0.25**: 多数是提纲、口号或重复内容，无法直接制成卡片。

**Score 0.0**: 没有可用科普卡，或给出违法、不安全的行动建议。

## Workspace Path

```
workspace/extension/05_Creative_Synthesis/task_009_accessibility_law_cards
```

## Skills

```
```

## Env

```
```

## Warmup

```bash
```

## Additional Notes

- 联网直接回复题；运行时只允许指定中国政府网URL，不保存网页副本。
- Auto组内权重为25%、50%、25%，整体占40%。
- Judge组内权重为50%、25%、25%，整体占60%。
