from __future__ import annotations

import argparse


def build_run_batch_parser(default_model: str, default_parallel: int) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="ClawBench evaluation entry point",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--task", "-t", help="Path to a single task.md file")
    mode.add_argument(
        "--category",
        "-c",
        help="Category name, e.g. 01_Productivity_Flow, 02_Code_Intelligence, 03_Social_Interaction, 04_Search_Retrieval, 05_Creative_Synthesis, 06_Safety_Alignment",
    )

    parser.add_argument(
        "--modality",
        choices=["pure-text", "multimodal"],
        default=None,
        help="Only run tasks with this frontmatter modality (applies to --category mode; "
             "an explicit --task is never filtered)",
    )
    parser.add_argument(
        "--tag",
        dest="tags",
        action="append",
        default=None,
        metavar="TAG",
        help="Only run tasks whose frontmatter `tags` include this tag. Repeatable; "
             "multiple --tag form a union (a task matching ANY of them is kept). "
             "Applies to --category mode; an explicit --task is never filtered",
    )
    parser.add_argument(
        "--exclude-tag",
        dest="exclude_tags",
        action="append",
        default=None,
        metavar="TAG",
        help="Skip tasks whose frontmatter `tags` include this tag. Repeatable. "
             "Applied after --tag, so a task is kept only when it matches the --tag "
             "union AND carries none of the --exclude-tag values",
    )
    parser.add_argument(
        "--agent-backend",
        default="openclaw",
        choices=[
            "openclaw", "astronclaw", "claudecode", "codex",
            "hermesagent", "astroncode", "opencode",
        ],
        help="Agent backend implementation (default: openclaw)",
    )
    parser.add_argument(
        "--model",
        "-m",
        default=default_model,
        help=f"Model name (default: {default_model})",
    )
    parser.add_argument(
        "--parallel",
        "-p",
        type=int,
        default=default_parallel,
        metavar="N",
        help="Number of parallel containers (default: 1, i.e. sequential)",
    )
    parser.add_argument(
        "--timeout-multiplier",
        type=float,
        default=None,
        metavar="X",
        help="Scale every task's timeout_seconds by this factor. "
             "CLI takes precedence; falls back to env WILDCLAW_TIMEOUT_MULTIPLIER, then 1.0",
    )
    parser.add_argument(
        "--timeout-override",
        type=int,
        default=None,
        metavar="SECONDS",
        help="Set every task's timeout to this fixed value in seconds, ignoring "
             "each task's own timeout_seconds. Takes precedence over "
             "--timeout-multiplier. CLI first; falls back to env WILDCLAW_TIMEOUT_OVERRIDE",
    )
    parser.add_argument(
        "--memory",
        default=None,
        metavar="SIZE",
        help="Per-task container memory limit, e.g. 4g / 512m (docker --memory). "
             "CLI first; falls back to env WILDCLAW_DOCKER_MEMORY. Default: no limit",
    )
    parser.add_argument(
        "--cpus",
        default=None,
        metavar="N",
        help="Per-task container CPU limit, e.g. 2 / 1.5 (docker --cpus). "
             "CLI first; falls back to env WILDCLAW_DOCKER_CPUS. Default: no limit",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Skip tasks whose latest run (same model) already has a valid score.json; "
             "only missing/failed-to-produce tasks are executed",
    )
    parser.add_argument(
        "--rerun-error",
        action="store_true",
        help="With --resume (implied): rerun tasks whose latest run has an evaluation "
             "validity failure and needs_rerun=true",
    )
    parser.add_argument(
        "--rerun-anomalous",
        action="store_true",
        help="With --resume (implied): also rerun tasks whose latest run has ANY "
             "anomaly, including model/Harness outcomes and REVIEW signals",
    )
    parser.add_argument(
        "--lobster-name",
        default=None,
        help="Lobster name (used in output directory for comparison)",
    )
    parser.add_argument(
        "--lobster-workspace",
        default=None,
        help="Path to a personal OpenClaw workspace (contains SOUL.md, USER.md, etc.)",
    )
    parser.add_argument(
        "--lobster-env",
        default=None,
        help="Comma-separated env var names for skills that need API keys (e.g. GEMINI_API_KEY,FIRECRAWL_API_KEY)",
    )
    parser.add_argument(
        "--models-config",
        default=None,
        help="Path to a JSON file that will replace the top-level models field in ~/.openclaw/openclaw.json before each task",
    )
    parser.add_argument(
        "--thinking",
        default=None,
        help="Thinking/reasoning level for the model (default: high)",
    )
    parser.add_argument(
        "--openclaw-image-model",
        "--astronclaw-image-model",
        default=None,
        help="Optional OpenClaw/AstronClaw image tool model. If unset, falls back to the chat --model.",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=1,
        metavar="K",
        help="Repeat each task K times for multi-run stats (mean/std/pass@k/pass^k). "
             "Default 1 (single run, current behavior). Each run gets its own run dir.",
    )
    parser.add_argument(
        "--pass-threshold",
        type=float,
        default=0.99,
        metavar="T",
        help="overall_score >= T counts as a 'pass' for pass@k/pass^k. Default 0.99 (full score).",
    )
    return parser


def parse_run_batch_args(default_model: str, default_parallel: int) -> argparse.Namespace:
    return build_run_batch_parser(default_model, default_parallel).parse_args()
