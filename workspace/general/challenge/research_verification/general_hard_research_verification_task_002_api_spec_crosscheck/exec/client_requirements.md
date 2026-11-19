# 接入说明核验需求

请为接入同事核对给定的实时语音转写标准版官方文档，整理连接、鉴权、音频、结束与响应、错误处理和授权边界，修正旧说明。仅交付原生表格、修订说明和来源账本，不编写或运行转写客户端，不调用真实业务/付费API，不登录账号，不使用任何真实凭据。

只读本地三份输入：本需求、legacy_integration.md、official_entry.json。官方入口和本题取证快照身份见official_entry.json。可以直接fetch或浏览，不要求搜索调用；仅沿同官方文档子树读取相关正文，不能把其他产品/SDK、博客或搜索摘要当成该接口规范。抓取日期和自建snapshot ID不能冒充官方版本或发布日期。

核对10个主题：T01产品/连接/文档身份，T02握手参数和凭据放置，T03签名构造，T04时间戳语义与文档中的时间窗口，T05音频，T06发送节奏/空闲/总时长，T07结束与响应，T08可选参数缺省/启用，T09错误码/诊断/重试边界，T10白名单和FAQ/正式参数差异。

所有新交付写入results，单份不超过5MiB，三份输入保持字节不变，不删除覆盖。完成前核对三份交付中的事实和引用一致，不在聊天里补交缺文件。

## 三份交付

1. `api_contract.xlsx`：真正可编辑、可见的原生XLSX，不含宏或外部数据连接。填写下列38个事实字段及3个本地合成签名向量。字段值可以是标量、固定record或record集合，形状在下表明示；不要用长prose代替明确值。记录型value可写清楚JSON、明确子字段列/子行；也可用10个topic对象按字段无歧义展开，不能将全部核心结果藏在一格巨大JSON、隐藏区域或图片里。Sheet名、坐标、行列次序、分表合表和辅助列不限，英文列名或清楚中文别名均可。
2. `integration_revised.md`：给同事可使用的修订说明，覆盖L01—L12，每项写问题、修订、关联field_id和citation_id；解释冲突/未知/本地策略及后续确认。文档规定、建议、示例推导、工程解释与自定客户端策略要分开，不把建议升为硬限制，不声称服务实测或专家认证。正确结构不能代替真实解释。
3. `sources.json`：记录实际读取来源和来源状态、必要短原文与定位。顶层sources、limitations；可以有searches/navigation但不强制搜索。sources各项至少source_id/url/access_status/accessed_at/title/citations，access_status为read_full/read_excerpt/search_only/unavailable；每个citation含唯一citation_id、locator对象和quote。HTML定位到实际标题/锚点/逻辑表格行，区分HTTP获取时间和官方文档日期；引用ID在表和说明中一致。片段必须能回查实际原文，不能用自己写的网页快照自证；未读、仅摘要、单源、来源冲突及无法确认之处明确标注。多个URL不自动成为独立统计/规范来源。

事实表可以使用topic_id、field_id、value、status、unit、requirement_strength、citation_ids列；推荐一个field_id一行，record与集合保持明确类型。若同一record有已知及未知leaf，status=mixed并保留未知leaf是合理表达。整行缺失不等于确认未知；未知使用真正null、空单元格加明确未知状态，或清楚未知标记，绝不能当成数值0。单位清楚的Hz/kHz、ms/s、bit/byte等价换算接受；没有单位歧义的整数仍保持整数。值的事实含义优先于表示样式。

枚举词汇及别名帮助统一交接，词汇池包含合理备选，不代表哪项是官方答案；对应中文的清楚等价表达也接受，不必机械抄编码。来源未给出的版本、日期、限制或默认数值保留未知，不能从相邻产品、示例、控制值或自己的实践补成“文档规定”。

## 本地合成签名核算

三组输入都明显合成、没有真实账户/服务授权。固定ts只作数学输入，不检查它是否当前可登录，也不得改成当前时间或向真实服务发送URL。依据实际官方构造，离线计算md5_hex、signa_base64、signa_urlencoded；结果写入原生签名表，不要求在Excel中实现密码算法，也不要求交付代码。不得把官方示例中的密钥复制为配置。Base64与URL编码须区分，保留字符与大小写，不用未经说明的URLsafe变体或重复编码。

## 字段与类型契约（不含事实答案）

