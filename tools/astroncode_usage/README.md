# AstronCode 生产使用数据分析

`analyze_astroncode_prod_usage.py` 将生产 `agent.turn` 日志分成五层产物，一次抓取后的汇总、分类和候选用例筛选都可在本地完成。

## 产物设计

| 层级 | 格式 | 用途 | 保留建议 |
| --- | --- | --- | --- |
| 受控原始快照 | `.jsonl.gz` | 完整保留 ES hit，用于字段追溯或重新标准化 | 30–90 天，仅限受控本地存储 |
| 标准化数据 | `.parquet` | 后续分析的长期数据源 | 长期保留，按批次归档 |
| 场景分类缓存 | `.parquet` | 保存 Query 哈希、最终分类、分类方式、置信度和模型信息；不保存 Query 正文 | 与标准化数据同批次归档 |
| 分析汇总 | `.xlsx` | 查看场景、Query 长度、耗时、模型、AstronStudio/AstronCode 版本、Token、状态、日期趋势和数据质量 | 按分析批次保留 |
| 产品候选 Query | `.xlsx` | 产品筛选可转化为 WildClawBench 评测用例的 Query | 作为人工评审工作底稿 |

Excel 单工作表上限为 1,048,576 行，4 万多条可以存放。但完整 ES hit 字段宽、文本长且包含敏感数据，不适合把 Excel 作为原始存储。

## 安全与生产负载控制

- 凭据只从环境变量读取，不接受密码命令行参数，不写入任何产物。
- 忽略系统和环境代理，生产日志直连 ES 目标。
- 单线程、单连接，默认每页 500 条，每页间隔 0.5 秒。
- 使用 PIT + `search_after` 稳定分页，不产生并发请求突发。
- 429/502/503/504 使用指数退避，默认最多重试 4 次。
- 默认分析最近 30 天。命中超过 100,000 条时自动缩短到最近 14 天；两周仍超限则停止。
- 快照和 Parquet 先写同目录临时文件，完整性校验后再原子替换正式文件。
- 在 POSIX 系统上，五类产物默认设为仅当前用户可读写（`0600`）。
- 默认输出到已被 Git 忽略的 `outputs/astroncode_usage/`。不要把生产产物提交到 Git 或公开分发。
- 大模型语义分类必须显式传入 `--allow-remote-query-content`；只发送规则未命中的唯一 Query，不发送已由规则完成的 Query。
- 发送给分类模型前会自动脱敏常见凭据和个人信息，单条最多发送 2,000 字符；默认并发 2、请求启动间隔 0.5 秒。
- 场景分类缓存只保存 Query 的 SHA-256，不保存 Query 正文。分类原因也会再次脱敏并限制长度。
- 分类服务返回 400/413/422 时会拆分批次定位到单条；单条仍被拒绝时保持未分类。累计超过 10 条会中止，避免服务异常被静默掩盖。

## 依赖与环境变量

```bash
python3 -m pip install -r requirements.txt
```

配置 Elasticsearch，认证方式只能选一种：

```bash
export ES_URL='http://elasticsearch-o-00gcvdonjneh.escloud.volces.com:9200'
export ES_USERNAME='<用户名>'
read -s ES_PASSWORD
export ES_PASSWORD
```

也可使用 `ES_API_KEY` 或 `ES_BEARER_TOKEN`。索引默认为 `oc_acode-observer_prod*`，可用 `ES_INDEX` 或 `--index` 覆盖。

混合场景分类使用 OpenAI 兼容的 `/chat/completions` 接口。分类服务和模型可单独配置：

```bash
export SCENE_LLM_BASE_URL='<OpenAI 兼容接口的基础 URL>'
export SCENE_LLM_MODEL='xopglm52'
export SCENE_LLM_API_KEY_ENV='SCENE_LLM_API_KEY'
read -s SCENE_LLM_API_KEY
export SCENE_LLM_API_KEY
```

