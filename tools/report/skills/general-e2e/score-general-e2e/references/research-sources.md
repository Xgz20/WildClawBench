# 独立公开来源取证

score `0.24.0` 在评分 CLI 外围增加可选 `research_sources`，core 保持 `0.15.2`。它把候选实际阅读/引用的公开 URL 交给可信评分侧 collector 独立获取，再给离线规则和语义 Judge 提供同一份原件与文本。采集器不评分，不调用 LLM，不接受候选提供的快照作为独立原件。

## 准入和顺序

新 Task MD 显式声明：

```yaml
scoring_runtime:
  research_sources: true
```

私有 GT 同时包含 `research_source_policy.json`。原 prepare 后、run-rules 和 prepare-semantics 前执行：

```bash
"<frozen-python>" -X utf8 <score-skill>/scripts/score_general_e2e.py collect-research-sources \
  --attempt-root /absolute/private-attempt --curl /usr/bin/curl
```

collector 使用 curl 默认 TLS 校验，禁用用户 curlrc，不使用 `--insecure`。每一跳仅接受无控制字符/用户密码的 HTTP/HTTPS；拒绝 localhost、非 global unicast 地址和混合公网/私网 DNS 结果。解析后以 `--resolve` 钉住已验证地址，核对 curl 的实际 remote_ip，手动跟随最多10次重定向，每跳重新核验。生产没有放开私网的参数。为防代理另行 DNS 绕过地址绑定，获取禁用代理；只能经代理访问的环境明确报供证失败。

它保存重定向和必要响应头、请求/最终 URL、每跳验证/连接地址、UTC 访问时刻、原始响应字节和 SHA；网络阶段需要可信 curl。PDF 完整逐页提取需要评分 CLI 的 Python 已具备 pypdf，不向已有规则 Worker 安装依赖。UTF-8 HTML 用不执行脚本的标准库正文投影；普通 UTF-8 文本也可使用。

该命令只创建一次性 `private/research-sources/` 和 `research-sources.lock.json`，不改原 attempt manifest、GT、候选或 runtime/workspace。已创建来源锁、已运行 Worker 或已准备语义目录时拒绝重收集。网络失败不封存成功锁，单独留下 research-source-failure 回执；可在进入评分前重试尚未封存的获取。已封存输入需要变更时使用新的评分 attempt。

旧任务未声明开关则不需要来源包；没有开关却附带来源锁/目录会拒绝。开关为 true 而缺 policy、缺锁或缺来源文件时阻断依赖它的评分，不补零。普通 verify 允许 prepare 后尚未收集；一旦来源锁存在，verify 也复核它。

## policy v1

最小必需字段：

```json
{
  "schema_version": "wildclawbench.research-source-policy/v1",
  "ledger_path": "results/source_ledger.json",
  "deliverable_paths": ["results/findings.xlsx", "results/source_ledger.json", "results/answer.md"],
  "as_of_inclusive": "2026-09-30",
  "timezone": "Asia/Shanghai"
}
```

可选字段及默认值：

| 字段 | 默认值 |
|---|---|
| sources_key / source_id_key / url_key | sources / source_id / url |
| access_status_key / collect_statuses | access_status / [read_full, read_excerpt] |
| citations_key / citation_id_key | citations / citation_id |
| quote_key / locator_key | quote / locator |
| max_sources | 40，允许 1–1000 |
| max_bytes_per_source | 20971520，最高 67108864 |
| timeout_seconds | 60，最高 300 |

不接受未知字段、绝对/越界/GT候选路径或域名白名单。ledger_path 必须包含在 deliverable_paths 中。固定时点字段用于保留契约；collector 不从它自动推断发布身份或历史可得性。

ledger 根为对象，sources 为数组。source_id 为任意非空、唯一的稳定字符串；citation_id 在账本中唯一。每个 source 的 citations 是对象数组，原 citation 内容随独立来源保存，引用正确性由题内规则/Judge 判断。access_status 命中 collect_statuses，或者具有任何引用，都会独立获取；未读且无引用的搜索候选不获取。URL 必须为不带用户密码的 HTTP/HTTPS。错误 URL 保留 candidate_invalid；不在私有参考池中的 URL 仍按同样方式获取。

所有声明交付都记录 exists/SHA；文件、账本与引用跨文件一致性由题内规则核验。采集器不替候选补 ledger 或寻找预期答案，也不执行候选程序。超过获取预算明确报错，不静默只取前 N 个。

## bundle、锁及规则接口

来源包 manifest 的 schema 为 `wildclawbench.research-source-bundle/v1`。它包含 acquisition_identity、created_at、bindings、规范化 policy、candidate_input_status、errors、sources、collector_sha256、collector_python 和 `historical_publication_verified=false`。

bindings 含 candidate_sha256、policy_sha256、deliverables（path/exists/sha256）。candidate_input_status 为 valid、missing_ledger、invalid_ledger；后两者证明候选交付缺陷，来源列表为空，仍可交给原 rubric 合法失分。sources 中有效条目的 status 为 acquired，无效 URL 为 candidate_invalid；未读搜索候选不列入收集 sources。

