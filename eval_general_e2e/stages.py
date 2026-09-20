"""Locked public stage and Skill identities for General E2E."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Dict, Tuple


CONTRACT_VERSION = "general-e2e-contract-v1"
BUNDLE_PROTOCOL = "general-e2e-package-v1"
SKILL_METADATA_SCHEMA = "wildclawbench.general-e2e-skill/v1"
INITIAL_SKILL_VERSION = "0.1.0"
INTERFACE_ONLY = "interface_only"
OPERATIONAL = "operational"
PREPARE_SKILL_VERSION = "0.2.0"
EXECUTE_SKILL_VERSION = "0.9.1"
COLLECT_SKILL_VERSION = "0.6.1"
ORCHESTRATE_SKILL_VERSION = "0.9.0"
SCORE_SKILL_VERSION = "0.8.0"
RUN_SKILL_VERSION = "0.5.0"
REPORT_SKILL_VERSION = "0.2.2"


@dataclass(frozen=True)
class GeneralE2ESkillSpec:
    """Stable public identity and ownership boundary for one General E2E Skill."""

    name: str
    stages: Tuple[str, ...]
    responsibility: str
    input_contract: str
    output_contract: str
    version: str = INITIAL_SKILL_VERSION
    implementation_status: str = INTERFACE_ONLY

    def as_dict(self) -> Dict[str, object]:
        payload = asdict(self)
        payload["stages"] = list(self.stages)
        return payload

    def metadata(self) -> Dict[str, object]:
        return {
            "schema_version": SKILL_METADATA_SCHEMA,
            "name": self.name,
            "version": self.version,
            "contract_version": CONTRACT_VERSION,
            "bundle_protocol": BUNDLE_PROTOCOL,
            "implementation_status": self.implementation_status,
            "stages": list(self.stages),
        }


GENERAL_E2E_SKILLS: Tuple[GeneralE2ESkillSpec, ...] = (
    GeneralE2ESkillSpec(
        name="prepare-general-e2e-workspaces",
        stages=("prepare",),
        responsibility="从冻结数据集装配隔离的执行包、评分包和批次配置",
        input_contract="版本化 dataset bundle、Harness 配置和输出位置",
        output_contract="批次 manifest、execution/scoring ZIP、报告配置和 Skill 清单",
        version=PREPARE_SKILL_VERSION,
        implementation_status=OPERATIONAL,
    ),
    GeneralE2ESkillSpec(
        name="execute-general-e2e",
        stages=("execute",),
        responsibility="驱动或协助桌面 Harness 执行用例并持久化原生执行状态",
        input_contract="execution 包、Harness 配置和执行策略",
        output_contract="原生会话绑定、执行终态和初步资源记录",
        version=EXECUTE_SKILL_VERSION,
        implementation_status=OPERATIONAL,
    ),
    GeneralE2ESkillSpec(
        name="collect-general-e2e",
        stages=("collect-evidence",),
        responsibility="冻结候选并收集可审计的轨迹、资源和执行证据",
        input_contract="执行状态、原生轨迹和终态 Workspace",
        output_contract="冻结候选、标准轨迹、指标、证据清单和执行回执",
        version=COLLECT_SKILL_VERSION,
        implementation_status=OPERATIONAL,
    ),
    GeneralE2ESkillSpec(
        name="orchestrate-general-e2e",
        stages=("score",),
        responsibility="建立独立评分工作空间并调度可恢复的单题裁判任务",
        input_contract="有效执行回执、scoring 包和冻结裁判配置",
        output_contract="评分队列、裁判任务状态和有效 submission",
        version=ORCHESTRATE_SKILL_VERSION,
        implementation_status=OPERATIONAL,
    ),
    GeneralE2ESkillSpec(
        name="score-general-e2e",
        stages=("score",),
        responsibility="对单题执行自动规则和语义裁判并保留证据审计",
        input_contract="单题评分工作空间和冻结裁判配置",
        output_contract="规则分、语义分、证据引用、审计和标准 score.json",
        version=SCORE_SKILL_VERSION,
        implementation_status=OPERATIONAL,
    ),
    GeneralE2ESkillSpec(
        name="report-general-e2e",
        stages=("report",),
        responsibility="校验并聚合回传包，生成同源可复算报告",
        input_contract="校验通过的回传包和报告配置",
        output_contract="报告 JSON、Markdown、Excel、覆盖率和异常分母",
        version=REPORT_SKILL_VERSION,
        implementation_status=OPERATIONAL,
    ),
    GeneralE2ESkillSpec(
        name="run-general-e2e",
        stages=(
            "prepare",
            "execute",
            "collect-evidence",
            "score",
            "package",
            "import-return",
            "report",
        ),
        responsibility="按用户明确选择的阶段串联、恢复和交接 General E2E 流程",
        input_contract="显式阶段、冻结配置、输入包或已有运行状态",
        output_contract="阶段状态、回执、回传包及所选阶段的最终产物",
        version=RUN_SKILL_VERSION,
        implementation_status=OPERATIONAL,
    ),
)

_SKILLS_BY_NAME = {spec.name: spec for spec in GENERAL_E2E_SKILLS}


def get_skill_spec(name: str) -> GeneralE2ESkillSpec:
    """Return one locked Skill specification or raise a stable lookup error."""

    try:
        return _SKILLS_BY_NAME[name]
    except KeyError as exc:
        raise KeyError(f"unknown General E2E Skill: {name}") from exc
