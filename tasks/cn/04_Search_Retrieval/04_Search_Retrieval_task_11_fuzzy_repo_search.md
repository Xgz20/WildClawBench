---
id: 04_Search_Retrieval_task_11_fuzzy_repo_search
name: 模糊仓库检索
category: 04_搜索检索
timeout_seconds: 900
modality: pure-text
difficulty: L2
grading_type: llm_judge
---
## Prompt

帮我找到 2023–2024 年间的那个开源项目，它让大语言模型无需专用 GPU 就能在普通的笔记本和台式机上运行。我只依稀记得关于它的几点信息：

- 该项目为了追求极致性能，采用了一种底层系统编程语言（C 或 C++）实现，外部依赖极少。
- 仓库名引用了一种通常与南美洲相关联的动物。
- 该项目最初的作者在社区中还以为一个流行的开源语音识别模型打造了一款类似的轻量级推理工具而闻名。
- 该项目首创了一种自定义的量化文件格式，后来被社区广泛采用。

这个 GitHub 仓库应该有超过 60k 的 star。

将结果保存到 `/tmp_workspace/results/results.md`。

## Expected Behavior

agent 应完成以下任务：

1. 在网络上搜索能够在无 GPU 的消费级硬件上运行 LLM 的开源项目。

2. 找出多个候选项目（如 llama.cpp、Ollama、llamafile、LocalAI 等），并逐一对照给定的线索进行评估。

3. 通过确认以下几点缩小到正确的项目：(a) 它是用 C/C++ 编写的，(b) 名称引用了一种南美洲动物，(c) 作者还打造过一款语音识别推理工具（whisper.cpp），(d) 该项目引入了一种被广泛使用的量化格式（GGUF）。

4. 核实 GitHub star 数量超过 60k。

## Grading Criteria

- [ ] 找到正确的仓库即得分。

## Automated Checks

```python
def grade(**kwargs) -> dict:
    """
    04_Search_Retrieval_task_11_fuzzy_repo_search

    Args:

    Returns:
        0 or 1
    """
    import os
    import json
    import logging
    from pathlib import Path

    log = logging.getLogger("04_Search_Retrieval_task_11_fuzzy_repo_search Grading Start!")
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

        gt_description = "llama.cpp (https://github.com/ggerganov/llama.cpp) by Georgi Gerganov (ggerganov)"
        judge_prompt = f"""你是一位评分裁判。请你依据标准答案和待评估回答进行打分。

具体要求是：
1. 如果待评估回答中找到的项目与标准答案不一致（即不是 llama.cpp），就返回 score 为 0。
2. 如果待评估回答中找到的项目与标准答案一致（即是 llama.cpp，由 ggerganov / Georgi Gerganov 开发），就返回 score 为 1。
3. 请注意：Ollama、llamafile、LocalAI 等项目均不是正确答案。只有 llama.cpp 才是正确答案。

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

    # ---- Fall back when all LLM attempts fail ----
    if not llm_succeeded:
        log.warning("LLM Judge failed all 3 attempts, scoring 0")
        scores["overall_score"] = 0

    log.info("Final score: overall_score=%s",
             scores["overall_score"])

    return scores
```

## Workspace Path

```
workspace/04_Search_Retrieval/task_11_fuzzy_repo_search
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
npm install -g agent-browser
```
