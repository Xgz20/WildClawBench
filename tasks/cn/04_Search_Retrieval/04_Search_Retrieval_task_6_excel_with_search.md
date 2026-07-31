---
id: 04_Search_Retrieval_task_6_excel_with_search
name: 本地与在线信息的综合检索
category: 04_搜索检索
timeout_seconds: 600
modality: pure-text
difficulty: L3
grading_type: llm_judge
---
## Prompt

请检查 `/tmp_workspace/04_Search_Retrieval_task_6_excel_with_search/files` 中的两个 Excel 文件，并在联网的情况下完成以下任务：

1. 在 NPIAS-2023-2027-Appendix-A.xlsx 的 CA 工作表中，找出 California 的机场里，在 Role (FY23) 为 Regional 且 Svc Lvl (FY23) 为 CS 的机场中，Enplaned (CY21) 最高的那个机场。

2. 回答：在 CY 2022 年，它还需要多少登机人数才能成为一个 primary airport？

将你的结果写入 `/tmp_workspace/results/results.md`。

输出格式：

Target airport: <airport name> (LocID: <code>)

Final answer: <integer>

## Expected Behavior

agent 应完成以下任务：

1. agent 必须首先阅读本地的 Excel 文件来完成任务 1，并在多个约束条件下，从 Excel 数据中识别出关键信息。

2. agent 随后必须结合多个 Excel 文件的信息并进行网络搜索；在整合信息后，完成任务 2。

## Grading Criteria

- [ ] 如果答案正确，则得分。

## Automated Checks

```python
def grade(**kwargs) -> dict:
    """
    04_Search_Retrieval_task_6_excel_with_search

    Args:

    Returns:
        0 or 1
    """
    import os
    import json
    import logging
    from pathlib import Path

    log = logging.getLogger("04_Search_Retrieval_task_6_excel_with_search Grading Start!")
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

        gt_description = "\n".join([
            "Target airport: Jack McNamara Field (LocID: CEC)",
            "Final answer: 1783"
        ])
        judge_prompt = f"""你是一位评分裁判。请你依据标准答案和待评估回答进行打分。

具体要求是：
1. 如果待评估回答中 Target airport 和 Final answer 都和标准答案一致，就返回 score 为 1。
2. 如果待评估回答中 Target airport 和 Final answer 只有一个是正确的，就返回 score 为 0.5。
3. 如果待评估回答中 Target airport 和 Final answer 都是错误的，就返回 score 为 0。

【标准答案】
{gt_description}

【待评估回答】
{pred_description}

请只返回一个 JSON 对象，格式：{{"score": <0-1>, "reason": "<简要理由>"}}"""

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
workspace/04_Search_Retrieval/task_6_excel_with_search
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

