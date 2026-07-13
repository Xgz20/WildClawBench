---
id: 05_Creative_Synthesis_task_5_product_launch_video_to_json
name: 发布会视频转结构化 JSON 与宣传物料
category: 05_创意合成
timeout_seconds: 1200
modality: multimodal
difficulty: L4
grading_type: hybrid
grading_weights:
  automated: 0.6
  llm_judge: 0.4
---
## Prompt

你有一段产品发布会视频，位于 `/tmp_workspace/recording.mp4`。

**无网络访问——所有信息必须完全来自视频。**

请观看视频，识别出发布会上宣布的所有硬件产品，并将结构化数据保存到 `/tmp_workspace/results/products.json`。该文件应包含一个 `products` 数组，其中每一项包含：`product_name`（string）、`category`（"smartphone" | "smartwatch" | "earbuds"）、`chip`（string | null）、`colors`（string 数组 | null）、`battery_life_hours`（int 或 int 数组 | null）、`starting_price_usd`（int | null）。对于视频中未明确展示的任何值，使用 `null`。颜色请使用视频中显示的准确英文名称。

同时在 `/tmp_workspace/results/promotional_post.pdf` 创建一份视觉精美的 5 页 A4 宣传 PDF，配以从视频中提取的产品图片和核心亮点。

只包含硬件产品（不包含软件/服务类发布内容）。

如果你需要视频理解或多模态能力，可以调用 OpenRouter API（base_url 通过环境变量 `OPENROUTER_BASE_URL` 获取，API key 通过环境变量 `OPENROUTER_API_KEY` 获取）。

## Expected Behavior

agent 应当：

1. 分析视频录像（通过抽帧、字幕/音频分析或视觉检视），识别出发布会上宣布的所有硬件产品
2. 从视频内容中提取每款产品客观、可核实的规格参数
3. 产出一份结构良好、严格遵循给定 schema 的 `products.json`
4. 从视频中提取具有代表性的产品图片或关键帧
5. 制作一份视觉精美的 PDF 宣传物料（`promotional_post.pdf`），将图片、产品亮点、规格和价格整合为专业的版式
6. 确保该 PDF 恰好为 5 页，且每页均为 A4 尺寸

agent 可以生成一个中间 HTML 文件并将其转换为 PDF（例如通过 `playwright`、`weasyprint` 或 `wkhtmltopdf`），或直接使用 PDF 库。

agent 不应访问互联网，也不应使用关于产品的先验知识。所有提取的数据都必须来自视频。

## Grading Criteria

- [ ] `products.json` 已创建、能成功解析，且每一项都严格遵循所需的 schema
- [ ] 预测的产品集合与 ground truth 中的硬件产品完全一致，无遗漏、无重复、无虚构产品
- [ ] 所有匹配上的产品，起售价完全正确
- [ ] `promotional_post.pdf` 已创建且包含实质性的视觉内容（> 1 KB）
- [ ] `promotional_post.pdf` 恰好为 5 页，且每页均为 A4 尺寸
- [ ] 宣传物料覆盖了全部（或大部分）8 款 ground-truth 产品（VLM 评估）
- [ ] 物料中的产品图片与其对应的文字描述相符（VLM 评估）
- [ ] 物料中提及的产品规格、价格和名称相较 ground truth 准确无误（VLM 评估）
- [ ] 宣传物料具有良好的视觉美感：专业的版式、字体排印、配色方案和整体设计质量（VLM 评估）

## Automated Checks

