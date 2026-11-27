"""Keep AStudio's collapsed-paste title verifiable without editing task inputs."""
from .preprocessing import file_sha256_bytes

ASTUDIO_CARD_PROFILE = "astudio-environment-card-title/v1"


def astudio_environment_card(prompt, metadata):
    """AStudio exposes the first line as the title of a pasted-text card.

    The short framework heading `[执行环境]` cannot pass WGUI's >=12-character
    prefix check. Put a content-bound identifier first so a collapsed card can
    be read back and cannot be confused with another task's generic heading.
    Keep the task body, environment instructions and plugin references intact.
    """
    heading, newline, body = prompt.partition("\n")
    if heading.rstrip("\r") != "[执行环境]" or not newline:
        return prompt, metadata
    source_sha = file_sha256_bytes(prompt.encode("utf-8"))
    effective = f"[{source_sha[:32]} 执行环境]\n" + body
    return effective, {**metadata, "changed": True,
        "effective_prompt_sha256": file_sha256_bytes(effective.encode("utf-8")),
        "prompt_transport": {"profile": ASTUDIO_CARD_PROFILE, "source_prompt_sha256": source_sha}}
