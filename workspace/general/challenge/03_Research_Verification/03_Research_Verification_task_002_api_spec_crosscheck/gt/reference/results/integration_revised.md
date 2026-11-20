# 实时语音转写标准版接入修订说明

本说明针对给定标准版 WebSocket API，依据此前实际获取并完整读取的官方主文档整理为作者参考。规范事实先于参考冻结；此次组装已获授权读取冻结的作者真值，不代表候选 Harness 实跑、人工专家认证或服务验收。来源和15个短引见 `sources.json`，原始抓取完成时间为2026-10-28T09:10:44.255426+00:00；自建 `xfyun-rtasr-standard-20261028` 仅标识同字节快照。

下列“规定”指正文明确要求，“建议”保留原有强度；“示例推导/工程解释”说明字节或控制流程的解释边界；“未知”表示本次完整文章有界审阅未找到明确声明。短引仅帮助定位，结论依据相关完整段落、逻辑表格行及上下文，不能用标题短引证明某规则不存在。

## L01：产品、协议与域名

**问题：**旧稿混用了语音听写的普通HTTP调用方式，并建议固定服务IP。

**修订〔规定〕：**目标是标准版实时语音转写，通过WebSocket长连接交互。优先采用 `wss://rtasr.xfyun.cn/v1/ws`；正文也列出同host/path的 `ws://` 地址。使用域名，服务IP不固定。页首的大模型推荐链接不改变本题产品和接口。

字段：`service.product`、`connection.endpoint`、`connection.host_policy`。引用：C-title、C-requirements、C-handshake。

## L02：必填参数与凭据

**问题：**旧稿写错参数大小写，将密钥放进URL，并把FAQ中的checkSum加为必填。

**修订〔规定及表格边界〕：**正式握手参数表的必填项是 `appid`、`ts`、`signa`，三者类型均为string；使用小写 `appid`。`apiKey`用于本地签名，正式查询参数表没有列出它。FAQ确实提到checkSum，但完整参数表未列，不能据此新增必填项；这也不表示已验证服务器会拒绝一切额外参数。不要复制官方示例密钥作为配置，本题核算仅使用需求文件给定的三组明显合成输入。

字段：`handshake.required_query`、`auth.api_key_placement`、`handshake.checksum_boundary`。引用：C-handshake、C-signature、C-faq-checksum。

## L03：签名串、算法与编码层次

**问题：**旧稿改签完整路径和排序query，跳过MD5、换用SHA256，并混淆key/message及摘要字节。

**修订〔规定〕：**按顺序无分隔拼接 `appid + ts`，先做MD5；再以apiKey为key，以MD5结果为message做HMAC-SHA1，之后生成Base64签名。这里没有要求把完整路径或排序query作为该签名原串。

**示例推导/工程解释：**官方MD5示例呈现32位小写十六进制文本；本地核算使用该文本的UTF-8字节作为HMAC消息，原始HMAC摘要再做标准Base64。不要将HMAC十六进制文字再做Base64，也不要改为URLsafe Base64。该字节解释与冻结核算一致，但没有进行服务器接收验证，也不据此声称服务器必拒绝所有其他MD5大小写表示。

字段：`signature.base_string`、`signature.md5_representation`、`signature.hmac_inputs`、`signature.final_encoding`。引用：C-signature。

## L04：时间戳与未知时间窗口

**问题：**旧稿将ts写为毫秒，并虚构5分钟有效窗，再套用SDK的30分钟错误。

**修订〔规定〕：**`ts`为string，表示从1970年1月1日起到当前的秒数，即秒级Unix时间戳。

**未知及后续确认：**完整主文章、握手/签名/错误码/FAQ的相关上下文没有给出时钟允许偏差或签名有效时长，二者保留未知，不能填0。约5分钟描述的是白名单配置传播；15秒描述音频发送空闲；SDK授权的30分钟不能套入此WebSocket契约。未知不等于服务器不校验时间。生产需要具体容差时，应取得服务提供方对本接口的明确约定；不在本任务中调用业务服务探测。

字段：`timestamp.semantic`、`timestamp.documented_window`。引用：C-handshake、C-whitelist、C-upload；未知依据完整main article有界审阅，以上短引仅定位相关上下文。

## L05：音频属性

**问题：**旧稿将44.1kHz、24bit、双声道WAV/MP3作为默认输入。

**修订〔规定〕：**按文档的 `pcm_s16le` 音频准备数据：16kHz、16bit、单声道。没有依据把WAV/MP3容器或其他采样属性写为该接口支持的默认输入。

字段：`audio.format`、`audio.sample_rate`、`audio.bit_depth`、`audio.channels`。引用：C-requirements，具体支持定位到接口说明及音频格式/音频属性行。

## L06：音频消息与Query编码

**问题：**旧稿将音频Base64后用text上传，并把裸签名与重复编码视为等价。

**修订〔规定〕：**音频上传使用binary message，内容为音频二进制数据。查询参数的key和value都需要urlencode。

**工程解释：**先得到标准Base64签名，再对查询值做一次百分号编码；Base64中的 `+`、`/`、`=` 与其编码形式需要区分。不要对已编码签名再次编码，也不把整个URL一起编码。SIG-02与SIG-03的合成结果覆盖特殊字符核算，未发送到服务。

字段：`audio.message_type`、`query.encoding`。引用：C-upload、C-handshake。

## L07：发送节奏、空闲与总时长

**问题：**旧稿把建议分片升为唯一允许值和最大值，又将空闲超时当作整场时长上限。

**修订〔建议〕：**文档建议每40ms发送1280字节，发送过快可能造成引擎错误；没有把它们写成必须恰好或最大值，也未给其他节奏的精确容差。16,000×2×1×0.04=1280只是数学一致性。

