# H052 接口与验收契约

仅修改 project/repository.py、service.py、api.py、client.mjs；project/__init__.py、legacy.py、app.py、index.html、夹具/公开测试/回放器/runtime/PRD/requirements 均保护，新文件只写 results。不得联网/安装/使用真实账号；本机 127.0.0.1 隔离 HTTP 是本题实际验证通道，可在随机端口启动和关闭本题子进程，不连接其他服务。Python3.11/3.12 stdlib和冻结Node已预置。执行受控作者变体不宣称OS安全沙箱。

## 服务器

app.py真实启动 ThreadingHTTPServer；--db指定SQLite，--port 0随机端口，--ready-file输出实际端口。只绑定127.0.0.1。初始库schema v1含members(id TEXT PRIMARY KEY,email,name,role,status,version INTEGER)，来自fixtures/seed.json；repository.initialize必须幂等升级user_version=2，不删除旧数据。所有模块必须实际使用传入SQLite连接，禁止内存假后端/写死夹具。initialize之后API每请求独立连接；所有写事务需BEGIN IMMEDIATE或等价串行化，版本判断/成员/receipt/audit同一事务。initialize可扩展schema，但现有members列和语义不得改变。audit公共列seq/actor/action/target/before_version/after_version/request_key，seq正整数递增。receipts表名和列沿原型。不得在helper内部提前commit造成半提交。

api.handle(db,method,path,body,actor_id)返回(status,body)。GET /health保持legacy.health原形（无鉴权）。其他路径先从DB查X-Actor：不存在401 UNAUTHENTICATED，inactive 403 INACTIVE_ACTOR，不能用body/自报role提权。GET /session返回当前public member。GET /members：q按ASCII trim/lower匹配name/email，status默认active，active/inactive/all，role默认all及admin/manager/viewer；未知筛选值400 INVALID_QUERY；按id排序，data={items,total}。GET /audit仅admin，否则403 FORBIDDEN；返回按seq的全部事件。GET /legacy-export调用保护legacy.export_members，data={csv}。未知路由404 NOT_FOUND。

其余body统一{ok,code,data,replayed}，成功ok=true；错误ok=false,data=null,replayed=false。POST /members执行create，PATCH /members/{id}执行update，POST /members/{id}/deactivate执行deactivate。create成功201 created，其他成功200 updated/deactivated。data是完整public member六字段id/email/name/role/status/version。actor及路由先校验，再按下述业务顺序。

create仅admin。update仅admin或manager（manager限active且非admin目标的name）；deactivate仅admin。非create先找目标，不存在404 NOT_FOUND，再权限检查；非重放的新命令不能更新/重复停用inactive目标，409 INACTIVE_MEMBER（receipt判定之后）。request_key为1..64字符非空字符串。允许字段：create=id/email/name/role/request_key；update=name/email/role/version/request_key且至少一项可编辑字段；deactivate=version/request_key。额外字段、缺键、bool/非整数version、非法值均400 INVALID_INPUT（manager碰email/role先403 FORBIDDEN）。id匹配[a-z][a-z0-9-]{0,31}；name为strip后1..40字符；role三值之一；email只ASCII trim/lower，匹配[A-Za-z0-9._+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}。规范email在全库（含inactive）唯一，重复email409 DUPLICATE_EMAIL，重复id409 DUPLICATE_ID。

目标存在/当前actor和字段权限、字段规范化校验之后，有效命令先查actor+request_key receipt；fingerprint是method operation/target和**规范化有效payload**的稳定JSON（request_key本身不计，version计入）。相同命令重放原status/code/data并replayed=true，不再检查旧version、不再写/加审计；不同命令409 KEY_REUSE。receipt之前仍要查当前actor和权限，inactive actor不能借旧key重放。失败不占key。非重放更新先校验version等于当前版本，否则409 VERSION_CONFLICT，再唯一性和最后active admin约束（409 LAST_ADMIN）。成功version+1；停用status=inactive，不物理删除。last-admin约束对降级和停用都适用。每次新成功写一条audit：action=create/update/deactivate，before_version创建0其余旧version，after_version新version，其余字段取本次actor/目标/key。SQLite审计插入失败应由app返回500 INTERNAL并回滚成员和receipt，不能留下半成功。

## 前端

client.mjs无外部import，export createController(transport)、render(snapshot)。transport是async(method,path,body)→{status,body}，由真实HTTP适配层注入；调用方固定actor。controller有async load()、async submit(operation,payload,key)、snapshot()。load依序GET /session和GET /members?status=all；成功后snapshot为{actor,rows,form,error,loading,permissions}，permissions={create:actor.role==='admin'}，rows来自实际列表完整字段。submit先form=深拷贝payload、error=null、loading=true，通过POST/PATCH调用对应路由，body加入request_key（payload含id时update/deactivate从URL取id且body不带id）。失败error为服务器code、form保持，rows不变；成功清空form并重新load。load失败也显示code，不伪造成功。同步snapshot返回独立JSON数据；序列调用无需实现并发UI调度。render含table/tbody/tr[data-id]和每行name/email/role/status/version，以及data-action=rename/sensitive/deactivate的button。admin对active行三者启用；manager对active非admin行只rename启用；其他disabled。create按钮data-action=create按permissions。error显示为文本。所有用户值HTML转义，不能注入标签。这里评估实际JS控制器/HTML语义，不宣称浏览器DOM交互或视觉质量。

## 交付

运行 python -B -m unittest discover -s tests_public 检查原型基础控制；python -B acceptance.py --output results/tests.txt 实际在独立临时目录、非项目cwd启动HTTP，调用12个固定公开验收及JS控制器，关闭服务器并保留真实请求/响应/SQLite读回。tests.txt含一个fenced JSON h052-acceptance-run/v1，固定case ID/观察/result和四源码SHA/source_digest；可如实输出FAIL，真实性与业务正确性分开，额外行不能稀释既有义务。source_digest是按路径排序的四源码SHA对象紧凑JSON（sort_keys=True,separators=(',',':')）的SHA256。

results/acceptance.xlsx是原生可解析表格，单表名不限：B2 source_digest，B3 tests.txt原字节SHA256；第6行A:E表头id/priority/implementation_paths/test_ids/status，第7行起12个R01..R12唯一记录，可重排行；paths为分号分隔的允许源码路径且至少包含requirements.json的owner，test_ids为对应PUB-Rxx，status为本次真实公开PASS/FAIL。其他列自由注释，不以样式或措辞给能力分，不要求公式。不得将图片/CSV伪装为xlsx。

results/handoff.md给实际入口、依赖和未验证边界，并有fenced JSON {source_digest,tests_sha256,entrypoint:'python -B app.py --db results/demo.sqlite --port 0 --ready-file results/ready.json',real_browser:false,external_services:false}。不要声称真实Harness已运行。900为元数据，不作能力分墙钟阈值。
支持的Python imports为sqlite3/json/hashlib/re/copy/contextlib/unicodedata/collections/functools/typing/urllib.parse/future annotations和本题project模块；可用普通函数/类及SQLite API，不用外部包、动态import/exec、网络/进程或其他IO。合法但超出支持profile保留typed未评估。

评分的原生OOXML读取profile支持ZIP包最多1000项、解压合计10MiB；正常12行追踪不接近此限。超限合法工作簿保留typed未评估，不作候选零分。

权限澄清v2：manager的active目标限制属于当前授权，必须在receipt之前检查；目标已停用时返回403 FORBIDDEN，即使同key曾有成功rename。409 INACTIVE_MEMBER适用于已经通过当前权限校验的非重放新命令（例如admin更新停用目标）。