acquired 条目提供 source_id、url、citations、reason=null、source_path、body_path/body_sha256、text_path/text_sha256、projection_path/projection_sha256、receipt_path/receipt_sha256、media_type、final_url。所有路径相对于来源包根；四种文件与所有成员均受锁约束：

- body.pdf/html/txt：独立响应原始字节，不重编码。
- response.json：requested_url、final_url、http_status、redirect_count、responses（每次 URL/status/必要 headers）、started_at/finished_at（UTC）、media_type、body_sha256/body_size、tls_verification、fetcher（name/path/version/sha256）、collector_sha256。
- text.json：schema `wildclawbench.research-source-text/v1`，source_sha256、engine、complete=true、records、raw_metadata。PDF records 使用 `{locator:{page:N},text:...}`；HTML/文本使用 `{locator:{record:1},text:...}`。PDF 引擎绑定 pypdf 版本、入口和包内容 SHA；原 PDF metadata 只作原字段记录。
- text.txt：同 records 内容，保留 `[page N]` 或 `[record N]` 标记，供分页查询与规则引用。

补充锁 schema 为 `wildclawbench.research-source-lock/v1`，绑定当前 identity、原 attempt_manifest_sha256、bindings、bundle_path、bundle_manifest_sha256、完整 entries（path/size/sha256）、acquisition_identity 与 parent_lock。GT 与候选不因新增锁而改变。rescore 复制原包，写绑定新 attempt 的新锁，parent_lock 保留原锁及原获取身份，不重新获取网页。

Worker 只额外获得两个专用环境变量，core IPC 和 grade 函数签名不变：

```text
GENERAL_E2E_RESEARCH_SOURCE_BUNDLE=<absolute bundle directory>
GENERAL_E2E_RESEARCH_SOURCE_BUNDLE_SHA256=<manifest.json SHA256>
```

规则应先核 manifest SHA，再读取已校验的来源与确定性定位；不自行联网或调用模型。逐项 rule evidence 引用来源锁及来源包文件；rule-audit 另记录来源包/锁摘要，语义目录登记同一包原件、投影和回执。语义 Judge 必须通过 query-evidence 实际阅读所引用的正文、元数据及反例，不能只查目录或 URL。

API Judge 若预算未能完整送入锁、来源清单、关键 text.txt 和 response.json，入口报 `RESEARCH_SOURCE_API_INPUT_INCOMPLETE`，不把被省略来源当已读。该门禁不自动证明语义判断正确，也不替代完整题目材料的供证。

## 正常、离线与归档验证

成功来源目录和锁设为只读；哈希验证不依赖 Unix mode，跨机器时使用相对路径重新解析。规则分、语义目录、合分来源锁及 verify-score 都验证同一来源树。私有目录可随现有回传包保留，顶层 runtime 可省略。

正常验证检查本版本 collector 源码，并用本机锁定提取器重新提取正文，比对投影和引擎身份；它不重抓网页，也不要求原 curl 路径仍存在。curl/获取机 Python 的版本、可执行文件 SHA 保留为获取时观察。离线执行评分须提供已封存来源包及匹配提取依赖。可以在在线评分侧 prepare/collect 后，把整个 attempt/独立 Skill ZIP 搬到离线机器。

`verify-score --archived` 不要求 curl、pypdf 或原解释器存在：核对原件、投影、回执、完整成员、候选/GT/attempt绑定与 text.json→text.txt 的一致性，并复核合分。此模式信任原取证阶段封存的提取回执，不声称在归档机重新证明投影忠于 PDF。库/脚本变化不能覆盖旧冻结入口；使用对应发行工具复核原 attempt。

## 失败与证明边界

缺/坏 ledger、悬空引用、无效 URL 或缺候选文件属于可观察的候选交付缺陷，由原规则和 rubric 计分。有效 URL 获取失败、404/403/429、网络/地区/证书限制、预算不足、空壳/扫描件/不支持的文本编码或提取依赖缺失属于评分侧供证不全，不返回能力零分。规则本身没有逐项 unresolved 协议时，应在 Worker 前以错误阻断。缺件能证明候选未交付时，也不能强行下载标准答案补交。

该版本不执行动态浏览器/OCR，不判正文对主张的语义支持，不把 HTTP 日期、URL 年份或 retrieval_at 当历史发布证明。200 登录/挑战页面可能产生非空文本，须由题内规则/独立 Judge 核实文档身份。需要历史身份时使用绑定原件的独立发布记录/版本 oracle，并为池外合法来源保留同标准判定或 unresolved。

SHA 证明封存后未漂移；可信独立 collector 是互联网来源的信任边界。候选原快照或 trace 工具返回不自动成为独立获取证据。独立重新获取到相同字节是合法情况，不能仅凭字节相同否定独立性。来源包同样不能单独证明候选实际读过正文；行为主张须结合完整绑定轨迹。
