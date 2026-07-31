---
id: 05_Creative_Synthesis_task_3_product_poster
name: 皮质公文包产品海报设计
category: 05_创意合成
timeout_seconds: 900
modality: multimodal
tags:
  - requires-native-multimodal
difficulty: L2
grading_type: hybrid
---
## Prompt

我有一张公文包的产品照片，位于 `/tmp_workspace/briefcase.png`。

请为这件商品设计一张**信息型产品展示图**（1080×1440 像素 PNG）。图片应以简洁、专业的排版清晰呈现产品的核心卖点与特征。

基本信息：

- **品牌**：Thornfield & Co.
- **产品名称**：The Meridian Briefcase
- **广告语**："Carry Your Story"
- **价格**：$279.00（参考价 $379.00）

请仔细观察产品照片，提炼其突出特征（材质、工艺、功能等），并在设计中重点展示。加入一句引导观众进一步了解的话语。

将最终图片保存到 `/tmp_workspace/results/poster.png`。

如果你需要图像理解或多模态生成能力，可以调用 OpenRouter API（base_url 通过环境变量 `OPENROUTER_BASE_URL` 获取，API key 通过环境变量 `OPENROUTER_API_KEY` 获取）。

## Expected Behavior

agent 应当：

1. 查看产品照片，理解产品的视觉风格与特征
2. 从照片中提炼核心卖点（材质、工艺、细节等）
3. 设计一张能重点突出这些特征的海报
4. 包含基本信息（品牌、名称、广告语、价格）以及一句行动号召（CTA）
5. 将最终 PNG 图片保存到指定路径

## Grading Criteria

### File & Dimensions

- [ ] `poster.png` 文件存在且尺寸正确（1080×1440）——尺寸错误会使总分 ×0.5

### LLM-as-Judge (3 dimensions, each 0.0–1.0)

- [ ] **Content Completeness**：基本信息齐全（品牌、名称、广告语、价格、CTA），且产品特征已识别并展示
- [ ] **Feature Highlighting**：海报识别和展示产品突出特征的水平——是否超越了给定信息，从照片中提炼出真实的细节？
- [ ] **Design & Impact**：排版构图、视觉层次、高级感，以及整体的精致度与说服力

## Automated Checks

