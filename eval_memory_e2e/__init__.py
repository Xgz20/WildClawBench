"""Multi-session memory evaluation, separate from General E2E contract v1."""

CONTRACT = "wildclawbench.memory-e2e/v1"
DATASET_ID = "memory-diagnostic20-v1"
HARNESS_PORTS = {"AstronStudio": 9240, "WorkBuddy": 9229, "QwenWork": 9250, "DoubaoWork": 9260}
EXECUTION_GUARD = (
    "【评测操作边界】本任务只验证当前被评测客户端的记忆。"
    "Codex 仅为调研参考，禁止访问或修改其记忆配置、开关和数据，尤其是 ~/.codex/config.toml 与 ~/.codex/memories/；"
    "不得调用其他客户端来代做本题。记住或忘记只针对本轮档案代号下的合成资料，不将其当作当前登录用户的真实身份或日常偏好；"
    "不得清空账号记忆、修改全局记忆开关或改动无关记忆。允许使用当前客户端的原生记忆机制保存本轮档案。"
    "文件操作仅限当前工作目录及当前客户端的原生记忆存储；禁止向上搜索或读取评测批次的 private、public、.native、evidence、runtime-source、manifest.json、其他 episode 工作目录或控制日志。"
    "不得从评测提示词副本、控制文件或评分材料中查找历史事实与参考答案。"
)
AUTOMATIC_EXECUTION_GUARD = (
    "【执行边界】仅在当前客户端完成本题。Codex 不属于本轮执行范围，禁止访问或修改 ~/.codex/config.toml 与 ~/.codex/memories/。"
    "不得调用其他客户端代做。题目中的项目和人物均为合成业务资料，不代表当前登录用户的身份或偏好。"
    "不得清空账号、修改全局配置或改动无关数据。文件操作仅限当前工作目录及当前客户端的原生存储；"
    "禁止向上搜索或读取评测批次的 private、public、.native、evidence、runtime-source、manifest.json、其他 episode 工作目录或控制日志。"
    "不得从评测提示词副本、控制文件或评分材料中查找历史事实与参考答案。"
)


def execution_guard(mode='explicit'):
    return AUTOMATIC_EXECUTION_GUARD if mode == 'automatic' else EXECUTION_GUARD
DIMENSIONS = {
    "retention": 3, "personalization": 3, "temporal": 3, "updates": 3,
    "forgetting": 2, "isolation": 2, "relevance": 2, "procedural": 2,
}
METRICS = {
    "fact_recall": "higher", "application": "higher", "temporal_accuracy": "higher",
    "update_accuracy": "higher", "stale_value_misuse": "lower",
    "forgetting_compliance": "higher", "retained_fact": "higher",
    "scope_leakage": "lower", "appropriate_abstention": "higher",
    "answerable_accuracy": "higher", "irrelevant_interference": "lower",
    "procedure_success": "higher",
}
