from pathlib import Path

import pytest

from tools.report.lib.eval_dataset.result_files import discover_results


RESULT_ROOT = Path("/Users/gzx/Project/GitHub/xgz/ai/evaluate/WildClawBench/eval_out/custom/round1/astroncode")


@pytest.mark.skipif(not RESULT_ROOT.is_dir(), reason="用户提供的外部 round1 结果目录不存在")
def test_real_round1_discovery():
    discovery = discover_results([RESULT_ROOT])
    assert len(discovery.records) == 300
    assert len({record.model for record in discovery.records}) == 5
    assert len({record.harness for record in discovery.records}) == 1
