---
id: 04_Search_Retrieval_task_4_efficient_search
name: 检索效率测试
category: 04_搜索检索
timeout_seconds: 600
modality: pure-text
difficulty: L2
grading_type: llm_judge
---
## Prompt

问题：
`pathlib.Path.walk()` 是从哪个 Python 版本开始被加入标准库的？
请进一步确定：合入它的那个 CPython GitHub Pull Request 编号是多少？
请给出最终答案，并输出一条完整的证据链来证明你的结论。

强制要求：

1. 搜索总次数不得超过 4 次。

2. 答案只能基于可公开搜索到的网页。

3. 答案必须明确说明：
    (1) 执行的搜索总次数；
    (2) 每次搜索所使用的查询词。

4. 必须提供一条完整的证据链。

5. 如果在搜索预算内无法确认答案，则必须终止任务，并明确声明 “Unable to confirm.”。不要猜测。

6. 将你的结果写入 `/tmp_workspace/results/results.md`。

输出格式（请严格遵循以下格式）：
```
Total number of searches: <number>

Search 1: <query>
Finding: <one-sentence summary>

Search 2: <query>
Finding: <one-sentence summary>

...

Final Answer:

First introduced in version: <version>

Corresponding PR: <PR number>

Evidence Chain:

<Evidence 1: page title + key conclusion + URL>

<Evidence 2: page title + key conclusion + URL>

Reasoning:
<Use 3–5 sentences to explain why these pieces of evidence are sufficient to support the final answer>
```

## Expected Behavior

agent 应完成以下任务：

1. 在网上找到对应的 Python 版本。

2. 在网上找到对应的 PR 编号。

3. 使用不超过 4 次搜索。

4. 将详细的搜索过程和最终答案写入一个 Markdown（.md）文件。

## Grading Criteria

- [ ] 找到正确答案得 0.2 分。
- [ ] 如果在 2 次搜索内找到答案，则获得剩余的 0.8 分。
- [ ] 如果用了 3 次搜索，则获得剩余的 0.4 分。
- [ ] 如果用了 4 次搜索，则不获得剩余分数。

## Automated Checks

```python
def grade(**kwargs) -> dict:
    """
    04_Search_Retrieval_task_4_efficient_search

    Args:

    Returns:
        0 - 1
    """
    import os
    import json
    import logging
    from pathlib import Path

    log = logging.getLogger("04_Search_Retrieval_task_4_efficient_search Grading Start!")
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
            "Python Version: 3.12",
            "CPython PR：#92517"
        ])
        judge_prompt = f"""你是一位评分裁判。请你依据标准答案和待评估回答进行打分。

具体要求是：
1. 如果待评估回答中的最终答案和标准答案不一致（Python Version: 3.12，CPython PR：#92517），直接返回 score 为0。
2. 如果待评估回答中的最终答案和标准答案一致（Python Version: 3.12，CPython PR：#92517），获得初始0.2分，并进一步依据2.1-2.3的要求打分：
    2.1. 如果待评估回答中给出的搜索过程使用了2次搜索，则额外获得0.8分，最终返回的 score 为 1。
    2.2. 如果待评估回答中给出的搜索过程使用了3次搜索，则额外获得0.4分，最终返回的 score 为 0.6。
    2.3. 如果待评估回答中给出的搜索过程使用了4次搜索，则额外获得0.0分，最终返回的 score 为 0.2。

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
workspace/04_Search_Retrieval/task_4_efficient_search
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

