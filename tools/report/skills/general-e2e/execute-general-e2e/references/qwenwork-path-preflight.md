# QwenWork 发送前路径预检

Driver 在加载冻结配置与 fresh probe 后、连接 CDP 前执行预检。`--validate-only` 同样执行，但不创建项目、锁或发送 Prompt。运行时证据放在 journal 的 `PATH_PREFLIGHT_VERIFIED` 事件中；派生预检字段不改变原 config digest。

当前 SDK 的 project 编码将非 ASCII 字母/数字的 UTF-16 code unit 替换为 `-`。映射结果不超过前缀阈值时直接使用；超过阈值时保留前缀，再附加 `-` 和对原始路径计算的 DJB2 XOR 绝对值 base36 哈希。QwenWorkCN 1.2.0 实际阈值为 200。probe 静态确认编码函数、哈希函数、唯一阈值赋值和 runtime SHA；不执行 SDK，不依赖混淆标识符或版本号。能力不能确认时返回未验证并拒绝执行。

预检包括：

- task/Workspace/Prompt 的绝对路径与包含关系；原始组件的 UTF-8 字节数。
- state、归档锁及原子写临时文件的路径预算。
- native `projects/<encoded>/...jsonl`、`logs/sessions/<encoded>/<session>/segments/<file>` 与 `tmp/<encoded>/images/<session>`。
- 原生 session 目录和 segment 文件名预留完整 NAME_MAX 级别的 255 字节；transcript 文件名也按 255 字节预留。它们是预算占位符，不是伪造的原生 ID。
- 使用 `/usr/bin/getconf` 读取 Workspace 和 trace 根所在文件系统的 NAME_MAX/PATH_MAX；PATH_MAX 还需容纳末尾 NUL。
- 路径组件、既有原生目录中的符号链接、canonical 路径变化、父目录不可写和非目录结构均拒绝。

越限时错误包含路径用途、实际与允许字节数，应重新准备更短的批次根或 trace 根。不得修改旧 attempt 的冻结路径绕过校验。题目 `timeout_seconds` 不参与预检，也不会变成任务执行期限。

这是执行/日志路径预算，不承诺模型未来任意创建的文件名都合法；候选文件树、受限链接与冻结一致性仍由正式 collector/finalizer 校验。