**修订〔规定及边界〕：**音频发送间隔超时阈值为15秒，超时会报错并由服务端主动断开。这里未实测恰好15.000秒的比较边界。FAQ对持续音频流的总长度给出理论不限的表述，未给有限秒数；这不构成永不超时或保证无限时长的SLA。

字段：`cadence.recommended_interval`、`cadence.recommended_chunk`、`cadence.requirement_strength`、`audio.idle_timeout`、`session.duration_boundary`。引用：C-upload、C-duration。

## L08：结束消息与收尾

**问题：**旧稿用text发送结束后立即主动关闭，可能丢失尚未返回的结果。

**修订〔规定〕：**音频传完后，按文档用binary message发送JSON对象 `{"end":true}`，其中true为布尔值；不要求JSON空白完全一致。正文说明服务端持续返回结果，全部发送完后断开连接。

**工程解释：**客户端应继续接收剩余结果和结束/错误事件，不能把“已发结束标志”当作“结果已全部收到”。若先收到服务错误则按错误路径处理；本参考没有承诺无损恢复。

字段：`end.message_type`、`end.payload`。引用：C-end、C-result。

## L09：响应类型与结果解析

**问题：**旧稿把服务端消息、外层字段类型和最终标志全部颠倒。

**修订〔规定〕：**服务端结果与异常以text message返回。JSON外层 `action`、`code`、`data`、`desc`、`sid` 都声明为string，code不能写成整数。对有转写结果载荷的消息，先解析外层JSON，再解析data内的JSON字符串；started/error示例的data可为空串，不应无条件把空串当JSON解析。结果type中0为最终、1为中间。

**解释边界：**上述类型标志不自动定义完整的增量覆盖、合并或去重算法。

字段：`response.message_type`、`response.envelope_types`、`response.data_parse`、`response.result_type`。引用：C-result、C-envelope、C-flags。

## L10：可选参数的行为、控制值与授权

**问题：**旧稿把建议值、控制值当数值默认，并忽略语种及翻译授权。

**修订〔规定/建议/未知分开〕：**lang非必填，默认中文；扩展语种/方言需相应授权，未授权可报10110。翻译需在控制台开通，transStrategy建议2，但没有声明数值默认2；transType的normal默认不能移给transStrategy。punc默认返回标点，`punc=0`用于过滤；其数值默认未知。roleType默认不开启，传2开启；“默认不开启”不是明示数值0，也不是传1开启。完整参数表及文章审阅未给这几项缺失的数值默认，保留未知。

字段：`optional.lang`、`optional.trans_strategy`、`optional.punc`、`optional.role_type`。引用：C-handshake；支持位置分别为lang、transStrategy、punc、roleType的实际表格行，短引本身不承担默认值缺失证明。

## L11：错误诊断、重试和sid

**问题：**旧稿将10110单独等同签名失败，并无依据承诺三次指数退避和无损续传。

**修订〔保留来源差异〕：**10110在错误表中是无授权许可；握手失败示例的desc包含签名错误；FAQ还提到授权数已满。保留code、desc、sid与授权上下文，不能仅凭10110唯一定位签名算法。

**修订〔按表处理〕：**10105检查apiKey、IP、ts等授权参数；10106检查必填参数、格式与编码；10110保留表中对参数范围/要求的检查提示；10800检查授权连接数；16003可重试或反馈；37005检查超过15秒未发送音频。这里没有把10110的不同文字强行改成单一根因。

**未知与客户端策略：**完整错误表中只有16003明确写重试；这不意味着其他故障被一律禁止重试。全文未声明重试次数、退避秒数或续传/重放保证。sid用途是DEBUG追查，不是已证明的续传令牌。若业务另定退避或重新连接策略，必须标为client_policy并另行评估重复结果、计费与恢复行为；本参考不代定三次重试，也不保证无损重放。

字段：`errors.selected_map`、`errors.10110_diagnostic`、`retry.documented_policy`。引用：C-errors、C-signa-error、C-faq-license、C-envelope；缺失保证来自全文有界审阅。

## L12：白名单与文档身份

**问题：**旧稿强制所有调用开白名单，混淆公网/局域网、生效时间和配置范围，并将采集身份当官方版本。

**修订〔规定〕：**白名单关闭时不校验IP；开启时拒绝未列入的调用方IP。应设置公网出口IP，按不同Appid的不同服务分别设置，保存后约5分钟生效；“约”不表示精确立即生效。

**未知及身份边界：**完整主文章没有自述正式文档版本、发布日期或修订日期，保持未知。HTTPDate、Last-Modified、资源路径日期、`/v1/`端点及遥测版本都不能代替该声明。capture_id、正文摘要和抓取UTC用于绑定本题取证，不是官方发布元数据；C-title仅帮助识别页面，不证明日期缺失。

字段：`ip_whitelist.rules`、`document.version_state`。引用：C-whitelist、C-title；版本日期未知来自完整文章有界审阅。

## 本地核算与交接边界

三组SIG输入仅取自需求文件，固定ts保持原值，仅离线核算MD5、HMAC-SHA1、标准Base64和一次百分号编码，已与来源先行冻结向量一致。没有复制官方示例密钥到配置，没有登录、发真实业务或付费API请求，没有修改原数学数据；数学一致性不等于服务器验收。

表格中的38个field_id可直接使用 `sources.json` 的 `field_citations`，并按 `field_support_locators` 回到真实完整段落/逻辑行。引用短引只有清单规定的15段、共136字符；不另复制38项事实表或官方全文。时钟窗口、未声明默认值、重试和恢复保证如影响生产决策，需取得该标准版接口的进一步明确资料后再更新；不得用自定策略填成文档事实。
