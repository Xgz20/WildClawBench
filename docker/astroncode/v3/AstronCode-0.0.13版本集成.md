本文汇总 ACode 与 Codex/one-iflytek 两类模型的最小启动配置、可选模型和思考深度，用于评测同学搭建评测框架和容器。

两个 TOML 示例都显式设置了 `model_reasoning_effort = "high"`。如果删除该字段，并且启动命令不使用 `-c` 覆盖，则采用模型目录中列出的默认思考深度。

1. ## ACode/Astron

1. ### 最小启动配置

修改 `~/.acode/config.toml`

与 Astron Code 当前产品配置保持一致所需的最小 TOML：

```Plaintext
model = "xopglm52"
model_provider = "astron-spark"
model_reasoning_effort = "high"

[model_providers.astron-spark]
name = "Astron Spark"
experimental_bearer_token = "<ASTRON_BEARER_TOKEN>"
```

启动：

```Bash
astron-code
```

启动时覆盖模型和思考深度：

```Bash
astron-code \
  -m xopglm52 \
  -c 'model_reasoning_effort="max"'
```

1. ### 可选模型与思考深度

| **`启动参数 -m可选id`****/TOML slug** | **UI 名称**     | **支持的思考深度** | **未覆盖深度时默认** | **上下文****窗口** |
| :------------------------------------ | :-------------- | :----------------- | :------------------- | :----------------- |
| `xminimaxm25`                         | Minimax-M2.5    | `high`             | `high`               | 128,000            |
| `xopkimik26`                          | Kimi-K2.6       | `none, high`       | `high`               | 256,000            |
| `xopglm52`                            | GLM-5.2         | `none, high, max`  | `high`               | 1,000,000          |
| `xsparkx2agent`                       | Spark-X2-Agent  | `none, high`       | `high`               | 262,144            |
| `xopglm51`                            | GLM-5.1         | `none, high, max`  | `high`               | 200,000            |
| `xopdeepseekv4pro`                    | DeepSeek-V4-Pro | `none, high, max`  | `high`               | 1,000,000          |
| `astronclaw-auto`                     | Auto            | `none, high`       | `high`               | 200,000            |
| `xopqwen36v35b`                       | Qwen3.6-35B-A3B | `none, high`       | `high`               | 128,000            |

要点：

- 所有 Astron 模型的目录默认思考深度都是 `high`。
- `xminimaxm25` 只声明支持 `high`，即固定开启思考。
- `xopglm52`、`xopglm51`、`xopdeepseekv4pro` 支持 `none/high/max`。
- 其余可关闭思考的模型支持 `none/high`；不要向未声明 `max` 的模型传入 `max`。

1. ## Codex/one-iflytek

1. ### 最小启动配置

修改 `~/.acode/config.toml`

使用 Codex 模型所需的最小 TOML：

```Plaintext
model = "gpt-5.6-sol"
model_provider = "one-iflytek"
model_reasoning_effort = "high"

[model_providers.one-iflytek]
name = "Codex via iFlytek One"
base_url = "https://one.iflytek.com/api/llm/console/chat/v1"
experimental_bearer_token = "<ONE_IFLYTEK_BEARER_TOKEN>"
wire_api = "responses"
requires_openai_auth = false
stream_idle_timeout_ms = 300000
```

将该配置写入 `~/.acode/config.toml` 后，直接启动：

```Bash
astron-code
```

启动时覆盖模型和思考深度：

```Bash
astron-code \
  -m gpt-5.6-sol \
  -c 'model_reasoning_effort="high"'
```

1. ### 可选模型与思考深度

| **`启动参数 -m可选id`****/TOML slug** | **UI 名称**   | **支持的思考深度**                     | **未覆盖时默认** | **上下文****窗口** |
| :------------------------------------ | :------------ | :------------------------------------- | :--------------- | :----------------- |
| `gpt-5.6-sol`                         | GPT-5.6-Sol   | `low, medium, high, xhigh, max, ultra` | `low`            | 372,000            |
| `gpt-5.6-terra`                       | GPT-5.6-Terra | `low, medium, high, xhigh, max, ultra` | `medium`         | 372,000            |
| `gpt-5.6-luna`                        | GPT-5.6-Luna  | `low, medium, high, xhigh, max`        | `medium`         | 372,000            |
| `gpt-5.5`                             | GPT-5.5       | `low, medium, high, xhigh`             | `medium`         | 272,000            |
| `gpt-5.4`                             | GPT-5.4       | `low, medium, high, xhigh`             | `medium`         | 272,000            |
| `gpt-5.4-mini`                        | GPT-5.4-Mini  | `low, medium, high, xhigh`             | `medium`         | 272,000            |
| `gpt-5.2`                             | GPT-5.2       | `low, medium, high, xhigh`             | `medium`         | 272,000            |

要点：

