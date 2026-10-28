# case-spec.json 结构

组装脚本接受一个严格 JSON object。路径相对 `case-spec.json` 所在目录解析；输入也可使用绝对路径。脚本拒绝未知字段、符号链接、目标路径穿越和覆盖。

## 顶层字段

| 字段 | 必需 | 说明 |
|---|---:|---|
| `name` | 是 | 报告展示名 |
| `title` | 否 | Markdown 一级标题，默认等于 `name` |
| `dataset_id` | 否 | catalog登记的系列或版本；省略时使用旧扩展集 |
| `category` | 是 | 所选数据集登记的分类；旧默认仍为六类 |
| `slug` | 是 | 小写 snake_case |
| `number` | 否 | 显式三位编号；通常省略并自动分配最低未占用编号 |
| `timeout_seconds` | 否 | 30~3600，默认 300 |
| `modality` | 否 | `pure-text` 或 `multimodal`，默认 `pure-text` |
| `attachment_size_limit_mb` | 否 | 1~20，默认 5 |
| `difficulty` | 是 | `L1`~`L4` |
| `grading_type` | 是 | `automated`、`llm_judge` 或 `hybrid` |
| `grading_weights` | 条件 | 仅 `hybrid`，`automated` 与 `llm_judge` 为正且和为 1 |
| `tags` | 否 | 默认自动加入 `custom`；禁止 `web-site-gen` 和 `ppt` |
| `prompt` | 是 | 面向被评 Agent 的原始任务，不泄露 gt |
| `expected_behavior` | 是 | 任务作者预期的正确行为 |
| `grading_criteria` | 是 | `automated` 与 `llm_judge` 两个数组，元素为 `key/description` |
| `automated_checks` | 条件 | automated/hybrid 的 Python `grade()` 源码字符串 |
| `llm_judge_rubric` | 条件 | llm_judge/hybrid 的结构化 criterion 数组 |
| `skills`、`env`、`warmup` | 否 | 字符串数组；为空时生成空章节 |
| `additional_notes` | 否 | 供任务作者审核的说明数组 |
| `workspace` | 是 | `exec` 与 `gt` 的复制清单 |
| `source` | 是 | 来源与改编记录 |
| `checkpoint_capabilities` | 是 | 精确覆盖运行时评分 key 的七维能力映射 |
| `judge_evidence` | 否 | `required`数组，各项为`path`及`role: candidate_deliverable`，path必须是`results/`下的相对路径 |
| `scoring_runtime` | 否 | 评分侧boolean `office`、`office_render`、`html_render`、`research_sources`要求；office_render为true须同时声明office为true，HTML可单独启用；生成私有评分契约，不注入被测端Env |

注册数据集的`source`改为以下结构（不能与旧`design_origin/runtime_sources`混填）：

```json
{
  "origin": {"mode": "constructed", "production_refs": []},
  "network": {"mode": "offline"},
  "attributes": {
    "requires_visual_input": false,
    "coding_primary": false,
    "retrieval_group": "local_evidence"
  }
}
```

`origin`可保留蓝图中的去身份来源信息与方法参考；线上原型必须带完整`query_hash`和审核`review`，不得复制原始用户文本。`network.mode`支持`offline/open_public_search/fixed_url_verification/site_scoped_search`，联网题还需在Prompt和来源中固定范围、时点与独立证据契约。`retrieval_group`仅检索类填写`open_search/directed_web_retrieval/local_evidence`，与联网方式一致。`requires_visual_input`必须与`modality`一致，不按办公文件格式推断。`workspace.gt`不能省略或只提供占位文件。编号优先匹配building蓝图中的同slug任务；新增题只加入源池，版本清单需另行显式登记。

## 最小 automated 示例

```json
{
  "name": "本地事实摘要",
  "category": "01_Productivity_Flow",
  "slug": "local_fact_summary",
  "timeout_seconds": 180,
  "difficulty": "L2",
  "grading_type": "automated",
  "prompt": "读取 /tmp_workspace/source.md，将事实摘要写入 /tmp_workspace/results/summary.md。",
  "expected_behavior": "完整提取给定材料中的关键事实，不引入材料外结论。",
  "grading_criteria": {
    "automated": [
      {"key": "summary_exists", "description": "摘要文件存在且非空"}
    ],
    "llm_judge": []
  },
  "automated_checks": "def grade(**kwargs) -> dict:\n    from pathlib import Path\n    root = Path(kwargs.get(\"workspace_path\") or \"/tmp_workspace\")\n    path = root / \"results\" / \"summary.md\"\n    score = float(path.is_file() and bool(path.read_text(encoding=\"utf-8\").strip()))\n    return {\"summary_exists\": score, \"overall_score\": score}\n",
  "llm_judge_rubric": [],
  "skills": [],
  "env": [],
  "warmup": [],
  "workspace": {
    "exec": [{"source": "inputs/source.md", "target": "source.md"}],
    "gt": []
  },
  "source": {
    "design_origin": {
      "type": "constructed",
      "verification_status": "constructed_from_user_query",
      "human_authorship": "user_provided",
      "request_summary": "把本地材料整理成事实摘要。",
      "adaptation_note": "固定输入和交付位置，并增加可判定检查。",
      "references": []
    },
    "runtime_sources": []
  },
  "checkpoint_capabilities": {
    "summary_exists": ["verification_delivery"]
  }
}
```

## Rubric criterion

`llm_judge_rubric` 每项只能包含：

```json
{
  "key": "factual_quality",
  "name": "事实质量",
  "weight": 1.0,
  "description": "摘要是否忠实且可追溯。",
  "levels": [
    {"score": 1.0, "description": "关键事实完整准确，并能回指给定材料。"},
    {"score": 0.5, "description": "存在非关键遗漏，但没有虚构或关键错误。"},
    {"score": 0.0, "description": "关键事实错误、虚构，或没有有效交付。"}
  ]
}
```

`grading_criteria.llm_judge` 的 key 和顺序必须与这里一致。`checkpoint_capabilities` 的合法能力为：`code_generation`、`tool_use`、`data_processing`、`retrieval_verification`、`reasoning_planning`、`content_generation`、`verification_delivery`；每个评分 key 映射 1~2 个不重复能力，且同一 key 不得同时映射 `retrieval_verification` 与 `verification_delivery`。