`SCENE_LLM_API_KEY_ENV` 的值是保存密钥的环境变量名。也可省略它并使用默认的 `OPENROUTER_API_KEY`；密钥本身不会进入命令行参数或产物。

Parquet 中的用户、会话、对话、Trace、Span、主机和路径等标识会使用加盐 SHA-256。为使不同批次可稳定关联，建议在受控环境设置一个长期盐值：

```bash
export ASTRONCODE_HASH_SALT='<受控的随机长字符串>'
```

若未设置，每次导出会生成一个临时随机盐。同一批次内可统计，不同批次不能直接用哈希关联。盐值本身不会写入产物。

## 执行

一次完成抓取和分析，默认最近 30 天：

```bash
python3 tools/astroncode_usage/analyze_astroncode_prod_usage.py run
```

指定起止日期：

```bash
python3 tools/astroncode_usage/analyze_astroncode_prod_usage.py run \
  --start 2026-08-15 \
  --end 2026-09-14
```

日期按 `Asia/Shanghai` 解释。`--end 2026-09-14` 包含 9 月 14 日全天；带时分秒的 ISO 8601 截止时间按该时刻排除。

只抓取快照和 Parquet：

```bash
python3 tools/astroncode_usage/analyze_astroncode_prod_usage.py fetch \
  --start 2026-08-15 \
  --end 2026-09-14
```

从本地 Parquet 重新生成两个 Excel，不访问 ES：

```bash
python3 tools/astroncode_usage/analyze_astroncode_prod_usage.py analyze \
  --input outputs/astroncode_usage/astroncode_usage_normalized_20260815_20260914.parquet
```

先生成可复用的 V3 混合场景分类缓存，同样不访问 ES：

```bash
python3 tools/astroncode_usage/analyze_astroncode_prod_usage.py classify-scenes \
  --input outputs/astroncode_usage/astroncode_usage_normalized_20260815_20260914.parquet \
  --output outputs/astroncode_usage/astroncode_usage_scene_classifications_20260815_20260914_v3.parquet \
  --allow-remote-query-content
```

分类过程会持续写入同目录的 `.checkpoint.jsonl`。任务中断后使用相同参数并增加 `--resume` 即可继续，不会重复发送已经完成的 Query：

```bash
python3 tools/astroncode_usage/analyze_astroncode_prod_usage.py classify-scenes \
  --input outputs/astroncode_usage/astroncode_usage_normalized_20260815_20260914.parquet \
  --output outputs/astroncode_usage/astroncode_usage_scene_classifications_20260815_20260914_v3.parquet \
  --allow-remote-query-content \
  --resume
```

使用 V3 分类缓存生成新的分析汇总和产品候选表，不覆盖 V1/V2：

```bash
python3 tools/astroncode_usage/analyze_astroncode_prod_usage.py analyze \
  --input outputs/astroncode_usage/astroncode_usage_normalized_20260815_20260914.parquet \
  --scene-classifications outputs/astroncode_usage/astroncode_usage_scene_classifications_20260815_20260914_v3.parquet \
  --analysis-output outputs/astroncode_usage/astroncode_usage_analysis_20260815_20260914_scene_v3_hybrid.xlsx \
  --candidates-output outputs/astroncode_usage/astroncode_usage_candidates_20260815_20260914_scene_v3_hybrid.xlsx
```

复用 V3 分类缓存，对初次“大模型未判定”且具有明确任务意图的 Query 做二次分类，
同时补充识别“继续任务”“重新执行”“再看下”等上下文依赖短指令。该命令只读取
本地 Parquet，不重新访问 Elasticsearch：

```bash
python3 tools/astroncode_usage/analyze_astroncode_prod_usage.py refine-scenes \
  --input outputs/astroncode_usage/astroncode_usage_normalized_20260815_20260914.parquet \
  --base-classifications outputs/astroncode_usage/astroncode_usage_scene_classifications_20260815_20260914_v3.parquet \
  --output outputs/astroncode_usage/astroncode_usage_scene_classifications_20260815_20260914_v4.parquet \
  --allow-remote-query-content
```