```json
{
  "facts_columns": [
    "topic_id",
    "field_id",
    "value",
    "status",
    "unit",
    "requirement_strength",
    "citation_ids"
  ],
  "fields": [
    {
      "topic_id": "T01",
      "field_id": "service.product",
      "label_zh": "产品与接入形态",
      "value_type": "enum",
      "value_shape": "string"
    },
    {
      "topic_id": "T01",
      "field_id": "connection.endpoint",
      "label_zh": "地址与协议",
      "value_type": "record",
      "value_shape": {
        "recommended": "url",
        "also_documented": "url"
      }
    },
    {
      "topic_id": "T01",
      "field_id": "connection.host_policy",
      "label_zh": "域名或固定IP策略",
      "value_type": "enum",
      "value_shape": "string"
    },
    {
      "topic_id": "T01",
      "field_id": "document.version_state",
      "label_zh": "正式版本与日期",
      "value_type": "record",
      "value_shape": {
        "version": "string|null",
        "publication_date": "date|null",
        "revision_date": "date|null"
      }
    },
    {
      "topic_id": "T02",
      "field_id": "handshake.required_query",
      "label_zh": "必填握手参数与类型",
      "value_type": "record_set",
      "value_shape": [
        {
          "name": "string",
          "type": "string"
        }
      ]
    },
    {
      "topic_id": "T02",
      "field_id": "auth.api_key_placement",
      "label_zh": "apiKey用途与放置",
      "value_type": "enum",
      "value_shape": "string"
    },
    {
      "topic_id": "T02",
      "field_id": "query.encoding",
      "label_zh": "Query编码范围",
      "value_type": "enum",
      "value_shape": "string"
    },
    {
      "topic_id": "T03",
      "field_id": "signature.base_string",
      "label_zh": "签名原串构造",
      "value_type": "record",
      "value_shape": {
        "ordered_terms": "string[]",
        "separator": "string"
      }
    },
    {
      "topic_id": "T03",
      "field_id": "signature.md5_representation",
      "label_zh": "MD5中间值表示",
      "value_type": "enum",
      "value_shape": "string"
    },
    {
      "topic_id": "T03",
      "field_id": "signature.hmac_inputs",
      "label_zh": "HMAC算法与输入",
      "value_type": "record",
      "value_shape": {
        "algorithm": "string",
        "key_role": "string",
        "message_role": "string"
      }
    },
    {
      "topic_id": "T03",
      "field_id": "signature.final_encoding",
      "label_zh": "最终签名编码",
      "value_type": "enum",
      "value_shape": "string"
    },
    {
      "topic_id": "T04",
      "field_id": "timestamp.semantic",
      "label_zh": "ts类型、单位与时基",
      "value_type": "record",
      "value_shape": {
        "type": "string",
        "unit": "string",
        "origin": "string",
        "current": "boolean"
      }
    },
    {
      "topic_id": "T04",
      "field_id": "timestamp.documented_window",
      "label_zh": "ts允许偏差和有效窗",
      "value_type": "record",
      "value_shape": {
        "clock_skew_seconds": "number|null",
        "signature_validity_seconds": "number|null"
      }
    },
    {
      "topic_id": "T05",
      "field_id": "audio.format",
      "label_zh": "音频编码",
      "value_type": "enum",
      "value_shape": "string"
    },
    {
      "topic_id": "T05",
      "field_id": "audio.sample_rate",
      "label_zh": "采样率",
      "value_type": "number",
      "value_shape": "number"
    },
    {
      "topic_id": "T05",
      "field_id": "audio.bit_depth",
      "label_zh": "位深",
      "value_type": "integer",
      "value_shape": "integer"
    },
    {
      "topic_id": "T05",
      "field_id": "audio.channels",
      "label_zh": "声道数",
      "value_type": "integer",
      "value_shape": "integer"
    },
    {
      "topic_id": "T05",
      "field_id": "audio.message_type",
      "label_zh": "音频消息类型",
      "value_type": "enum",
      "value_shape": "string"
    },
    {
      "topic_id": "T06",
      "field_id": "cadence.recommended_interval",
      "label_zh": "建议发送间隔",
      "value_type": "number",
      "value_shape": "number"
    },
    {
      "topic_id": "T06",
      "field_id": "cadence.recommended_chunk",
      "label_zh": "建议分片大小",
      "value_type": "integer",
      "value_shape": "integer"
    },
    {
      "topic_id": "T06",
      "field_id": "cadence.requirement_strength",
      "label_zh": "建议与硬限制",
      "value_type": "enum",
      "value_shape": "string"
    },
    {
      "topic_id": "T06",
      "field_id": "audio.idle_timeout",
      "label_zh": "发送空闲超时",
      "value_type": "record",
      "value_shape": {
        "threshold_seconds": "number",
        "consequences": "string[]"
      }
    },
    {
      "topic_id": "T06",
      "field_id": "session.duration_boundary",
      "label_zh": "音频总时长边界",
      "value_type": "record",
      "value_shape": {
        "source_claim": "string",
        "finite_total_seconds": "number|null"
      }
    },
    {
      "topic_id": "T07",
      "field_id": "end.message_type",
      "label_zh": "结束消息类型",
      "value_type": "enum",
      "value_shape": "string"
    },
    {
      "topic_id": "T07",
      "field_id": "end.payload",
      "label_zh": "结束消息内容",
      "value_type": "json_object",
      "value_shape": {
        "end": "boolean"
      }
    },
    {
      "topic_id": "T07",
      "field_id": "response.message_type",
      "label_zh": "服务端响应消息类型",
      "value_type": "enum",
      "value_shape": "string"
    },
    {
      "topic_id": "T07",
      "field_id": "response.envelope_types",
      "label_zh": "外层字段类型",
      "value_type": "record",
      "value_shape": "map<string,string>"
    },
    {
      "topic_id": "T07",
      "field_id": "response.data_parse",
      "label_zh": "结果数据解码层次",
      "value_type": "enum",
      "value_shape": "string"
    },
    {
      "topic_id": "T07",
      "field_id": "response.result_type",
      "label_zh": "结果最终/中间标志",
      "value_type": "record",
      "value_shape": {
        "final": "integer",
        "intermediate": "integer"
      }
    },
    {
      "topic_id": "T08",
      "field_id": "optional.lang",
      "label_zh": "lang缺省与授权",
      "value_type": "record",
      "value_shape": {
        "required": "boolean",
        "default": "string",
        "additional_languages_require_authorization": "boolean",
        "unauthorized_code": "string"
      }
    },
    {
      "topic_id": "T08",
      "field_id": "optional.trans_strategy",
      "label_zh": "transStrategy建议与缺省",
      "value_type": "record",
      "value_shape": {
        "required": "boolean",
        "recommended": "integer",
        "documented_default": "integer|null",
        "translation_requires_console_enable": "boolean"
      }
    },
    {
      "topic_id": "T08",
      "field_id": "optional.punc",
      "label_zh": "punc默认行为与过滤值",
      "value_type": "record",
      "value_shape": {
        "default_behavior": "string",
        "filter_value": "string",
        "documented_numeric_default": "number|null"
      }
    },
    {
      "topic_id": "T08",
      "field_id": "optional.role_type",
      "label_zh": "roleType默认行为与启用值",
      "value_type": "record",
      "value_shape": {
        "default_behavior": "string",
        "enable_value": "integer",
        "documented_numeric_default": "integer|null"
      }
    },
    {
      "topic_id": "T09",
      "field_id": "errors.selected_map",
      "label_zh": "指定错误码及表中处理",
      "value_type": "record_set",
      "value_shape": [
        {
          "code": "string",
          "meaning": "enum",
          "action": "enum"
        }
      ]
    },
    {
      "topic_id": "T09",
      "field_id": "errors.10110_diagnostic",
      "label_zh": "10110能否唯一定位签名",
      "value_type": "record",
      "value_shape": {
        "unique_signature_cause": "boolean",
        "table_meaning": "string",
        "handshake_example": "string",
        "faq_meaning": "string"
      }
    },
    {
      "topic_id": "T09",
      "field_id": "retry.documented_policy",
      "label_zh": "明文重试与未规定策略",
      "value_type": "record",
      "value_shape": {
        "explicit_retry_codes": "string[]",
        "max_attempts": "integer|null",
        "backoff_seconds": "number|null",
        "resume_or_replay_guarantee": "boolean|null"
      }
    },
    {
      "topic_id": "T10",
      "field_id": "ip_whitelist.rules",
      "label_zh": "白名单开关、范围与生效",
      "value_type": "record",
      "value_shape": {
        "disabled": "string",
        "enabled": "string",
        "ip_kind": "string",
        "settings_scope": "string",
        "propagation_minutes_approx": "number"
      }
    },
    {
      "topic_id": "T10",
      "field_id": "handshake.checksum_boundary",
      "label_zh": "FAQ checkSum与正式参数表",
      "value_type": "record",
      "value_shape": {
        "in_formal_table": "boolean",
        "mandatory": "boolean",
        "faq_mentions": "boolean"
      }
    }
  ],
  "signature_columns": [
    "vector_id",
    "md5_hex",
    "signa_base64",
    "signa_urlencoded",
    "citation_ids"
  ],
  "signature_inputs": [
    {
      "vector_id": "SIG-01",
      "appid": "h028-demo-app",
      "ts": "1700000000",
      "api_key": "SYNTHETIC_NOT_A_REAL_API_KEY_H028_B"
    },
    {
      "vector_id": "SIG-02",
      "appid": "H028-SYNTHETIC-app-02",
      "ts": "1700000001",
      "api_key": "SYNTHETIC_NOT_A_REAL_API_KEY_H028_02"
    },
    {
      "vector_id": "SIG-03",
      "appid": "h028-synthetic-app-03",
      "ts": "1700000010",
      "api_key": "SYNTHETIC_NOT_A_REAL_API_KEY_H028_03"
    }
  ],
  "column_aliases": {
    "topic_id": [
      "topic",
      "topic number",
      "主题编号",
      "核验主题"
    ],
    "field_id": [
      "field",
      "field key",
      "字段",
      "字段编号"
    ],
    "value": [
      "value",
      "verified value",
      "值",
      "核对值"
    ],
    "status": [
      "evidence status",
      "状态",
      "证据状态"
    ],
    "unit": [
      "unit",
      "单位"
    ],
    "requirement_strength": [
      "strength",
      "约束强度",
      "要求强度"
    ],
    "citation_ids": [
      "citation IDs",
      "引用ID",
      "引用编号"
    ],
    "vector_id": [
      "vector",
      "向量编号"
    ],
    "md5_hex": [
      "MD5 hex",
      "MD5十六进制"
    ],
    "signa_base64": [
      "Base64 signature",
      "Base64签名"
    ],
    "signa_urlencoded": [
      "URL-encoded signature",
      "URL编码签名"
    ]
  },
  "enum_vocabulary": {
    "product": [
      "rtasr_standard_websocket",
      "rtasr_llm_websocket",
      "iat_websocket",
      "other",
      "not_documented"
    ],
    "host_policy": [
      "use_domain_not_fixed_server_ip",
      "pin_fixed_server_ip",
      "either_domain_or_fixed_ip",
      "not_documented"
    ],
    "api_key_placement": [
      "signing_secret_not_documented_query_parameter",
      "query_parameter",
      "header_parameter",
      "not_documented"
    ],
    "query_encoding": [
      "urlencode_each_key_and_value",
      "encode_values_only",
      "no_url_encoding",
      "urlencode_whole_url",
      "not_documented"
    ],
    "signing_terms": [
      "appid",
      "ts",
      "apiKey",
      "signa",
      "path",
      "sorted_query",
      "MD5_hex_text",
      "MD5_raw_bytes",
      "HMAC_hex_text",
      "HMAC_raw_bytes"
    ],
    "md5_representation": [
      "32_lowercase_hex_text",
      "32_uppercase_hex_text",
      "16_raw_bytes",
      "not_documented"
    ],
    "algorithm": [
      "HMAC-SHA1",
      "HMAC-SHA256",
      "SHA1",
      "MD5",
      "other",
      "not_documented"
    ],
    "final_encoding": [
      "standard_base64_of_raw_hmac_sha1_digest",
      "base64_of_hmac_hex_text",
      "urlsafe_base64",
      "hex_text",
      "not_documented"
    ],
    "timestamp_type": [
      "string",
      "integer",
      "number",
      "not_documented"
    ],
    "timestamp_unit": [
      "s",
      "ms",
      "us",
      "not_documented"
    ],
    "timestamp_origin": [
      "unix_epoch",
      "other",
      "not_documented"
    ],
    "audio_format": [
      "pcm_s16le",
      "pcm_other",
      "wav",
      "mp3",
      "other",
      "not_documented"
    ],
    "message_type": [
      "binary",
      "text",
      "either",
      "not_documented"
    ],
    "cadence_strength": [
      "recommendation_not_exact_size_or_maximum",
      "mandatory_exact_size",
      "maximum_size",
      "minimum_size",
      "not_documented"
    ],
    "idle_consequence": [
      "error",
      "disconnect",
      "continue",
      "not_documented"
    ],
    "duration_claim": [
      "theoretically_unlimited",
      "finite_limit_documented",
      "guaranteed_unlimited",
      "not_documented"
    ],
    "json_type": [
      "string",
      "integer",
      "number",
      "object",
      "array",
      "boolean",
      "not_documented"
    ],
    "response_parse": [
      "parse_outer_json_then_result_data_json_string",
      "parse_outer_json_only_data_is_object",
      "parse_outer_json_only_data_is_plain_text",
      "not_documented"
    ],
    "language": [
      "cn",
      "en",
      "other",
      "not_documented"
    ],
    "default_behavior": [
      "return_punctuation",
      "filter_punctuation",
      "disabled",
      "enabled",
      "not_documented"
    ],
    "error_meaning": [
      "no_permission",
      "invalid_parameter",
      "illegal_parameter",
      "no_license",
      "over_authorized_connections",
      "basic_component_error",
      "audio_idle_over_15s",
      "illegal_signa",
      "no_license_or_authorization_count_full",
      "engine_error",
      "other",
      "not_documented"
    ],
    "error_action": [
      "check_authorization_apiKey_ip_ts",
      "check_required_parameters_format_encoding",
      "check_parameter_range_or_requirements",
      "check_authorized_connection_count",
      "retry_or_contact_provider",
      "check_audio_send_gap_15s",
      "retry_all_errors",
      "other",
      "not_documented"
    ],
    "whitelist_disabled": [
      "no_ip_check",
      "reject_all",
      "check_whitelist",
      "not_documented"
    ],
    "whitelist_enabled": [
      "reject_unlisted_client_ip",
      "allow_all",
      "reject_all",
      "not_documented"
    ],
    "ip_kind": [
      "public_egress_ip",
      "private_lan_ip",
      "any_ip",
      "not_documented"
    ],
    "settings_scope": [
      "per_appid_per_service",
      "shared_global",
      "per_appid_only",
      "per_service_only",
      "not_documented"
    ]
  },
  "enum_field_vocabulary": {
    "service.product": "product",
    "connection.host_policy": "host_policy",
    "auth.api_key_placement": "api_key_placement",
    "query.encoding": "query_encoding",
    "signature.base_string.ordered_terms": "signing_terms",
    "signature.md5_representation": "md5_representation",
    "signature.hmac_inputs.algorithm": "algorithm",
    "signature.hmac_inputs.key_role": "signing_terms",
    "signature.hmac_inputs.message_role": "signing_terms",
    "signature.final_encoding": "final_encoding",
    "timestamp.semantic.type": "timestamp_type",
    "timestamp.semantic.unit": "timestamp_unit",
    "timestamp.semantic.origin": "timestamp_origin",
    "audio.format": "audio_format",
    "audio.message_type": "message_type",
    "cadence.requirement_strength": "cadence_strength",
    "audio.idle_timeout.consequences": "idle_consequence",
    "session.duration_boundary.source_claim": "duration_claim",
    "end.message_type": "message_type",
    "response.message_type": "message_type",
    "response.envelope_types.*": "json_type",
    "response.data_parse": "response_parse",
    "optional.lang.default": "language",
    "optional.punc.default_behavior": "default_behavior",
    "optional.role_type.default_behavior": "default_behavior",
    "errors.selected_map[].meaning": "error_meaning",
    "errors.selected_map[].action": "error_action",
    "errors.10110_diagnostic.table_meaning": "error_meaning",
    "errors.10110_diagnostic.handshake_example": "error_meaning",
    "errors.10110_diagnostic.faq_meaning": "error_meaning",
    "ip_whitelist.rules.disabled": "whitelist_disabled",
    "ip_whitelist.rules.enabled": "whitelist_enabled",
    "ip_whitelist.rules.ip_kind": "ip_kind",
    "ip_whitelist.rules.settings_scope": "settings_scope",
    "handshake.required_query[].type": "json_type"
  },
  "enum_aliases": {
    "rtasr_standard_websocket": [
      "实时语音转写标准版WebSocket",
      "实时语音转写(标准版)",
      "标准版实时语音转写"
    ],
    "rtasr_llm_websocket": [
      "实时语音转写大模型版",
      "实时语音转写大模型"
    ],
    "iat_websocket": [
      "语音听写WebSocket",
      "语音听写"
    ],
    "use_domain_not_fixed_server_ip": [
      "使用域名，不固定服务器IP",
      "域名调用，勿指定固定IP"
    ],
    "pin_fixed_server_ip": [
      "固定服务器IP调用"
    ],
    "signing_secret_not_documented_query_parameter": [
      "签名密钥，不是文档列出的query参数",
      "仅用于生成签名，不随query发送"
    ],
    "query_parameter": [
      "query参数",
      "URL查询参数"
    ],
    "header_parameter": [
      "请求头参数"
    ],
    "urlencode_each_key_and_value": [
      "每个key和value分别URL编码",
      "键和值均进行urlencode"
    ],
    "encode_values_only": [
      "只编码值"
    ],
    "no_url_encoding": [
      "不进行URL编码"
    ],
    "urlencode_whole_url": [
      "整个URL一起编码"
    ],
    "32_lowercase_hex_text": [
      "32位小写十六进制文本",
      "小写MD5十六进制字符串"
    ],
    "32_uppercase_hex_text": [
      "32位大写十六进制文本"
    ],
    "16_raw_bytes": [
      "16字节原始摘要"
    ],
    "HMAC-SHA1": [
      "HmacSHA1",
      "HMACSHA1",
      "HMAC-SHA-1"
    ],
    "HMAC-SHA256": [
      "HmacSHA256",
      "HMACSHA256"
    ],
    "MD5_hex_text": [
      "MD5十六进制文本",
      "MD5小写hex字符串"
    ],
    "MD5_raw_bytes": [
      "MD5原始摘要字节"
    ],
    "HMAC_hex_text": [
      "HMAC十六进制文本"
    ],
    "HMAC_raw_bytes": [
      "HMAC原始摘要字节"
    ],
    "standard_base64_of_raw_hmac_sha1_digest": [
      "原始HMAC-SHA1摘要的标准Base64",
      "HMAC-SHA1原始字节再标准Base64"
    ],
    "base64_of_hmac_hex_text": [
      "HMAC的hex文本再Base64"
    ],
    "urlsafe_base64": [
      "URL安全Base64",
      "URLsafe Base64"
    ],
    "hex_text": [
      "十六进制文本"
    ],
    "unix_epoch": [
      "Unix纪元",
      "Unix时间戳时基",
      "1970-01-01 00:00:00 UTC"
    ],
    "s": [
      "秒",
      "seconds"
    ],
    "ms": [
      "毫秒",
      "milliseconds"
    ],
    "us": [
      "微秒",
      "microseconds"
    ],
    "string": [
      "字符串"
    ],
    "integer": [
      "整数"
    ],
    "number": [
      "数字",
      "数值"
    ],
    "object": [
      "对象"
    ],
    "array": [
      "数组"
    ],
    "boolean": [
      "布尔值"
    ],
    "pcm_s16le": [
      "16bit小端有符号PCM",
      "PCM signed 16-bit little-endian",
      "s16le PCM"
    ],
    "binary": [
      "二进制",
      "二进制消息",
      "binary message"
    ],
    "text": [
      "文本",
      "文本消息",
      "text message"
    ],
    "either": [
      "二者均可"
    ],
    "recommendation_not_exact_size_or_maximum": [
      "建议值，非精确大小或上限",
      "推荐分片，未规定必须恰好或最大值"
    ],
    "mandatory_exact_size": [
      "必须恰好该大小"
    ],
    "maximum_size": [
      "最大分片大小"
    ],
    "minimum_size": [
      "最小分片大小"
    ],
    "error": [
      "报错",
      "返回错误"
    ],
    "disconnect": [
      "断开连接",
      "关闭连接"
    ],
    "continue": [
      "继续连接"
    ],
    "theoretically_unlimited": [
      "理论不限",
      "音频流长度理论无限制"
    ],
    "finite_limit_documented": [
      "明确规定有限总时长"
    ],
    "guaranteed_unlimited": [
      "保证不限时长"
    ],
    "parse_outer_json_then_result_data_json_string": [
      "先解析外层JSON，再解析结果data内的JSON字符串",
      "外层JSON解析后对结果data二次JSON解析"
    ],
    "parse_outer_json_only_data_is_object": [
      "仅解析外层，data直接为对象"
    ],
    "parse_outer_json_only_data_is_plain_text": [
      "仅解析外层，data是普通文本"
    ],
    "cn": [
      "中文",
      "中文及中英混合"
    ],
    "en": [
      "英文"
    ],
    "return_punctuation": [
      "返回标点",
      "保留标点"
    ],
    "filter_punctuation": [
      "过滤标点"
    ],
    "disabled": [
      "默认关闭",
      "不开启"
    ],
    "enabled": [
      "开启"
    ],
    "no_permission": [
      "没有权限",
      "无权限",
      "illegal access"
    ],
    "invalid_parameter": [
      "无效参数",
      "invalid parameter"
    ],
    "illegal_parameter": [
      "非法参数值",
      "illegal parameter"
    ],
    "no_license": [
      "无授权许可",
      "no license"
    ],
    "over_authorized_connections": [
      "超过授权连接数",
      "超过授权路数",
      "over max connect limit"
    ],
    "basic_component_error": [
      "基础组件异常",
      "basic component error"
    ],
    "audio_idle_over_15s": [
      "超过15秒未发送音频",
      "超过15秒没有向服务端发送音频数据",
      "no audio data"
    ],
    "illegal_signa": [
      "签名非法",
      "illegal signa",
      "invalid authorization|illegal signa"
    ],
    "no_license_or_authorization_count_full": [
      "没有授权许可或授权数已满",
      "无授权许可或授权路数已满"
    ],
    "engine_error": [
      "引擎错误",
      "engine error"
    ],
    "check_authorization_apiKey_ip_ts": [
      "检查apiKey、IP、ts等授权参数",
      "检查密钥、IP白名单和时间戳等授权参数"
    ],
    "check_required_parameters_format_encoding": [
      "上传必要参数并检查格式编码",
      "检查必填参数、格式和编码"
    ],
    "check_parameter_range_or_requirements": [
      "检查参数值是否超过范围或不符合要求",
      "检查参数范围和要求"
    ],
    "check_authorized_connection_count": [
      "检查连接数是否超过授权数",
      "确认授权连接数或路数"
    ],
    "retry_or_contact_provider": [
      "重试或向服务提供商反馈",
      "重试或联系服务商"
    ],
    "check_audio_send_gap_15s": [
      "检查是否超过15秒没有进行音频发送",
      "检查音频发送间隔是否超过15秒"
    ],
    "retry_all_errors": [
      "所有错误都重试"
    ],
    "no_ip_check": [
      "不校验IP",
      "IP不限"
    ],
    "reject_unlisted_client_ip": [
      "拒绝未列入白名单的调用方IP",
      "检查调用方IP在白名单内，否则拒绝"
    ],
    "allow_all": [
      "全部放行"
    ],
    "reject_all": [
      "全部拒绝"
    ],
    "check_whitelist": [
      "检查白名单"
    ],
    "public_egress_ip": [
      "公网出口IP",
      "外网IP",
      "公网IP"
    ],
    "private_lan_ip": [
      "局域网IP",
      "内网IP"
    ],
    "any_ip": [
      "任意IP"
    ],
    "per_appid_per_service": [
      "不同Appid的不同服务分别设置",
      "按应用和服务分别设置"
    ],
    "shared_global": [
      "全局共用配置"
    ],
    "per_appid_only": [
      "仅按应用设置"
    ],
    "per_service_only": [
      "仅按服务设置"
    ],
    "not_documented": [
      "未知",
      "未注明",
      "未规定",
      "文档未说明"
    ],
    "other": [
      "其它",
      "其他"
    ],
    "apiKey": [
      "api_key",
      "API Key",
      "API key"
    ]
  },
  "boolean_aliases": {
    "true": [
      "是",
      "true"
    ],
    "false": [
      "否",
      "false"
    ]
  },
  "status_enum": [
    "documented",
    "document_example",
    "implementation_interpretation",
    "not_documented",
    "client_policy",
    "not_tested",
    "mixed"
  ],
  "strength_enum": [
    "required",
    "recommended",
    "optional",
    "example",
    "not_stated",
    "client_policy"
  ]
}
```