```python
def grade(**kwargs) -> dict:
    """
    Grade the product poster task on 3 dimensions:
    content completeness, aesthetic quality, design & impact.
    """
    import os
    import json
    import base64
    from pathlib import Path

    grading_model = os.environ.get("JUDGE_MODEL", "openai/gpt-5.4")
    workspace = Path("/tmp_workspace/results")
    scores = {}

    poster_path = workspace / "poster.png"

    scores["poster_exists"] = 1.0 if poster_path.exists() and poster_path.stat().st_size > 0 else 0.0

    zero_scores = {
        "dimensions_correct": 0.0,
        "content_completeness": 0.0,
        "feature_highlighting": 0.0,
        "design_impact": 0.0,
        "overall_score": 0.0,
    }
    llm_zero_scores = {
        "content_completeness": 0.0,
        "feature_highlighting": 0.0,
        "design_impact": 0.0,
        "overall_score": 0.0,
    }

    if scores["poster_exists"] == 0.0:
        scores.update(zero_scores)
        return scores

    try:
        from PIL import Image
        with Image.open(poster_path) as img:
            w, h = img.size
        scores["dimensions_correct"] = 1.0 if (w == 1080 and h == 1440) else 0.0
    except Exception:
        scores["dimensions_correct"] = 0.0

    raw = ""
    try:
        from openai import OpenAI
        client = OpenAI(api_key=os.environ["OPENROUTER_API_KEY"], base_url=os.environ["OPENROUTER_BASE_URL"])

        with open(poster_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode()

        grading_prompt = (
            "You are a senior art director at a top design agency reviewing a product display image "
            "for a leather briefcase. Be EXTREMELY critical — your standards are high.\n\n"
            "The agent was given a product photo and asked to identify the product's standout features "
            "and present them in a polished, professional poster (1080×1440). Only basic info was provided "
            "(brand, name, tagline, price). The agent had to observe the photo and extract real product "
            "details on its own.\n\n"
            "Score the image on exactly 3 dimensions (each 0.0 to 1.0). BE HARSH — most outputs "
            "should score 0.1-0.4 unless they are genuinely impressive.\n\n"
            "1. **content_completeness**: Are the basic elements present and legible?\n"
            "   Required: brand 'Thornfield & Co.', product name 'The Meridian Briefcase', "
            "tagline 'Carry Your Story', price $279, reference price $379, "
            "and an invitation to learn more.\n"
            "   Also check: does the image display product features and characteristics?\n"
            "   Score = fraction of required elements present + bonus for feature richness.\n"
            "   Deduct if any text overlaps, is cut off, or is hard to read.\n\n"
            "2. **feature_highlighting**: How well does the image identify and showcase "
            "the product's standout features?\n"
            "   Consider: Did it go beyond the basic given info and extract real, specific details "
            "from the product photo (e.g. leather grain texture, stitching pattern, buckle style, "
            "hardware finish, compartment layout, strap attachment mechanism)?\n"
            "   Are the features presented with visual creativity (e.g. callout lines pointing to "
            "the product, close-up crops, icons) — NOT just plain text boxes?\n"
            "   - Generic labels like 'Premium Leather' or 'Brass Hardware' without specificity = 0.0-0.2.\n"
            "   - Simple bordered text boxes listing features = 0.1-0.3 max.\n"
            "   - Specific, photo-informed features with strong visual integration = 0.7+.\n\n"
            "3. **design_impact**: Layout, hierarchy, originality, and visual quality.\n"
            "   This is a POSTER, not a web page. Judge it as a graphic design deliverable.\n"
            "   Red flags that indicate LOW scores (0.0-0.2):\n"
            "   - Looks like basic HTML/CSS rendering rather than graphic design\n"
            "   - Elements simply stacked vertically with no creative composition\n"
            "   - Large areas of dead/empty space with no purpose\n"
            "   - Plain rectangular boxes with thin borders for feature callouts\n"
            "   - No typographic sophistication (basic fonts, no weight/size contrast)\n"
            "   - Text overlapping or poorly aligned (e.g. prices crammed together)\n"
            "   - Product photo just dropped in without creative integration\n"
            "   - No color harmony, gradients, textures, or design elements\n"
            "   - Overall looks like a wireframe or first draft, not a finished design\n"
            "   Good scores (0.6+) require:\n"
            "   - Thoughtful composition with intentional whitespace\n"
            "   - Strong typographic hierarchy with varied weights and sizes\n"
            "   - Product photo creatively integrated into the layout\n"
            "   - Polished, premium visual feel suitable for a luxury brand\n"
            "   - Design elements (shapes, lines, color blocks) used purposefully\n\n"
            "Remember: most code-generated posters look like basic HTML templates. "
            "Do NOT give generous scores to template-quality work. A typical code-rendered "
            "poster with stacked elements and bordered boxes should score 0.1-0.2 on design_impact.\n\n"
            "Respond strictly in JSON:\n"
            '{"content_completeness": 0.0, "feature_highlighting": 0.0, "design_impact": 0.0}'
        )

        resp = client.chat.completions.create(
            model=grading_model,
            messages=[{"role": "user", "content": [
                {"type": "text", "text": grading_prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}},
            ]}],
            temperature=0,
        )

        raw = resp.choices[0].message.content.strip()
        required_keys = {"content_completeness", "feature_highlighting", "design_impact"}
        candidates = []
        decoder = json.JSONDecoder()
        for index, char in enumerate(raw):
            if char != "{":
                continue
            try:
                value, _ = decoder.raw_decode(raw[index:])
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict) and required_keys <= set(value):
                candidates.append(value)
        if not candidates:
            raise ValueError("Judge response does not contain the required score JSON object")
        llm_scores = candidates[-1]

        for key in ["content_completeness", "feature_highlighting", "design_impact"]:
            scores[key] = round(min(max(float(llm_scores.get(key, 0.0)), 0.0), 1.0), 4)

    except Exception as e:
        scores.update(llm_zero_scores)
        scores["llm_error"] = str(e)
        if raw:
            scores["llm_raw_excerpt"] = raw[:1000]
        return scores

    raw_score = (
        0.20 * scores["content_completeness"]
        + 0.40 * scores["feature_highlighting"]
        + 0.40 * scores["design_impact"]
    )

    dim_penalty = 1.0 if scores.get("dimensions_correct", 0) == 1.0 else 0.5
    scores["overall_score"] = round(raw_score * dim_penalty, 4)

    return scores
```
## Workspace Path

```
workspace/05_Creative_Synthesis/task_3_product_poster
```
## Skills
```
```
## Env

```
OPENROUTER_API_KEY
OPENROUTER_BASE_URL
JUDGE_MODEL
```
## Warmup
```bash
pip install openai
```
