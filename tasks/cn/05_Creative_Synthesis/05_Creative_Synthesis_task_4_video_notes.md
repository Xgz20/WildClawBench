---
id: 05_Creative_Synthesis_task_4_video_notes
name: 讲座视频学习笔记生成
category: 05_创意合成
timeout_seconds: 1200
modality: multimodal
difficulty: L2
grading_type: llm_judge
---
## Prompt

`/tmp_workspace/video.mp4` 有一段关于 LLM 的讲座视频。你能看一遍，帮我整理一份学习笔记吗？我希望以后能靠这份笔记复习，而不用把整段视频再看一遍。

请仔细观看这段视频，产出一份**全面的学习笔记**，概括其内容。

### Output Requirements

- 将笔记保存为 `/tmp_workspace/results/notes.md`
- 格式：Markdown
- 篇幅：不少于 800 词，不超过 3000 词

如果你需要视频理解或多模态能力，可以调用 OpenRouter API（base_url 通过环境变量 `OPENROUTER_BASE_URL` 获取，API key 通过环境变量 `OPENROUTER_API_KEY` 获取）。

## Expected Behavior

agent 应当：

1. 观看/分析视频，理解其完整内容
2. 识别主要主题及其逻辑脉络
3. 提炼关键概念、定义、示例和数字
4. 将所有内容组织成结构良好的 Markdown 笔记
5. 确保完整性——视频中所有主要观点都有所体现

## Grading Criteria

笔记将对照从视频真实内容中提取的 8 个事实检查点进行评分，这些检查点按视频的三个主要部分组织。

### Part 1 — What is an LLM? (Checkpoints 1–2)

- [ ] CP1：将 LLM 定义为一个预测下一个词/token 的数学函数；它输出的是所有可能的下一个词上的概率分布，而非单一确定的答案
- [ ] CP2：聊天机器人的工作方式是在前面拼接系统提示词 + 在后面追加用户消息 + 反复预测下一个词；从概率较低的词中采样会让输出更自然、更具随机性

### Part 2 — How does an LLM predict the next word? (Checkpoints 3–5)

- [ ] CP3：模型行为由参数/权重决定——大模型有数千亿个参数；模型是在海量互联网文本上训练的
- [ ] CP4：预训练：喂入除最后一个词以外的所有词，将预测与真实的最后一个词进行比较；通过反向传播调整参数；参数初始为随机值（乱码），并被迭代式地不断优化
- [ ] CP5：RLHF（基于人类反馈的强化学习）：标注人员标记出无用或有问题的预测；他们的修正会进一步改变模型参数，以对齐人类偏好

### Part 3 — Transformers (Checkpoints 6–8)

- [ ] CP6：在 2017 年之前，模型逐词处理文本；谷歌提出了 transformer，使并行化成为可能
- [ ] CP7：每个词被转换成一个向量/嵌入；注意力机制让这些向量相互交流，并根据上下文细化各自的含义
- [ ] CP8：前馈网络（MLP）提供额外的容量来存储语言模式；模型的行为是参数调优所涌现出的现象，因此难以解释具体的预测

### Structural Quality

- [ ] 笔记是合法的 Markdown，带有清晰的标题
- [ ] 篇幅在 800–3000 词范围内
- [ ] 笔记组织良好、逻辑清晰

## Automated Checks