- `gpt-5.6-sol` 默认 `low`，支持 `low/medium/high/xhigh/max/ultra`。
- `gpt-5.6-terra` 默认 `medium`，支持 `low/medium/high/xhigh/max/ultra`。
- `gpt-5.6-luna` 默认 `medium`，支持到 `max`，不声明 `ultra`。
- `gpt-5.5`、`gpt-5.4`、`gpt-5.4-mini`、`gpt-5.2` 默认 `medium`，支持 `low/medium/high/xhigh`。

1. ## 附录：完整JSON

**如果对上述模型内容仍有疑惑时，可以参考本章，本章内容无需做****配置****，ACode已内置，下列内容仅作参考使用。**

1. ### Codex/one-iflytek 模型目录完整 JSON

> 注意：下方内容是便于阅读的精简快照，已省略 `base_instructions`、`model_messages` 等与模型选择无关的内容，不是完整原始 JSON。该模型目录随 ACode 内核捆绑；在不升级 ACode 大版本内核的情况下不会发生变化。

```JSON
{
  "models": [
    {
      "slug": "gpt-5.6-sol",
      "prefer_websockets": true,
      "support_verbosity": true,
      "default_verbosity": "low",
      "apply_patch_tool_type": "freeform",
      "web_search_tool_type": "text_and_image",
      "input_modalities": [
        "text",
        "image"
      ],
      "supports_image_detail_original": true,
      "truncation_policy": {
        "mode": "tokens",
        "limit": 10000
      },
      "supports_parallel_tool_calls": true,
      "tool_mode": "code_mode_only",
      "multi_agent_version": "v2",
      "use_responses_lite": true,
      "include_skills_usage_instructions": false,
      "auto_review_model_override": null,
      "context_window": 372000,
      "max_context_window": 372000,
      "auto_compact_token_limit": null,
      "comp_hash": "3000",
      "reasoning_summary_format": "experimental",
      "default_reasoning_summary": "none",
      "display_name": "GPT-5.6-Sol",
      "description": "Latest frontier agentic coding model.",
      "default_reasoning_level": "low",
      "supported_reasoning_levels": [
        {
          "effort": "low",
          "description": "Fast responses with lighter reasoning"
        },
        {
          "effort": "medium",
          "description": "Balances speed and reasoning depth for everyday tasks"
        },
        {
          "effort": "high",
          "description": "Greater reasoning depth for complex problems"
        },
        {
          "effort": "xhigh",
          "description": "Extra high reasoning depth for complex problems"
        },
        {
          "effort": "max",
          "description": "Maximum reasoning depth for the hardest problems"
        },
        {
          "effort": "ultra",
          "description": "Maximum reasoning with automatic task delegation"
        }
      ],
      "shell_type": "shell_command",
      "visibility": "list",
      "minimal_client_version": "0.144.0",
      "supported_in_api": true,
      "availability_nux": {
        "message": "Our most capable model yet. GPT-5.6 Sol can tackle complex code changes, dig into research, produce polished documents, and take on your most ambitious work. Sol is highly capable at lower reasoning efforts—try starting lower, then turn it up for harder jobs."
      },
      "upgrade": null,
      "priority": 1,
      "experimental_supported_tools": [],
      "available_in_plans": [
        "business",
        "edu",
        "edu_plus",
        "edu_pro",
        "education",
        "enterprise",
        "enterprise_cbp_automation",
        "enterprise_cbp_usage_based",
        "finserv",
        "free",
        "free_workspace",
        "go",
        "hc",
        "k12",
        "plus",
        "pro",
        "prolite",
        "quorum",
        "sci",
        "self_serve_business_usage_based",
        "team"
      ],
      "supports_search_tool": true,
      "default_service_tier": null,
      "service_tiers": [
        {
          "id": "priority",
          "name": "Fast",
          "description": "1.5x speed, increased usage"
        }
      ],
      "additional_speed_tiers": [
        "fast"
      ],
      "supports_reasoning_summaries": true
    },
    {
      "slug": "gpt-5.6-terra",
      "prefer_websockets": true,
      "support_verbosity": true,
      "default_verbosity": "low",
      "apply_patch_tool_type": "freeform",
      "web_search_tool_type": "text_and_image",
      "input_modalities": [
        "text",
        "image"
      ],
      "supports_image_detail_original": true,
      "truncation_policy": {
        "mode": "tokens",
        "limit": 10000
      },
      "supports_parallel_tool_calls": true,
      "tool_mode": "code_mode_only",
      "multi_agent_version": "v2",
      "use_responses_lite": true,
      "include_skills_usage_instructions": false,
      "auto_review_model_override": null,
      "context_window": 372000,
      "max_context_window": 372000,
      "auto_compact_token_limit": null,
      "comp_hash": "3000",
      "reasoning_summary_format": "experimental",
      "default_reasoning_summary": "none",
      "display_name": "GPT-5.6-Terra",
      "description": "Balanced agentic coding model for everyday work.",
      "default_reasoning_level": "medium",
      "supported_reasoning_levels": [
        {
          "effort": "low",
          "description": "Fast responses with lighter reasoning"
        },
        {
          "effort": "medium",
          "description": "Balances speed and reasoning depth for everyday tasks"
        },
        {
          "effort": "high",
          "description": "Greater reasoning depth for complex problems"
        },
        {
          "effort": "xhigh",
          "description": "Extra high reasoning depth for complex problems"
        },
        {
          "effort": "max",
          "description": "Maximum reasoning depth for the hardest problems"
        },
        {
          "effort": "ultra",
          "description": "Maximum reasoning with automatic task delegation"
        }
      ],
      "shell_type": "shell_command",
      "visibility": "list",
      "minimal_client_version": "0.144.0",
      "supported_in_api": true,
      "availability_nux": null,
      "upgrade": null,
      "priority": 2,
      "experimental_supported_tools": [],
      "available_in_plans": [
        "business",
        "edu",
        "edu_plus",
        "edu_pro",
        "education",
        "enterprise",
        "enterprise_cbp_automation",
        "enterprise_cbp_usage_based",
        "finserv",
        "free",
        "free_workspace",
        "go",
        "hc",
        "k12",
        "plus",
        "pro",
        "prolite",
        "quorum",
        "sci",
        "self_serve_business_usage_based",
        "team"
      ],
      "supports_search_tool": true,
      "default_service_tier": null,
      "service_tiers": [
        {
          "id": "priority",
          "name": "Fast",
          "description": "1.5x speed, increased usage"
        }
      ],
      "additional_speed_tiers": [
        "fast"
      ],
      "supports_reasoning_summaries": true
    },
    {
      "slug": "gpt-5.6-luna",
      "prefer_websockets": true,
      "support_verbosity": true,
      "default_verbosity": "low",
      "apply_patch_tool_type": "freeform",
      "web_search_tool_type": "text_and_image",
      "input_modalities": [
        "text",
        "image"
      ],
      "supports_image_detail_original": true,
      "truncation_policy": {
        "mode": "tokens",
        "limit": 10000
      },
      "supports_parallel_tool_calls": true,
      "tool_mode": "code_mode_only",
      "multi_agent_version": "v1",
      "use_responses_lite": true,
      "include_skills_usage_instructions": false,
      "auto_review_model_override": null,
      "context_window": 372000,
      "max_context_window": 372000,
      "auto_compact_token_limit": null,
      "comp_hash": "3000",
      "reasoning_summary_format": "experimental",
      "default_reasoning_summary": "none",
      "display_name": "GPT-5.6-Luna",
      "description": "Fast and affordable agentic coding model.",
      "default_reasoning_level": "medium",
      "supported_reasoning_levels": [
        {
          "effort": "low",
          "description": "Fast responses with lighter reasoning"
        },
        {
          "effort": "medium",
          "description": "Balances speed and reasoning depth for everyday tasks"
        },
        {
          "effort": "high",
          "description": "Greater reasoning depth for complex problems"
        },
        {
          "effort": "xhigh",
          "description": "Extra high reasoning depth for complex problems"
        },
        {
          "effort": "max",
          "description": "Maximum reasoning depth for the hardest problems"
        }
      ],
      "shell_type": "shell_command",
      "visibility": "list",
      "minimal_client_version": "0.144.0",
      "supported_in_api": true,
      "availability_nux": null,
      "upgrade": null,
      "priority": 3,
      "experimental_supported_tools": [],
      "available_in_plans": [
        "business",
        "edu",
        "edu_plus",
        "edu_pro",
        "education",
        "enterprise",
        "enterprise_cbp_automation",
        "enterprise_cbp_usage_based",
        "finserv",
        "free",
        "free_workspace",
        "go",
        "hc",
        "k12",
        "plus",
        "pro",
        "prolite",
        "quorum",
        "sci",
        "self_serve_business_usage_based",
        "team"
      ],
      "supports_search_tool": true,
      "default_service_tier": null,
      "service_tiers": [
        {
          "id": "priority",
          "name": "Fast",
          "description": "1.5x speed, increased usage"
        }
      ],
      "additional_speed_tiers": [
        "fast"
      ],
      "supports_reasoning_summaries": true
    },
    {
      "slug": "gpt-5.5",
      "prefer_websockets": true,
      "support_verbosity": true,
      "default_verbosity": "low",
      "apply_patch_tool_type": "freeform",
      "web_search_tool_type": "text_and_image",
      "input_modalities": [
        "text",
        "image"
      ],
      "supports_image_detail_original": true,
      "truncation_policy": {
        "mode": "tokens",
        "limit": 10000
      },
      "supports_parallel_tool_calls": true,
      "tool_mode": null,
      "multi_agent_version": null,
      "use_responses_lite": false,
      "include_skills_usage_instructions": true,
      "auto_review_model_override": null,
      "context_window": 272000,
      "max_context_window": 272000,
      "auto_compact_token_limit": null,
      "comp_hash": "2911",
      "reasoning_summary_format": "experimental",
      "default_reasoning_summary": "none",
      "display_name": "GPT-5.5",
      "description": "Frontier model for complex coding, research, and real-world work.",
      "default_reasoning_level": "medium",
      "supported_reasoning_levels": [
        {
          "effort": "low",
          "description": "Fast responses with lighter reasoning"
        },
        {
          "effort": "medium",
          "description": "Balances speed and reasoning depth for everyday tasks"
        },
        {
          "effort": "high",
          "description": "Greater reasoning depth for complex problems"
        },
        {
          "effort": "xhigh",
          "description": "Extra high reasoning depth for complex problems"
        }
      ],
      "shell_type": "shell_command",
      "visibility": "list",
      "minimal_client_version": "0.124.0",
      "supported_in_api": true,
      "availability_nux": {
        "message": "GPT-5.5 is now available in Codex. It's our strongest agentic coding model yet, built to reason through large codebases, check assumptions with tools, and keep going until the work is done.\n\nLearn more: https://openai.com/index/introducing-gpt-5-5/\n\n"
      },
      "upgrade": null,
      "priority": 7,
      "experimental_supported_tools": [],
      "available_in_plans": [
        "business",
        "edu",
        "edu_plus",
        "edu_pro",
        "education",
        "enterprise",
        "enterprise_cbp_automation",
        "enterprise_cbp_usage_based",
        "finserv",
        "free",
        "free_workspace",
        "go",
        "hc",
        "k12",
        "plus",
        "pro",
        "prolite",
        "quorum",
        "sci",
        "self_serve_business_usage_based",
        "team"
      ],
      "supports_search_tool": true,
      "default_service_tier": null,
      "service_tiers": [
        {
          "id": "priority",
          "name": "Fast",
          "description": "1.5x speed, increased usage"
        }
      ],
      "additional_speed_tiers": [
        "fast"
      ],
      "supports_reasoning_summaries": true
    },
    {
      "slug": "gpt-5.4",
      "prefer_websockets": true,
      "support_verbosity": true,
      "default_verbosity": "low",
      "apply_patch_tool_type": "freeform",
      "web_search_tool_type": "text_and_image",
      "input_modalities": [
        "text",
        "image"
      ],
      "supports_image_detail_original": true,
      "truncation_policy": {
        "mode": "tokens",
        "limit": 10000
      },
      "supports_parallel_tool_calls": true,
      "tool_mode": null,
      "multi_agent_version": null,
      "use_responses_lite": false,
      "include_skills_usage_instructions": false,
      "auto_review_model_override": null,
      "context_window": 272000,
      "max_context_window": 1000000,
      "auto_compact_token_limit": null,
      "comp_hash": "2911",
      "reasoning_summary_format": "experimental",
      "default_reasoning_summary": "none",
      "display_name": "GPT-5.4",
      "description": "Strong model for everyday coding.",
      "default_reasoning_level": "medium",
      "supported_reasoning_levels": [
        {
          "effort": "low",
          "description": "Fast responses with lighter reasoning"
        },
        {
          "effort": "medium",
          "description": "Balances speed and reasoning depth for everyday tasks"
        },
        {
          "effort": "high",
          "description": "Greater reasoning depth for complex problems"
        },
        {
          "effort": "xhigh",
          "description": "Extra high reasoning depth for complex problems"
        }
      ],
      "shell_type": "shell_command",
      "visibility": "list",
      "minimal_client_version": "0.98.0",
      "supported_in_api": true,
      "availability_nux": null,
      "upgrade": null,
      "priority": 16,
      "experimental_supported_tools": [],
      "available_in_plans": [
        "business",
        "edu",
        "edu_plus",
        "edu_pro",
        "education",
        "enterprise",
        "enterprise_cbp_automation",
        "enterprise_cbp_usage_based",
        "finserv",
        "go",
        "hc",
        "plus",
        "pro",
        "prolite",
        "quorum",
        "sci",
        "self_serve_business_usage_based",
        "team"
      ],
      "supports_search_tool": true,
      "default_service_tier": null,
      "service_tiers": [
        {
          "id": "priority",
          "name": "Fast",
          "description": "1.5x speed, increased usage"
        }
      ],
      "additional_speed_tiers": [
        "fast"
      ],
      "supports_reasoning_summaries": true
    },
    {
      "slug": "gpt-5.4-mini",
      "prefer_websockets": true,
      "support_verbosity": true,
      "default_verbosity": "medium",
      "apply_patch_tool_type": "freeform",
      "web_search_tool_type": "text_and_image",
      "input_modalities": [
        "text",
        "image"
      ],
      "supports_image_detail_original": true,
      "truncation_policy": {
        "mode": "tokens",
        "limit": 10000
      },
      "supports_parallel_tool_calls": true,
      "tool_mode": null,
      "multi_agent_version": null,
      "use_responses_lite": false,
      "include_skills_usage_instructions": false,
      "auto_review_model_override": null,
      "context_window": 272000,
      "max_context_window": 272000,
      "auto_compact_token_limit": null,
      "comp_hash": "2911",
      "reasoning_summary_format": "experimental",
      "default_reasoning_summary": "none",
      "display_name": "GPT-5.4-Mini",
      "description": "Small, fast, and cost-efficient model for simpler coding tasks.",
      "default_reasoning_level": "medium",
      "supported_reasoning_levels": [
        {
          "effort": "low",
          "description": "Fast responses with lighter reasoning"
        },
        {
          "effort": "medium",
          "description": "Balances speed and reasoning depth for everyday tasks"
        },
        {
          "effort": "high",
          "description": "Greater reasoning depth for complex problems"
        },
        {
          "effort": "xhigh",
          "description": "Extra high reasoning depth for complex problems"
        }
      ],
      "shell_type": "shell_command",
      "visibility": "list",
      "minimal_client_version": "0.98.0",
      "supported_in_api": true,
      "availability_nux": null,
      "upgrade": null,
      "priority": 23,
      "experimental_supported_tools": [],
      "available_in_plans": [
        "business",
        "edu",
        "edu_plus",
        "edu_pro",
        "education",
        "enterprise",
        "enterprise_cbp_automation",
        "enterprise_cbp_usage_based",
        "finserv",
        "free",
        "free_workspace",
        "go",
        "hc",
        "k12",
        "plus",
        "pro",
        "prolite",
        "quorum",
        "sci",
        "self_serve_business_usage_based",
        "team"
      ],
      "supports_search_tool": true,
      "default_service_tier": null,
      "service_tiers": [],
      "additional_speed_tiers": [],
      "supports_reasoning_summaries": true
    },
    {
      "slug": "gpt-5.2",
      "prefer_websockets": true,
      "support_verbosity": true,
      "default_verbosity": "low",
      "apply_patch_tool_type": "freeform",
      "web_search_tool_type": "text",
      "input_modalities": [
        "text",
        "image"
      ],
      "supports_image_detail_original": false,
      "truncation_policy": {
        "mode": "bytes",
        "limit": 10000
      },
      "supports_parallel_tool_calls": true,
      "tool_mode": null,
      "multi_agent_version": null,
      "use_responses_lite": false,
      "include_skills_usage_instructions": false,
      "auto_review_model_override": null,
      "context_window": 272000,
      "max_context_window": 272000,
      "auto_compact_token_limit": null,
      "comp_hash": null,
      "reasoning_summary_format": "none",
      "default_reasoning_summary": "auto",
      "display_name": "GPT-5.2",
      "description": "Optimized for professional work and long-running agents.",
      "default_reasoning_level": "medium",
      "supported_reasoning_levels": [
        {
          "effort": "low",
          "description": "Balances speed with some reasoning; useful for straightforward queries and short explanations"
        },
        {
          "effort": "medium",
          "description": "Provides a solid balance of reasoning depth and latency for general-purpose tasks"
        },
        {
          "effort": "high",
          "description": "Maximizes reasoning depth for complex or ambiguous problems"
        },
        {
          "effort": "xhigh",
          "description": "Extra high reasoning for complex problems"
        }
      ],
      "shell_type": "shell_command",
      "visibility": "list",
      "minimal_client_version": "0.0.1",
      "supported_in_api": true,
      "availability_nux": null,
      "upgrade": null,
      "priority": 29,
      "experimental_supported_tools": [],
      "available_in_plans": [
        "business",
        "edu",
        "edu_plus",
        "edu_pro",
        "education",
        "enterprise",
        "enterprise_cbp_automation",
        "enterprise_cbp_usage_based",
        "finserv",
        "free",
        "free_workspace",
        "go",
        "hc",
        "k12",
        "plus",
        "pro",
        "prolite",
        "quorum",
        "sci",
        "self_serve_business_usage_based",
        "team"
      ],
      "supports_search_tool": true,
      "default_service_tier": null,
      "service_tiers": [],
      "additional_speed_tiers": [],
      "supports_reasoning_summaries": true
    },
    {
      "slug": "codex-auto-review",
      "prefer_websockets": true,
      "support_verbosity": true,
      "default_verbosity": "low",
      "apply_patch_tool_type": "freeform",
      "web_search_tool_type": "text_and_image",
      "input_modalities": [
        "text",
        "image"
      ],
      "supports_image_detail_original": true,
      "truncation_policy": {
        "mode": "tokens",
        "limit": 10000
      },
      "supports_parallel_tool_calls": true,
      "tool_mode": null,
      "multi_agent_version": null,
      "use_responses_lite": false,
      "include_skills_usage_instructions": false,
      "auto_review_model_override": null,
      "context_window": 272000,
      "max_context_window": 1000000,
      "auto_compact_token_limit": null,
      "comp_hash": null,
      "reasoning_summary_format": "experimental",
      "default_reasoning_summary": "none",
      "display_name": "Codex Auto Review",
      "description": "Automatic approval review model for Codex.",
      "default_reasoning_level": "medium",
      "supported_reasoning_levels": [
        {
          "effort": "low",
          "description": "Fast responses with lighter reasoning"
        },
        {
          "effort": "medium",
          "description": "Balances speed and reasoning depth for everyday tasks"
        },
        {
          "effort": "high",
          "description": "Greater reasoning depth for complex problems"
        },
        {
          "effort": "xhigh",
          "description": "Extra high reasoning depth for complex problems"
        }
      ],
      "shell_type": "shell_command",
      "visibility": "hide",
      "minimal_client_version": "0.98.0",
      "supported_in_api": true,
      "availability_nux": null,
      "upgrade": null,
      "priority": 43,
      "experimental_supported_tools": [],
      "available_in_plans": [
        "business",
        "edu",
        "edu_plus",
        "edu_pro",
        "education",
        "enterprise",
        "enterprise_cbp_automation",
        "enterprise_cbp_usage_based",
        "finserv",
        "go",
        "hc",
        "plus",
        "pro",
        "prolite",
        "quorum",
        "sci",
        "self_serve_business_usage_based",
        "team"
      ],
      "supports_search_tool": true,
      "default_service_tier": null,
      "service_tiers": [],
      "additional_speed_tiers": [],
      "supports_reasoning_summaries": true
    }
  ]
}
```

