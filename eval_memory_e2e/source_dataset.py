"""Deterministic adaptation of pinned author-published records, never LLM QA synthesis."""

from __future__ import annotations

import json
from pathlib import Path

from .dataset import DATA, OPEN_DATA, load_dataset
from .io import publish, sha, safe_file, read_json, require

LONGMEMEVAL_REVISION = "98d7416c24c778c2fee6e6f3006e7a073259d48f"
LONGMEMEVAL_SHA256 = "821a2034d219ab45846873dd14c14f12cfe7776e73527a483f9dac095d38620c"
SOURCE_IDS = {1: "66f24dbb", 2: "1903aded", 3: "caf9ead2", 4: "b6025781", 5: "a89d7624", 6: "d6233ab6",
              7: "9aaed6a3", 8: "8077ef71", 9: "efc3f7c2", 10: "0f05491a", 11: "dfde3500", 12: "4b24c848",
              17: "f4f1d8a4_abs", 18: "0862e8bf_abs"}


def literal(text):
    return str(text).replace("{", "{{").replace("}", "}}")


def build_source_dataset(cache_root, destination=OPEN_DATA.parent):
    cache, destination = Path(cache_root), Path(destination)
    require(not destination.exists(), "OUTPUT_EXISTS", str(destination))
    source_file = safe_file(cache / "longmemeval__longmemeval_oracle.json")
    require(sha(source_file.read_bytes()) == LONGMEMEVAL_SHA256, "UPSTREAM_DATA_DRIFT", "Expected the pinned author data")
    records = read_json(source_file)
    lookup = {row["question_id"]: (index, row) for index, row in enumerate(records)}
    original_cases = load_dataset(DATA)["scenarios"]
    assets, names = {}, []
    destination.mkdir(parents=True)
    license_bytes = safe_file(cache / "longmemeval__LICENSE").read_bytes()
    publish(destination / "LICENSE.LongMemEval.txt", license_bytes)
    assets["LICENSE.LongMemEval.txt"] = sha(license_bytes)
    for number, old in enumerate(original_cases, 1):
        case = json.loads(json.dumps(old))
        if number not in SOURCE_IDS:
            case["provenance"] = {"origin": "self_constructed", "author": "Codex model-generated diagnostic scenario",
                                  "source_case": "memory-diagnostic20-v1/" + case["id"],
                                  "purpose": "补充定向遗忘、身份/项目隔离、可控工具经验；不是开源原题",
                                  "difficulty_calibration": "not_run"}
        else:
            row_index, original = lookup[SOURCE_IDS[number]]
            record_path = "originals/" + case["id"] + ".json"
            raw = (json.dumps(original, ensure_ascii=False, indent=2) + "\n").encode()
            publish(destination / record_path, raw)
            assets[record_path] = sha(raw)
            order = sorted(range(len(original["haystack_sessions"])), key=lambda i: original["haystack_dates"][i])
            steps = []
            for index, original_index in enumerate(order, 1):
                session = original["haystack_sessions"][original_index]
                transcript = "\n\n".join(message["role"].upper() + ":\n" + message["content"] for message in session)
                # Public input contains dialogue and dates only. has_answer,
                # answer_session_ids, gold answers and question type stay private.
                text = ("本轮公开基准档案代号为 {project}。以下为虚构历史资料，不是当前登录用户的真实身份或日常偏好。"
                        "请将它保留为该档案的独立上下文，供后续新会话查询；不要混入其他项目或个人记忆。无需逐字复述。\n"
                        + "历史日期：" + literal(original["haystack_dates"][original_index]) + "\n\n" + literal(transcript))
                steps.append({"id": f"s{index}", "phase": "seed", "session": "new", "scope": "A", "prompt": text})
            step_id = f"s{len(steps) + 1}"
            question = ("仅按本轮档案 {project} 的已知历史回答；缺失信息请明确说明未知，不要猜测。\n"
                        + "问题的业务日期：" + literal(original["question_date"]) + "\n\n" + literal(original["question"]))
            steps.append({"id": step_id, "phase": "probe", "session": "new", "scope": "A", "prompt": question})
            metric = {"retention": "fact_recall", "personalization": "application", "temporal": "temporal_accuracy",
                      "updates": "update_accuracy", "relevance": "appropriate_abstention"}[case["dimension"]]
            expectation = "按作者原始答案作语义判定，允许等价表达，不自行增加新要求。原始参考答案：\n" + json.dumps(original["answer"], ensure_ascii=False)
            if original["question_id"].endswith("_abs"):
                expectation += "\n正确指出信息未提供或说明未知即可，不要求凭空回答；不将只答其他已知事实视为回答了本题。"
            checks = [{"id": "c1", "step_id": step_id, "metric": metric, "expectation": literal(expectation), "required": True}]
            if case["dimension"] == "updates":
                checks.append({"id": "c2", "step_id": step_id, "metric": "stale_value_misuse",
                               "expectation": literal("在当前答案处错误使用历史中已被更正的旧值；应以原始参考答案为当前有效事实：" + str(original["answer"])),
                               "required": True})
            case.update(title="LongMemEval 原题适配 " + original["question_id"], steps=steps, checkpoints=checks, fixtures=[])
            case["provenance"] = {"origin": "open_source_adapted", "dataset": "LongMemEval-cleaned/oracle",
                "original_id": original["question_id"], "original_type": original["question_type"], "row_index": row_index,
                "revision": LONGMEMEVAL_REVISION, "license": "MIT", "record_path": record_path, "record_sha256": sha(raw),
                "source_url": "https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned/resolve/" + LONGMEMEVAL_REVISION + "/longmemeval_oracle.json",
                "upstream_file_sha256": LONGMEMEVAL_SHA256, "chronological_session_indices": order,
                "adaptations": ["author_oracle_evidence_sessions", "chronological_history_replay_as_user_inputs",
                                "original_English_question_and_gold_unchanged", "strip_public_has_answer_annotations",
                                "add_scoped_fictional_archive_wrapper", "reuse_original_question_date"],
                "selection": "fixed_short_history_diagnostic_selection_not_random_representative_sampling",
                "difficulty_calibration": "assigned_for_planning_not_empirically_calibrated",
                "official_benchmark_score_comparable": False}
        filename = case["id"] + ".json"
        publish(destination / filename, case)
        names.append(filename)
    attribution = ("# 来源与适配边界\n\n"
        "本集包含14道 LongMemEval 作者发布的原题适配和6道明确标记的自建补充题。\n\n"
        "LongMemEval: Di Wu, Hongwei Wang, Wenhao Yu, Yuwei Zhang, Kai-Wei Chang, Dong Yu. "
        "LongMemEval: Benchmarking Chat Assistants on Long-Term Interactive Memory, ICLR 2025.\n"
        "https://github.com/xiaowu0162/LongMemEval\n"
        "https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned\n\n"
        "数据 revision: " + LONGMEMEVAL_REVISION + "。MIT许可全文见 LICENSE.LongMemEval.txt。\n\n"
        "使用 oracle 文件的证据会话，保留原始问题、答案、角色文本和业务日期；增加档案作用域包装，转成桌面多会话输入。"
        "这降低了完整 S/M 长历史条件的检索负担，且固定选择了较短的历史，不能作为官方 LongMemEval 成绩或代表性抽样。\n\n"
        "自建补充为 MEM-13/14/15/16/19/20：遗忘、隔离和可控工具经验，来源不得写成开源原题。"
        "所有难度标签均未经四端实测校准。\n")
    publish(destination / "ATTRIBUTION.md", attribution.encode())
    assets["ATTRIBUTION.md"] = sha(attribution.encode())
    catalog = {"dataset_id": "memory-mixed20-v1", "version": 1, "language": "en-with-zh-control-wrapper",
        "timezone": "Asia/Shanghai", "composition": {"open_source_adapted": 14, "self_constructed": 6},
        "calibration": "not_run", "scenarios": names, "source_assets": assets}
    publish(destination / "manifest.json", catalog)
    return load_dataset(destination / "manifest.json")
