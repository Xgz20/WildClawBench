---
id: 04_Search_Retrieval_task_2_conflicting_handling
name: 本地数据与网络信息的冲突处理
category: 04_搜索检索
timeout_seconds: 900
modality: pure-text
difficulty: L3
grading_type: llm_judge
---
## Prompt

在巴黎奥运会期间，中国的 A 公司向国内的 B 公司出售了一批体育器材，用于 B 公司的出口业务。双方约定 B 公司应在交货后 30 天内支付货款。然而，B 公司收货后一直未付款。

同年 8 月，B 公司通过电子邮件确认其仍欠付货款人民币 50 万元，并承诺尽快支付。

此后，双方进行了多轮催收和协商，但欠款仍未偿还。

同年 9 月，我作为一名律师，准备代表 A 公司提起诉讼以追讨货款。我的问题是：该项债权的诉讼时效是多久？

将你的分析写入 `/tmp_workspace/results/results.md`。

我资料库中的法律材料是本律所整理的办案参考条文。请参考这些文件完成任务。这些法律条文位于以下文件夹：`/tmp_workspace/04_Search_Retrieval_task_2_conflicting_handling/laws`

## Expected Behavior

1. agent 应首先阅读本地存储的法律条文，以确定解决该问题的依据。

2. agent 随后应意识到其中一些条文可能已经过时，并在互联网上进行核实。

3. 最后，agent 需要解决本地信息与网络信息之间的任何冲突，并给出正确答案。

## Grading Criteria

- [ ] 如果答案正确，则得分。

## Automated Checks

```python
def grade(**kwargs) -> dict:
    """
    04_Search_Retrieval_task_2_conflicting_handling

    Args:

    Returns:
        0 or 1
    """
    import os
    import json
    import logging
    from pathlib import Path

    log = logging.getLogger("04_Search_Retrieval_task_2_conflicting_handling Grading Start!")
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

        gt_description = "3 years"
        judge_prompt = f"""你是一位评分裁判。请你依据标准答案和待评估回答进行打分。

具体要求是：
1. 如果待评估回答给出的最后推理答案认为有效期是 3 years（和标准答案一致），score 为 1。
2. 如果待评估回答给出的最后推理答案是其他年份，就返回 score 为 0。

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
workspace/04_Search_Retrieval/task_2_conflicting_handling
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