1. ### ACode/Astron 模型目录 JSON

> 注意：下方内容是便于阅读的精简快照，已省略 `base_instructions`、`model_messages` 等与模型选择无关的内容，不是接口返回的完整原始 JSON。远程模型目录可以独立更新，因此模型、思考深度和上下文窗口都可能发生变动。

查询当前 master 默认配置所使用的 Astron 远程模型目录。执行前，需要将 `ASTRON_MODELS_API_KEY` 设置为当前有效的模型目录 Bearer Token：

```Bash
curl --silent --show-error \
  --header "Authorization: Bearer ${ASTRON_MODELS_API_KEY}" \
  "https://astroncode-api-prod.xf-yun.com/api/v1/astroncode_webserver/models"
{
  "code": 0,
  "message": "success",
  "traceId": "trace_20260729_165609_5920",
  "data": {
    "models": [
      {
        "slug": "xminimaxm25",
        "upgrade": null,
        "priority": 6,
        "comp_hash": null,
        "tool_mode": null,
        "shell_type": "unified_exec",
        "visibility": "list",
        "description": "Minimax-M2.5 文本模型。",
        "display_name": "Minimax-M2.5",
        "service_tiers": [],
        "context_window": 128000,
        "availability_nux": null,
        "input_modalities": [
          "text"
        ],
        "supported_in_api": true,
        "default_verbosity": null,
        "support_verbosity": true,
        "truncation_policy": {
          "mode": "bytes",
          "limit": 10000
        },
        "max_context_window": 128000,
        "use_responses_lite": false,
        "multi_agent_version": null,
        "default_service_tier": null,
        "supports_search_tool": true,
        "web_search_tool_type": "text",
        "apply_patch_tool_type": null,
        "additional_speed_tiers": [],
        "default_reasoning_level": "high",
        "auto_compact_token_limit": null,
        "default_reasoning_summary": "none",
        "auto_review_model_override": null,
        "supported_reasoning_levels": [
          {
            "effort": "high",
            "description": "固定开启思考"
          }
        ],
        "experimental_supported_tools": [],
        "supports_parallel_tool_calls": true,
        "supports_reasoning_summaries": true,
        "supports_image_detail_original": true,
        "effective_context_window_percent": 95,
        "include_skills_usage_instructions": false
      },
      {
        "slug": "xopkimik26",
        "upgrade": null,
        "priority": 7,
        "comp_hash": null,
        "tool_mode": null,
        "shell_type": "unified_exec",
        "visibility": "list",
        "description": "Kimi-K2.6 多模态模型",
        "display_name": "Kimi-K2.6",
        "service_tiers": [],
        "context_window": 256000,
        "availability_nux": null,
        "input_modalities": [
          "text",
          "image"
        ],
        "supported_in_api": true,
        "default_verbosity": null,
        "support_verbosity": true,
        "truncation_policy": {
          "mode": "bytes",
          "limit": 10000
        },
        "max_context_window": 256000,
        "use_responses_lite": false,
        "multi_agent_version": null,
        "default_service_tier": null,
        "supports_search_tool": true,
        "web_search_tool_type": "text",
        "apply_patch_tool_type": null,
        "additional_speed_tiers": [],
        "default_reasoning_level": "high",
        "auto_compact_token_limit": null,
        "default_reasoning_summary": "none",
        "auto_review_model_override": null,
        "supported_reasoning_levels": [
          {
            "effort": "none",
            "description": "关闭思考"
          },
          {
            "effort": "high",
            "description": "开启思考"
          }
        ],
        "experimental_supported_tools": [],
        "supports_parallel_tool_calls": true,
        "supports_reasoning_summaries": true,
        "supports_image_detail_original": true,
        "effective_context_window_percent": 95,
        "include_skills_usage_instructions": false
      },
      {
        "slug": "xopglm52",
        "upgrade": null,
        "priority": 4,
        "comp_hash": null,
        "tool_mode": null,
        "shell_type": "unified_exec",
        "visibility": "list",
        "description": "GLM-5.2 文本模型。",
        "display_name": "GLM-5.2",
        "service_tiers": [],
        "context_window": 1000000,
        "availability_nux": null,
        "input_modalities": [
          "text"
        ],
        "supported_in_api": true,
        "default_verbosity": null,
        "support_verbosity": true,
        "truncation_policy": {
          "mode": "bytes",
          "limit": 10000
        },
        "max_context_window": 1000000,
        "use_responses_lite": false,
        "multi_agent_version": null,
        "default_service_tier": null,
        "supports_search_tool": true,
        "web_search_tool_type": "text",
        "apply_patch_tool_type": null,
        "additional_speed_tiers": [],
        "default_reasoning_level": "high",
        "auto_compact_token_limit": null,
        "default_reasoning_summary": "none",
        "auto_review_model_override": null,
        "supported_reasoning_levels": [
          {
            "effort": "none",
            "description": "关闭思考"
          },
          {
            "effort": "high",
            "description": "高强度思考"
          },
          {
            "effort": "max",
            "description": "最大强度思考"
          }
        ],
        "experimental_supported_tools": [],
        "supports_parallel_tool_calls": true,
        "supports_reasoning_summaries": true,
        "supports_image_detail_original": true,
        "effective_context_window_percent": 95,
        "include_skills_usage_instructions": false
      },
      {
        "slug": "xsparkx2agent",
        "upgrade": null,
        "priority": 2,
        "comp_hash": null,
        "tool_mode": null,
        "shell_type": "unified_exec",
        "visibility": "list",
        "description": "Spark-X2-Agent 文本模型。",
        "display_name": "Spark-X2-Agent",
        "service_tiers": [],
        "context_window": 262144,
        "availability_nux": null,
        "input_modalities": [
          "text"
        ],
        "supported_in_api": true,
        "default_verbosity": null,
        "support_verbosity": true,
        "truncation_policy": {
          "mode": "bytes",
          "limit": 10000
        },
        "max_context_window": 262144,
        "use_responses_lite": false,
        "multi_agent_version": null,
        "default_service_tier": null,
        "supports_search_tool": true,
        "web_search_tool_type": "text",
        "apply_patch_tool_type": null,
        "additional_speed_tiers": [],
        "default_reasoning_level": "high",
        "auto_compact_token_limit": null,
        "default_reasoning_summary": "none",
        "auto_review_model_override": null,
        "supported_reasoning_levels": [
          {
            "effort": "none",
            "description": "关闭思考"
          },
          {
            "effort": "high",
            "description": "开启思考"
          }
        ],
        "experimental_supported_tools": [],
        "supports_parallel_tool_calls": true,
        "supports_reasoning_summaries": true,
        "supports_image_detail_original": true,
        "effective_context_window_percent": 95,
        "include_skills_usage_instructions": false
      },
      {
        "slug": "xopglm51",
        "upgrade": null,
        "priority": 5,
        "comp_hash": null,
        "tool_mode": null,
        "shell_type": "unified_exec",
        "visibility": "list",
        "description": "GLM-5.1 文本模型。",
        "display_name": "GLM-5.1",
        "service_tiers": [],
        "context_window": 200000,
        "availability_nux": null,
        "input_modalities": [
          "text"
        ],
        "supported_in_api": true,
        "default_verbosity": null,
        "support_verbosity": true,
        "truncation_policy": {
          "mode": "bytes",
          "limit": 10000
        },
        "max_context_window": 200000,
        "use_responses_lite": false,
        "multi_agent_version": null,
        "default_service_tier": null,
        "supports_search_tool": true,
        "web_search_tool_type": "text",
        "apply_patch_tool_type": null,
        "additional_speed_tiers": [],
        "default_reasoning_level": "high",
        "auto_compact_token_limit": null,
        "default_reasoning_summary": "none",
        "auto_review_model_override": null,
        "supported_reasoning_levels": [
          {
            "effort": "none",
            "description": "关闭思考"
          },
          {
            "effort": "high",
            "description": "高强度思考"
          },
          {
            "effort": "max",
            "description": "最大强度思考"
          }
        ],
        "experimental_supported_tools": [],
        "supports_parallel_tool_calls": true,
        "supports_reasoning_summaries": true,
        "supports_image_detail_original": true,
        "effective_context_window_percent": 95,
        "include_skills_usage_instructions": false
      },
      {
        "slug": "xopdeepseekv4pro",
        "upgrade": null,
        "priority": 9,
        "comp_hash": null,
        "tool_mode": null,
        "shell_type": "unified_exec",
        "visibility": "list",
        "description": "DeepSeek-V4-Pro 文本模型。",
        "display_name": "DeepSeek-V4-Pro",
        "service_tiers": [],
        "context_window": 1000000,
        "availability_nux": null,
        "input_modalities": [
          "text"
        ],
        "supported_in_api": true,
        "default_verbosity": null,
        "support_verbosity": true,
        "truncation_policy": {
          "mode": "bytes",
          "limit": 10000
        },
        "max_context_window": 1000000,
        "use_responses_lite": false,
        "multi_agent_version": null,
        "default_service_tier": null,
        "supports_search_tool": true,
        "web_search_tool_type": "text",
        "apply_patch_tool_type": null,
        "additional_speed_tiers": [],
        "default_reasoning_level": "high",
        "auto_compact_token_limit": null,
        "default_reasoning_summary": "none",
        "auto_review_model_override": null,
        "supported_reasoning_levels": [
          {
            "effort": "none",
            "description": "关闭思考"
          },
          {
            "effort": "high",
            "description": "高强度思考"
          },
          {
            "effort": "max",
            "description": "最大强度思考"
          }
        ],
        "experimental_supported_tools": [],
        "supports_parallel_tool_calls": true,
        "supports_reasoning_summaries": true,
        "supports_image_detail_original": true,
        "effective_context_window_percent": 95,
        "include_skills_usage_instructions": false
      },
      {
        "slug": "astronclaw-auto",
        "upgrade": null,
        "priority": 1,
        "comp_hash": null,
        "tool_mode": null,
        "shell_type": "unified_exec",
        "visibility": "list",
        "description": "Auto 文本模型。",
        "display_name": "Auto",
        "service_tiers": [],
        "context_window": 200000,
        "availability_nux": null,
        "input_modalities": [
          "text"
        ],
        "supported_in_api": true,
        "default_verbosity": null,
        "support_verbosity": true,
        "truncation_policy": {
          "mode": "bytes",
          "limit": 10000
        },
        "max_context_window": 200000,
        "use_responses_lite": false,
        "multi_agent_version": null,
        "default_service_tier": null,
        "supports_search_tool": true,
        "web_search_tool_type": "text",
        "apply_patch_tool_type": null,
        "additional_speed_tiers": [],
        "default_reasoning_level": "high",
        "auto_compact_token_limit": null,
        "default_reasoning_summary": "none",
        "auto_review_model_override": null,
        "supported_reasoning_levels": [
          {
            "effort": "none",
            "description": "关闭思考"
          },
          {
            "effort": "high",
            "description": "开启思考"
          }
        ],
        "experimental_supported_tools": [],
        "supports_parallel_tool_calls": true,
        "supports_reasoning_summaries": true,
        "supports_image_detail_original": true,
        "effective_context_window_percent": 95,
        "include_skills_usage_instructions": false
      },
      {
        "slug": "xopqwen36v35b",
        "upgrade": null,
        "priority": 8,
        "comp_hash": null,
        "tool_mode": null,
        "shell_type": "unified_exec",
        "visibility": "list",
        "description": "Qwen3.6-35B-A3B 文本模型。",
        "display_name": "Qwen3.6-35B-A3B",
        "service_tiers": [],
        "context_window": 128000,
        "availability_nux": null,
        "input_modalities": [
          "text"
        ],
        "supported_in_api": true,
        "default_verbosity": null,
        "support_verbosity": true,
        "truncation_policy": {
          "mode": "bytes",
          "limit": 10000
        },
        "max_context_window": 128000,
        "use_responses_lite": false,
        "multi_agent_version": null,
        "default_service_tier": null,
        "supports_search_tool": true,
        "web_search_tool_type": "text",
        "apply_patch_tool_type": null,
        "additional_speed_tiers": [],
        "default_reasoning_level": "high",
        "auto_compact_token_limit": null,
        "default_reasoning_summary": "none",
        "auto_review_model_override": null,
        "supported_reasoning_levels": [
          {
            "effort": "none",
            "description": "关闭思考"
          },
          {
            "effort": "high",
            "description": "开启思考"
          }
        ],
        "experimental_supported_tools": [],
        "supports_parallel_tool_calls": true,
        "supports_reasoning_summaries": true,
        "supports_image_detail_original": true,
        "effective_context_window_percent": 95,
        "include_skills_usage_instructions": false
      }
    ]
  }
}
```