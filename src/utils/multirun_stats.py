"""多轮评测统计：mean/std/pass@k/pass^k（无偏组合估计）。

参考 OpenAI HumanEval 的无偏 pass@k，Harbor/QwenClawBench 同源。
纯函数、无副作用、无第三方依赖（仅标准库 math/statistics）。
口径定义见 docs/local/design/评测评分口径.md §6。
"""
from __future__ import annotations

import math
import statistics

DEFAULT_PASS_THRESHOLD = 0.99


def pass_at_k(n: int, c: int, k: int) -> float:
    """n 轮中 c 轮成功，k 次尝试至少成功一次的无偏概率。

    Parameters
    ----------
    n : int
        总有效轮数
    c : int
        成功（pass）轮数
    k : int
        报告的尝试次数（通常取 k=n）

    Returns
    -------
    float
        pass@k 概率（0.0 ~ 1.0）
    """
    if k > n or n <= 0:
        return 0.0
    if c <= 0:
        return 0.0
    if n - c < k:
        return 1.0  # 失败轮不足 k，任取 k 轮必含成功
    return 1.0 - math.comb(n - c, k) / math.comb(n, k)


def pass_hat_k(n: int, c: int, k: int) -> float:
    """n 轮中 c 轮成功，连续 k 次尝试全部成功的无偏概率。

    Parameters
    ----------
    n : int
        总有效轮数
    c : int
        成功（pass）轮数
    k : int
        报告的尝试次数（通常取 k=n）

    Returns
    -------
    float
        pass^k 概率（0.0 ~ 1.0）
    """
    if k > n or n <= 0:
        return 0.0
    if c < k:
        return 0.0
    return math.comb(c, k) / math.comb(n, k)


def aggregate_runs(scores: list[float], pass_threshold: float = DEFAULT_PASS_THRESHOLD) -> dict:
    """聚合一个 task 的多轮 overall_score 列表。

    scores 只应包含**有效轮**的分数（调用方负责剔除无 score.json 的轮；
    执行失败但产出了 0 分 score.json 的轮算有效轮，计入 n 但通常不 pass）。

    Parameters
    ----------
    scores : list[float]
        有效轮的 overall_score 列表（0.0 ~ 1.0）
    pass_threshold : float, optional
        overall_score >= 此值算 pass，默认 0.99（满分）

    Returns
    -------
    dict
        包含 runs/mean/std/pass_count/pass_at_k/pass_hat_k/pass_threshold/scores
    """
    n = len(scores)
    if n == 0:
        return {
            "runs": 0, "mean": None, "std": None, "pass_count": 0,
            "pass_at_k": None, "pass_hat_k": None,
            "pass_threshold": pass_threshold, "scores": [],
        }
    c = sum(1 for s in scores if s >= pass_threshold)
    k = n  # 报告口径：用满 n 轮估计 pass@n / pass^n
    return {
        "runs": n,
        "mean": statistics.fmean(scores),
        "std": statistics.pstdev(scores) if n > 1 else 0.0,
        "pass_count": c,
        "pass_at_k": pass_at_k(n, c, k),
        "pass_hat_k": pass_hat_k(n, c, k),
        "pass_threshold": pass_threshold,
        "scores": scores,
    }