二次分类候选默认要求规范化 Query 不少于 8 个 Unicode 字符、包含明确任务动作，
且不属于上下文依赖短指令。仍使用 70% 置信度阈值。执行过程同样写入 checkpoint；
中断后使用相同参数并增加 `--resume` 即可继续。

使用 V4 分类缓存生成新的工作簿，不覆盖 V3：

```bash
python3 tools/astroncode_usage/analyze_astroncode_prod_usage.py analyze \
  --input outputs/astroncode_usage/astroncode_usage_normalized_20260815_20260914.parquet \
  --scene-classifications outputs/astroncode_usage/astroncode_usage_scene_classifications_20260815_20260914_v4.parquet \
  --analysis-output outputs/astroncode_usage/astroncode_usage_analysis_20260815_20260914_scene_v4_secondary.xlsx \
  --candidates-output outputs/astroncode_usage/astroncode_usage_candidates_20260815_20260914_scene_v4_secondary.xlsx
```

可用 `--snapshot-output`、`--parquet-output`、`--analysis-output` 和 `--candidates-output` 覆盖默认路径。

## 标准化与分析口径

- 原始快照保留完整 ES hit。Parquet 保留 Query、耗时、模型、推理强度、Token、状态、客户端和运行时字段，但不保留模型输出正文、原始用户 ID、主机名或路径。
- 日志用 `Trace ID + Span ID` 去重，缺失时回退 `_index + _id`。
- 耗时和 Token 的缺失值保留为空，不按 0 计。P50/P90/P95/P99 使用线性插值。
- Query 长度梯度为 0、1–20、21–50、51–100、101–200、201–500、501–1000、>1000。
- “版本分布”在同一 Sheet 中汇总 AstronStudio 的 `astron.desktop.version` 和 AstronCode 的 `acode.cli_version`；每个产品分别以全部去重后 `agent.turn` 为分母，缺失版本单列为“未记录”。
- 场景分类 V3 使用“高精度规则 + 上下文依赖识别 + 大模型语义分类”的单标签混合方案；V4 在复用 V3 结果的基础上增加候选筛选和大模型二次分类。16 个可解释类别及当前规则位于 `scene_categories.json`；V1/V2 规则分别保存在 `scene_categories_v1.json` 和 `scene_categories_v2.json`。
- 高精度规则命中的 Query 直接分类；规则未命中的 Query 才交给大模型做整体语义判断。V4 对初次“大模型未判定”、规范化长度不少于 8 个字符、包含明确任务动作且不属于上下文依赖的 Query 做二次分类。
- 两轮分类均使用 0.70 置信度阈值。模型仍未判定、低于阈值、不满足二次候选条件、属于上下文依赖或为空的 Query，最终归为“未分类”。
- 分类只使用当前 Query。空 Query，以及“继续”“按照上面调整”一类缺少独立场景信息的续接、指代和通用短指令保持未分类；不会根据不可见的前文猜测场景。
- 分析汇总中的“分类方法”会分别统计规则、大模型、上下文依赖、大模型低置信度、大模型未判定、大模型二次分类、大模型二次低置信度和大模型二次未判定，便于审计两轮分类覆盖情况。
- 调整规则时应修改版本号并保留最后一个无关键词的兜底分类。分析不同规则版本时使用不同 Excel 文件名，避免覆盖历史结果。
- 产品候选 V1 按 Unicode NFKC、合并空白和不区分大小写做精确去重，不做语义聚类。
- 候选 Query 会自动脱敏常见凭据、邮箱、IP、身份证、手机号和用户主目录，并防止 Excel 公式注入。自动脱敏不替代产品入选前的人工复核。
- Query 超过 Excel 单元格 32,767 字符上限时，候选表保留可见前缀并在脱敏状态中标记“Excel已截断”。完整原文仍在受控 Parquet 中。