```python
def grade(**kwargs) -> dict:
    """
    Grade the video lecture notes task by checking factual checkpoints via LLM-as-judge.

    Returns:
        Dict mapping criterion names to scores (0.0 to 1.0)
    """
    import os
    import json
    from pathlib import Path

    grading_model = os.environ.get("JUDGE_MODEL", "openai/gpt-5.4")
    workspace = Path("/tmp_workspace/results")
    notes_path = workspace / "notes.md"

    scores = {}
    zero = {f"cp_{i}": 0.0 for i in range(1, 9)}
    zero.update({"checkpoint_avg": 0.0, "overall_score": 0.0})

    # ========== 1. Pre-checks ==========
    if not notes_path.exists() or notes_path.stat().st_size == 0:
        scores.update(zero)
        return scores

    notes_content = notes_path.read_text(encoding="utf-8")
    word_count = len(notes_content.split())

    # ========== 2. Checkpoint evaluation via LLM-as-judge ==========
    checkpoints = {
        "cp_1": "The notes define an LLM as a mathematical function that predicts the next word/token; it outputs a probability distribution over all possible next words, not a single deterministic answer.",
        "cp_2": "The notes describe how chatbots work by prepending a system prompt + appending the user's message + repeatedly predicting the next word; sampling from less likely words makes output more natural and non-deterministic.",
        "cp_3": "The notes explain that model behavior is determined by parameters/weights, large models have hundreds of billions of them, and models are trained on enormous internet text.",
        "cp_4": "The notes describe pre-training: feed all-but-the-last word, compare prediction with the actual last word; backpropagation adjusts parameters; parameters start random (gibberish) and are iteratively refined.",
        "cp_5": "The notes explain RLHF (Reinforcement Learning from Human Feedback): workers flag unhelpful or problematic predictions, and their corrections further change the model's parameters to align preferences.",
        "cp_6": "The notes mention that before 2017, models processed text one word at a time; Google introduced transformers which enable parallelization.",
        "cp_7": "The notes explain that each word is converted into a vector/embedding; the attention mechanism lets vectors communicate and refine meanings based on context.",
        "cp_8": "The notes mention feed-forward networks (MLPs) providing additional capacity to store language patterns; the model's behavior is an emergent phenomenon from parameter tuning, making it hard to explain specific predictions.",
    }

    cp_scores = {}
    try:
        from openai import OpenAI
        client = OpenAI(api_key=os.environ["OPENROUTER_API_KEY"], base_url=os.environ["OPENROUTER_BASE_URL"])

        checkpoint_list = "\n".join(
            f"- **{key}**: {desc}" for key, desc in checkpoints.items()
        )

        prompt = (
            "You are a STRICT grading assistant. Below are study notes about Large Language Models. "
            "Your job is to verify whether the notes reflect SPECIFIC content from the source video, "
            "not just generic textbook knowledge about LLMs.\n\n"
            "IMPORTANT grading rules:\n"
            "- Each checkpoint contains multiple specific claims. ALL claims must be present for full marks.\n"
            "- Generic/vague statements that happen to overlap with a checkpoint should score 0.3 or below.\n"
            "- If any specific claim within a checkpoint is missing, deduct proportionally.\n"
            "- If information is incorrect or contradicts the checkpoint, score 0.0.\n"
            "- Only give 1.0 if every detail in the checkpoint is clearly and accurately covered.\n\n"
            "=== STUDENT NOTES ===\n"
            f"{notes_content}\n"
            "=== END NOTES ===\n\n"
            "Score each checkpoint from 0.0 to 1.0:\n\n"
            f"{checkpoint_list}\n\n"
            "Also evaluate:\n"
            "- **structure_quality**: Are the notes well-organized with clear headings, "
            "logical flow, and readable formatting? (0.0 to 1.0)\n\n"
            "Respond strictly in JSON format with no other content. Example:\n"
            '{"cp_1": 1.0, "cp_2": 0.5, ..., "cp_8": 0.0, "structure_quality": 0.8}'
        )

        resp = client.chat.completions.create(
            model=grading_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )
        raw = resp.choices[0].message.content.strip()
        raw = raw.strip("`").removeprefix("json").strip()
        cp_scores = json.loads(raw)
    except Exception as e:
        scores["llm_error"] = str(e)

    for key in checkpoints:
        scores[key] = round(float(cp_scores.get(key, 0.0)), 4)
    scores["structure_quality"] = round(float(cp_scores.get("structure_quality", 0.0)), 4)

    # ========== 3. Overall score ==========
    checkpoint_avg = sum(scores[f"cp_{i}"] for i in range(1, 9)) / 8.0
    scores["checkpoint_avg"] = round(checkpoint_avg, 4)

    # Length penalty: discount if outside 800-3000 word range
    if word_count < 800:
        length_penalty = max(0.0, word_count / 800)
    elif word_count > 3000:
        length_penalty = max(0.0, 1.0 - (word_count - 3000) / 3000)
    else:
        length_penalty = 1.0

    scores["overall_score"] = round(
        (0.85 * checkpoint_avg + 0.15 * scores["structure_quality"]) * length_penalty, 4
    )

    return scores
```
## Workspace Path

```
workspace/05_Creative_Synthesis/task_4_video_notes
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
```bash
pip install openai
apt-get update && apt-get install -y ffmpeg
```
