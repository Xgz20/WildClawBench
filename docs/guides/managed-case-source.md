# 平台个人用例来源与评分契约

外部来源采用 `wildclawbench.managed-cases/v1`。平台在数据库保存不可变修订，在私有对象存储保存原素材与冻结包；框架只消费经 SHA-256 校验的包，不写 `tasks/` 或 Git 数据集注册表。

## 包与准备

ZIP 根目录 `manifest.json` 包含 `schema`、`dataset_id`、`scene`、`cases`、`files`、`content_sha256`。每个 case 固定修订身份、完整结构化 document 和素材引用。`files` 逐文件保存大小与 SHA-256；`content_sha256` 是移除此字段后按键排序、紧凑 UTF-8 JSON 的摘要。派发另绑定整个 ZIP 的 SHA-256。

素材条目包含 `role: input|gt|support`、工作区相对 `path`、包内 `file` 和 `sha256`。输出在 `outputs` 声明。`input` 进入 `execution/exec`，其它素材仅进入 `private-scoring/gt`。评分期间才把 GT 加入独立评分副本，原执行容器与执行备份不被改写。

```bash
python eval/manage_cases.py describe
python eval/manage_cases.py validate --input case-validation.json
python eval/manage_cases.py compile --input source.zip --sha256 <ZIP_SHA256> --output <持久化缓存目录>
```

校验输入为 `{"document": {...}, "scene": {"base_contract": "general"}}`。CLI 入口使用 `--case-source` 和必填 `--case-source-sha256`；E2E 的 `plan.selection.case_source` 使用 `{path, sha256}`。平台接口接受数据库来源引用，不能让用户指定服务端文件路径。

编译仅构造本包的任务/素材树及标准 bundle。复用缓存也重新核对来源、派生清单、文件集合和摘要。缓存不是原始数据源，可删除后从私有原包重建。

## 配置式场景

`scene.base_contract` 支持 `general`、`web`、`ppt`，保留业务场景名称和版本。配置项有：

- `required_inputs`、`required_outputs`：必须声明的相对路径。
- `criteria`、`rules`、`case_defaults`：新草稿的默认标准、检查和字段。
- `scoring`：冻结的默认模板与说明。
- `required_capabilities`：所需取证能力；未知能力被拒绝。

这些来源使用明确的 `managed-case-score/v1` 契约和 0–1 分值，不冒充旧专项 Web/PPT Skill 结果。配置式 Web/PPT 通过实际浏览器/Office 媒体取证评阅产物。API 支持静态网页宽窄屏取证；需要浏览器交互、原生桌面或新增构建/取证驱动时，必须选择支持的投递方式，无法满足时返回评分异常。旧专项系统用例跨契约混编会被阻止。

## 评分上下文与隔离

上下文采用 `wildclawbench.scoring-context/v1`，固定题目、Rubric、规则结果、素材目录、候选、轨迹、模板版本和投递方式。模板只替换白名单变量：`task.prompt`、`task.name`、`rubric`、`materials`、`candidate`、`trajectory`、`rules`、`output_contract`。不执行模板代码或访问服务器环境变量。

模板优先级为新评分组显式模板、单题模板、场景模板。补充字段保留；同一评分组重评沿用冻结配置。Rubric、权重、锚点和结果校验不能被模板替换。系统固定引用保留原判分契约，不允许自定义模板覆盖。

- API：发送实际文本及渲染图片，支持 Chat Completions、Responses、Anthropic 消息格式。
- Codex/DSH CLI：发送上下文文件、媒体文件和原生工具指引。
- 桌面沙箱：上传独立私有评分目录；候选和渲染证据均检查回传内容摘要。

规则代码由后端静态解析，在无模型凭据、无 Docker socket、无网络的独立容器执行。容器只读根目录、只读候选、限制 CPU/内存/PID 和超时；规则结果作为数据交给语义裁判。不会在带模型凭据的 CLI 进程执行检查代码，也不修改共享镜像安装依赖。

显式依赖使用 `dependencies`，例如 `python:openpyxl`、`python:pandas`、`python:pillow`、`python:pymupdf`、`python:python-docx`、`python:python-pptx`、`python:playwright`。在所选镜像探测，缺少就预检失败。规则默认最多 600 秒，受总评分超时约束。

媒体提取在同类隔离容器实际渲染 Office/PDF、图片与静态网页；最多 50 页、16 MB 证据上下文，超过限制或不支持格式明确失败，不截断后给分。CLI/桌面收到实际媒体文件，API 收到实际媒体内容。

评分记录上下文、实际 Prompt 和模板摘要。`verify_score` 独立核对冻结输入、规则结果、原始模型 JSON、键集合、分值锚点、聚合值、候选及媒体文件。异常不补零。E2E 输出显式 `wildclawbench.managed-e2e-score/v1`，兼容现有评分版本与报告适配，不标称原 Skill `verify-score`。

临时规则/模型容器记录不可猜测的资源所有权标签；恢复前只清理标签吻合的原资源。桌面释放未确认或资源观察失败时保留异常，避免重复派发。

## 系统引用与导入安全

系统固定引用在平台保存受保护的原始材料，历史运行不依赖当前 checkout。下载共享的自建包包含自建 GT/脚本，系统部分只导出固定引用；复制成可编辑草稿只含公开输入，必须补齐并重新审核评分材料。

ZIP 采用有界逐成员读取，拒绝路径穿越、链接、特殊文件、重名和 Windows 路径冲突。默认 10000 成员、2 GiB 解压总量、512 MiB 单文件；前两项通过 `WCB_CASE_MAX_FILES`、`WCB_CASE_MAX_UNPACKED` 调整。支持 BOM/CRLF，保留未知 YAML 字段及章节；拒绝重复 YAML 键和递归别名。

## 验证

```bash
python -m unittest tests.test_managed_cases tests.test_unified_reports tests.e2e.test_case_reruns -q
WCB_MANAGED_TEST_IMAGE=<已安装的本地评分镜像> WCB_MANAGED_TEST_CONTEXT=colima python -m unittest tests.test_managed_cases -q
```

容器验证仅使用合成材料和离线检查，不调用付费模型。跨平台执行采用既有 `wildclawbench.workspace-paths/v1`：Linux `/tmp_workspace`，Windows 通过经过写读探针核验的 `C:\tmp_workspace` junction 映射到客户端工作区；不向被测端提供 GT。
