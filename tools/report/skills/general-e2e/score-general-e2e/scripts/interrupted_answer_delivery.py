"""Represent a proven interrupted turn without a formal answer as absent delivery."""
import ast
import hashlib

PROFILE = "verified-native-interruption-answer-absence/v1"
ADMISSION = "authorized-astronstudio-native-interruption/v1"
DATASET = {"id": "general-custom70-v4", "digest": "914783354b23efa4f814342187ebe931df76cbcb0b2ea3dd85bd3f5705f485ff"}
REGISTRY = {
    "01_Information_Search_Organization_task_007_rice_awd_field_trials": (
        "34470d2c802bd05af42abe62bd85bfd1f368710a059e5f9ac84cbb2829ed5299",
        "c253d90b6c0e1653a1b94e6587be572d6158ec3acacf5ea1307196a9ae8617dd"),
    "01_Information_Search_Organization_task_018_urban_rural_cpi_sign_screening": (
        "577f8a3c684046c627b041201bf456dcf98b388e95c38aa81e4dafa842ea2a2d",
        "122f8dd3d9216da7a0163039f79f0703acd872f5b6a4fa4c7cd76f22d62d9888"),
    "01_Information_Search_Organization_task_020_treasury_yield_rising_intervals": (
        "a0a735db791432be079b355692019382f6185c4252adda9f280d3a6f5d1edb40",
        "12fac49ec3702ed6fa46321b8c7746fb51ee0ec3d4ba24f6326071946ea7dd33"),
}
GUARD = "    if not completed:\n        raise ValueError('EVALUATOR_EVIDENCE_MISSING: final answer cannot be determined')"
REPLACEMENT = '''    if not completed:
        aborted=[(i,row.get('status',{})) for i,row in current
                 if row.get('type')=='status' and row.get('status',{}).get('type')=='turn_aborted']
        if (len(aborted)==1 and aborted[0][0]==len(transcript)-1
                and aborted[0][1].get('reason')=='interrupted'
                and isinstance(aborted[0][1].get('turn_id'),str)):
            return '',{'status':'verified_interrupted_without_formal_answer','event_index':aborted[0][0],
                      'delivery_profile':'verified-native-interruption-answer-absence/v1',
                      'formal_answer_present':False,'terminal_type':'turn_aborted'}
        raise ValueError('EVALUATOR_EVIDENCE_MISSING: final answer cannot be determined')'''
POLICY = {
    "profile": PROFILE,
    "formal_answer_present": False,
    "extraction_basis": "经原生中断证明、完整同回合SDK和候选目录核实，正式答复未交付。证据导出的空答复文本表示交付缺失。",
    "judge_instruction": "按原Rubric逐项核实业务交付及过程。进度、压缩交接、计划、工具返回不视为正式答复。过程能力可按实际回执判断。适配器未分配质量分，正式分数由独立裁判及原合分规则产生。",
    "original_transcript_preserved": True,
    "original_terminal_preserved": True,
    "numeric_decisions_assigned": False,
}


def marker(contract, contract_sha, dataset, evidence_admission):
    if evidence_admission != ADMISSION or {k: dataset.get(k) for k in DATASET} != DATASET:
        return None
    expected = REGISTRY.get(contract.get("task_id"))
    if not expected or (contract_sha, hashlib.sha256(contract.get("automated_checks", "").encode()).hexdigest()) != expected:
        return None
    return {"profile": PROFILE, "contract_sha256": expected[0], "source_sha256": expected[1]}


def policy(manifest, contract):
    frozen = manifest.get("runtime", {}).get("interrupted_answer_delivery_profile")
    if frozen is None:
        return None
    expected = marker(contract, manifest["digests"]["contract_sha256"], manifest["dataset"], manifest.get("evidence_admission"))
    if frozen != expected or expected is None:
        raise ValueError("INTERRUPTED_ANSWER_DELIVERY_PROFILE_MISMATCH")
    return POLICY


def effective_source(manifest, original, current, prior):
    contract = {"task_id": manifest["identity"]["task_id"], "automated_checks": original}
    if policy(manifest, contract) is None:
        return current, prior
    nodes = [n for n in ast.parse(current).body if isinstance(n, ast.FunctionDef) and n.name == "_final_answer"]
    if len(nodes) != 1:
        raise ValueError("INTERRUPTED_ANSWER_DELIVERY_SOURCE_MISMATCH")
    function = ast.get_source_segment(current, nodes[0])
    if function.count(GUARD) != 1:
        raise ValueError("INTERRUPTED_ANSWER_DELIVERY_SOURCE_MISMATCH")
    corrected = current.replace(function, function.replace(GUARD, REPLACEMENT, 1), 1)
    receipt = {"schema_version": "wildclawbench.general-e2e-rule-source-correction/v1", "correction_id": PROFILE,
               "task_id": contract["task_id"], "contract_sha256": manifest["digests"]["contract_sha256"],
               "original_source_sha256": hashlib.sha256(original.encode()).hexdigest(),
               "effective_source_sha256": hashlib.sha256(corrected.encode()).hexdigest(),
               "candidate_rewritten": False, "numeric_decisions_assigned": False, "answer_delivery_policy": POLICY,
               "reason": "完整原生中断证明下，正式答复未交付作为交付缺失交接原Rubric，不再因提取不到正式答复阻止零权重取证Worker。原规则和业务/能力权重保持原契约。"}
    if prior:
        receipt["prior_correction"] = prior
    return corrected, receipt
