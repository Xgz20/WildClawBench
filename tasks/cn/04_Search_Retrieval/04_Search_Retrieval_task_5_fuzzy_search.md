---
id: 04_Search_Retrieval_task_5_fuzzy_search
name: 模糊意图检索
category: 04_搜索检索
timeout_seconds: 900
modality: pure-text
difficulty: L2
grading_type: llm_judge
---
## Prompt

帮我找一下 2025 年的那篇论文，它是较早把类似 DeepSeek-R1 的方法迁移到视觉感知任务上的工作之一。我只记得第一作者姓 Liu，而且他们的 GitHub 仓库应该有超过 2k 的 star。
将结果保存到 `/tmp_workspace/results/results.md`。

## Expected Behavior

agent 应完成以下任务：

1. 找到那段时期内多篇将 DeepSeek-R1 方法迁移到视觉感知任务的论文。

2. 在这些论文中，识别出第一作者姓 Liu 的那一篇。

3. 找到对应的 GitHub 仓库，其 star 数应在 2k 以上。

## Grading Criteria

- [ ] 找到正确的论文即可得分。

## Automated Checks

```python
def grade(**kwargs) -> dict:
    """
    04_Search_Retrieval_task_5_fuzzy_search

    Args:

    Returns:
        0 or 1
    """
    import os
    import json
    import logging
    from pathlib import Path

    log = logging.getLogger("04_Search_Retrieval_task_5_fuzzy_search Grading Start!")
    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")

    description_file = Path("/tmp_workspace/results/results.md")
    scores = {}

    if not description_file.exists():
        log.warning("results.md not found: %s", description_file)
        scores["overall_score"] = 0.0
        return scores

    pred_description = description_file.read_text(encoding="utf-8").strip()
    if not pred_description:
        log.warning("results.md is empty")
        scores["overall_score"] = 0.0
        return scores

    log.info("Content in MD: %s", pred_description[:200])

    llm_succeeded = False
    last_error = None

    try:
        import time
        from openai import OpenAI

        client = OpenAI(
            api_key=os.environ["OPENROUTER_API_KEY"],
            base_url=os.environ["OPENROUTER_BASE_URL"],
        )

        gt_description = "Visual-RFT: Visual Reinforcement Fine-Tuning"
        judge_prompt = f"""你是一位评分裁判。请你依据标准答案和待评估回答进行打分。

具体要求是：
1. 如果待评估回答中找到的论文与标准答案不一致，就返回 score 为 0。
2. 如果待评估回答中找到的论文与标准答案一致，就返回 score 为 1。

【标准答案】
{gt_description}

【待评估回答】
{pred_description}

请只返回一个 JSON 对象，格式：{{"score": <0或1>, "reason": "<简要理由>"}}"""

        max_retries = 3
        for attempt in range(max_retries):
            log.info("LLM Judge request %d/%d...", attempt + 1, max_retries)
            try:
                response = client.chat.completions.create(
                    model=os.environ.get("JUDGE_MODEL", "openai/gpt-5.4"),
                    messages=[{"role": "user", "content": judge_prompt}],
                    temperature=0,
                )

                result_text = response.choices[0].message.content.strip()
                log.info("LLM raw response: %s", result_text[:300])

                if result_text.startswith("```"):
                    result_text = result_text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

                result_json = json.loads(result_text)
                raw_score = float(result_json.get("score", 0))
                scores["overall_score"] = raw_score
                scores["judge_reason"] = result_json.get("reason", "")
                llm_succeeded = True
                log.info("LLM Judge succeeded — score: %s, reason: %s",
                         raw_score, scores["judge_reason"])
                break

            except Exception as e:
                last_error = e
                log.warning("LLM Judge attempt %d failed: %s", attempt + 1, e)
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)

    except Exception as e:
        last_error = e
        log.error("OpenAI client initialization failed: %s", e)

    if not llm_succeeded and last_error:
        scores["judge_error"] = str(last_error)

    # ---- Fall back to keyword matching when all LLM attempts fail ----
    if not llm_succeeded:
        log.warning("LLM Judge failed all 3 attempts, scoring 0")
        scores["overall_score"] = 0

    log.info("Final score: overall_score=%s",
             scores["overall_score"])

    return scores
```
## Workspace Path

```
workspace/04_Search_Retrieval/task_5_fuzzy_search
```
## Skills

```
agent-browser
```

## Env

```
OPENROUTER_API_KEY
OPENROUTER_BASE_URL
JUDGE_MODEL
```

## Warmup

```
command -v agent-browser >/dev/null 2>&1 || npm install -g agent-browser
```

