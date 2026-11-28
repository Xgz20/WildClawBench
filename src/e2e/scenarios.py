"""Map product scenarios to their execution and scoring contracts."""


def runtime_scene(scenario: str) -> str:
    # Legal tasks use the General file/trace contract and hybrid scorer.
    return "general" if scenario == "legal" else scenario
