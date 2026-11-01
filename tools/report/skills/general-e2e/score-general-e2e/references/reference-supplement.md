# 独立参考补证

仅支持codex-agent-judge-v1的新rescore，且语义请求尚未生成。使用相同冻结执行、原题、原参考、候选、轨迹与裁判配置；本层是评分端新增来源，不能计作候选行为。来源不足时保持unresolved，不按期望分数筛选材料。

先在独立研究目录保存公开来源及必要的文本提取结果。每份材料写清其类型和限制：正文、公开附录、作者稿、公开引用上下文或二次引述。来源URL必须为HTTPS；文件相对输入JSON所在目录定位，不能越界或经过符号链接。输入JSON示例：

```json
{
  "schema_version": "wildclawbench.general-e2e-reference-supplement-input/v1",
  "task_id": "original-task-id",
  "source_score_sha256": "原score.json的64位SHA256",
  "documents": [{
    "name": "source.txt",
    "path": "source.txt",
    "sha256": "文件的64位SHA256",
    "size": 123,
    "url": "https://publisher.example/article",
    "retrieved_at": "2026-11-01T00:00:00+00:00",
    "kind": "publisher_public_appendices",
    "description": "仅公开附录，未获取受订阅限制的主文。"
  }]
}
```

`kind`可选publisher_full_text、publisher_public_appendices、publisher_metadata、author_manuscript、citation_context_excerpt、secondary_citation、research_note或original_source_binary。二进制PDF可与按页提取的UTF-8文本一起登记，在description记录二者关系及页码；不得静默清洗、截断或宣称OCR绝对准确。每份64MiB、总计128MiB，最多16份；这些是新增参考层资源上限，不改变原业务取证预算。

用冻结CLI登记：

```text
python scripts/score_general_e2e.py register-reference-supplement --attempt-root ABS --source-manifest ABS --authorization-reference "直接人类补证与独立重评分授权的引用"
```

新目录只读发布；相同输入幂等，其他冲突拒绝。全部材料和来源清单进入正式语义目录、查询审计与请求锁。完成后使用原prepare-semantics、query-evidence、record-semantics、finalize及verify-score流程。归档后不依赖原研究目录；补证漂移或不在冻结目录内均拒绝。旧attempt无此目录时行为不变。