```python
def grade(**kwargs) -> dict:
    """
    Grade the product launch promotional post task.

    Uses VLM via OpenRouter as judge for PDF promotional post visual evaluation
    (product completeness, image-text match, text accuracy).
    Only checks GT keys: product_name, category, starting_price_usd.
    """
    from pathlib import Path
    import json
    import os
    import re
    import base64
    import time
    from openai import OpenAI

    ALL_CRITERIA = [
        "products_file_exists",
        "schema_validity",
        "product_count",
        "price_accuracy",
        "post_created",
        "post_page_constraints",
        "post_product_completeness",
        "post_image_text_match",
        "post_text_accuracy",
        "post_visual_aesthetics",
        "overall_score",
    ]

    OPENROUTER_API_KEY = os.environ["OPENROUTER_API_KEY"]
    VLM_MODEL = os.environ.get("JUDGE_MODEL", "openai/gpt-5.4")
    OPENROUTER_BASE_URL = os.environ["OPENROUTER_BASE_URL"]

    # ── LLM helpers ──────────────────────────────────────────────────

    client = OpenAI(api_key=OPENROUTER_API_KEY, base_url=OPENROUTER_BASE_URL)

    def _call_llm(messages, model=None, max_tokens=2048, retries=2):
        if model is None:
            model = VLM_MODEL
        for attempt in range(retries + 1):
            try:
                resp = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=0,
                )
                return resp.choices[0].message.content
            except Exception:
                if attempt < retries:
                    time.sleep(2 ** attempt)
                    continue
                return None

    def _extract_json(text):
        if text is None:
            return None
        m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
        if m:
            text = m.group(1)
        try:
            return json.loads(text.strip())
        except json.JSONDecodeError:
            m2 = re.search(r"\{.*\}", text, re.DOTALL)
            if m2:
                try:
                    return json.loads(m2.group(0))
                except json.JSONDecodeError:
                    pass
            return None

    REQUIRED_KEYS = {"product_name", "category", "starting_price_usd"}
    VALID_CATEGORIES = {"smartphone", "smartwatch", "earbuds"}

    def _is_int_like(value):
        return isinstance(value, int) and not isinstance(value, bool)

    def _validate_product_entry(product):
        if not isinstance(product, dict):
            return False
        if not REQUIRED_KEYS.issubset(set(product.keys())):
            return False
        if not isinstance(product.get("product_name"), str) or not product["product_name"].strip():
            return False
        if product.get("category") not in VALID_CATEGORIES:
            return False
        price = product.get("starting_price_usd")
        if price is not None and not _is_int_like(price):
            return False
        return True

    def _to_number(value):
        if isinstance(value, bool) or value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        return None

    def _check_pdf_page_constraints(pdf_path):
        try:
            import fitz
        except ImportError:
            return 0.0

        a4_sizes = [(595, 842), (842, 595)]
        tolerance = 18

        try:
            doc = fitz.open(str(pdf_path))
            if len(doc) != 5:
                doc.close()
                return 0.0

            for page in doc:
                width = page.rect.width
                height = page.rect.height
                if not any(abs(width - w) <= tolerance and abs(height - h) <= tolerance for w, h in a4_sizes):
                    doc.close()
                    return 0.0
            doc.close()
            return 1.0
        except Exception:
            return 0.0

    # ── PDF VLM judge ────────────────────────────────────────────────

    def _vlm_judge_pdf(pdf_path, ground_truth):
        """Evaluate promotional PDF using VLM with ground-truth rubric."""
        defaults = {
            "post_product_completeness": 0.0,
            "post_image_text_match": 0.0,
            "post_text_accuracy": 0.0,
            "post_visual_aesthetics": 0.0,
        }
        try:
            import fitz
        except ImportError:
            return defaults

        try:
            doc = fitz.open(str(pdf_path))
            images_b64 = []
            for page_num in range(min(len(doc), 5)):
                page = doc[page_num]
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                images_b64.append(base64.b64encode(pix.tobytes("png")).decode())
            doc.close()
        except Exception:
            return defaults

        if not images_b64:
            return defaults

        gt_summary = json.dumps(ground_truth, indent=2, ensure_ascii=False)
        n_products = len(ground_truth)

        content = []
        for b64 in images_b64:
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{b64}"},
            })

        content.append({
            "type": "text",
            "text": (
                "You are evaluating a promotional post PDF for a product launch event.\n\n"
                f"Ground truth product list ({n_products} products):\n{gt_summary}\n\n"
                "Rate each criterion from 0.0 to 1.0:\n\n"
                f"1. product_completeness: What fraction of the {n_products} ground-truth "
                "products are mentioned or visually featured in this post? "
                f"(count / {n_products})\n\n"
                "2. image_text_match: Do the images/visual elements correspond to the "
                "products described in the text? Are product images relevant and "
                "correctly paired with descriptions? 1.0 = perfect match, 0.0 = unrelated.\n\n"
                "3. text_accuracy: Are the product names, specs (chips, colors, prices, "
                "battery life) mentioned in the post accurate compared to the ground truth? "
                "1.0 = all facts correct, lower for errors or hallucinated specs.\n\n"
                "4. visual_aesthetics: Rate the overall visual design quality of this "
                "promotional post. Consider: professional layout and composition, "
                "typography choices, color scheme harmony, visual hierarchy, use of "
                "whitespace, image quality and placement, and whether it looks like a "
                "polished marketing material suitable for social media sharing. "
                "1.0 = stunning professional design, 0.5 = acceptable but plain, "
                "0.0 = ugly or broken layout.\n\n"
                "Return ONLY valid JSON:\n"
                '{"product_completeness": <float>, "image_text_match": <float>, '
                '"text_accuracy": <float>, "visual_aesthetics": <float>}'
            ),
        })

        result = _call_llm([{"role": "user", "content": content}], model=VLM_MODEL, max_tokens=512)
        data = _extract_json(result)
        if data is None:
            return defaults

        return {
            "post_product_completeness": min(1.0, max(0.0, float(data.get("product_completeness", 0)))),
            "post_image_text_match": min(1.0, max(0.0, float(data.get("image_text_match", 0)))),
            "post_text_accuracy": min(1.0, max(0.0, float(data.get("text_accuracy", 0)))),
            "post_visual_aesthetics": min(1.0, max(0.0, float(data.get("visual_aesthetics", 0)))),
        }

    # ── Main grading logic ───────────────────────────────────────────

    gt_dir = Path("/tmp_workspace/gt")
    gt_file = gt_dir / "ground_truth.json"
    if not gt_file.exists():
        return {k: 0.0 for k in ALL_CRITERIA} | {"error": f"ground_truth.json not found: {gt_file}"}
    GROUND_TRUTH = json.loads(gt_file.read_text())["products"]

    scores = {}
    workspace = Path("/tmp_workspace/results")

    products_file = workspace / "products.json"
    if not products_file.exists() or products_file.stat().st_size == 0:
        return {k: 0.0 for k in ALL_CRITERIA}

    try:
        pred_data = json.loads(products_file.read_text())
        pred_products = pred_data.get("products", [])
    except (json.JSONDecodeError, KeyError):
        return {k: 0.0 for k in ALL_CRITERIA}

    scores["products_file_exists"] = 1.0 if pred_products else 0.0
    scores["schema_validity"] = (
        round(sum(1 for product in pred_products if _validate_product_entry(product)) / len(pred_products), 2)
        if pred_products else 0.0
    )

    def _norm(s):
        if not isinstance(s, str):
            return str(s).strip().lower() if s is not None else ""
        return s.strip().lower().replace("-", " ").replace("\u2013", " ").replace("_", " ")

    def _match_product(pred_product, gt_list):
        pred_name = pred_product.get("product_name", "")
        pred_category = pred_product.get("category")
        pred_n = _norm(pred_name)
        best, best_score = None, 0
        for gt in gt_list:
            if pred_category != gt["category"]:
                continue
            gt_n = _norm(gt["product_name"])
            if pred_n == gt_n:
                return gt
            tokens = gt_n.split()
            matched = sum(1 for t in tokens if t in pred_n)
            score = matched / len(tokens) if tokens else 0
            if score > best_score:
                best_score = score
                best = gt
        return best if best_score >= 0.6 else None

    matched = {}
    for pred in pred_products:
        gt = _match_product(pred, GROUND_TRUTH)
        if gt and gt["product_name"] not in matched:
            matched[gt["product_name"]] = (pred, gt)

    matched_count = len(matched)
    pred_count = len(pred_products)
    precision = matched_count / pred_count if pred_count else 0.0
    recall = matched_count / len(GROUND_TRUTH) if GROUND_TRUTH else 0.0
    if precision + recall > 0:
        product_f1 = 2 * precision * recall / (precision + recall)
    else:
        product_f1 = 0.0
    if matched_count == len(GROUND_TRUTH) and pred_count == len(GROUND_TRUTH):
        scores["product_count"] = 1.0
    else:
        scores["product_count"] = round(product_f1, 2)

    # ── Price accuracy ─────────────────────────────────────────────

    price_ok = 0
    price_total = sum(
        1 for gt in GROUND_TRUTH
        if gt.get("starting_price_usd") is not None
    )
    for gt_name, (pred, gt) in matched.items():
        gt_price = gt.get("starting_price_usd")
        if gt_price is None:
            continue
        pred_price_num = _to_number(pred.get("starting_price_usd"))
        gt_price_num = _to_number(gt_price)
        if pred_price_num is not None and gt_price_num is not None and pred_price_num == gt_price_num:
            price_ok += 1
    scores["price_accuracy"] = round(price_ok / price_total, 2) if price_total else 1.0

    # ── PDF evaluation (VLM judge) ───────────────────────────────────

    pdf_file = workspace / "promotional_post.pdf"
    if pdf_file.exists() and pdf_file.stat().st_size > 1_000:
        scores["post_created"] = 1.0
        scores["post_page_constraints"] = _check_pdf_page_constraints(pdf_file)
        vlm_scores = _vlm_judge_pdf(pdf_file, GROUND_TRUTH)
        scores.update(vlm_scores)
    elif pdf_file.exists():
        scores["post_created"] = 0.5
        scores["post_page_constraints"] = 0.0
        scores["post_product_completeness"] = 0.0
        scores["post_image_text_match"] = 0.0
        scores["post_text_accuracy"] = 0.0
        scores["post_visual_aesthetics"] = 0.0
    else:
        scores["post_created"] = 0.0
        scores["post_page_constraints"] = 0.0
        scores["post_product_completeness"] = 0.0
        scores["post_image_text_match"] = 0.0
        scores["post_text_accuracy"] = 0.0
        scores["post_visual_aesthetics"] = 0.0

    # ── Weighted overall score ───────────────────────────────────────

    scored_criteria = [k for k in ALL_CRITERIA if k != "overall_score"]
    scores["overall_score"] = round(
        sum(scores.get(k, 0.0) for k in scored_criteria) / len(scored_criteria), 4
    ) if scored_criteria else 0.0

    return scores
```
## Workspace Path

```
workspace/05_Creative_Synthesis/task_5_product_launch_video_to_json
```
## Skills

```
video-frames
```

## Env

```
OPENROUTER_API_KEY
OPENROUTER_BASE_URL
JUDGE_MODEL
```

## Warmup

```
pip install weasyprint pymupdf requests
apt-get update && apt-get install -y ffmpeg
```
