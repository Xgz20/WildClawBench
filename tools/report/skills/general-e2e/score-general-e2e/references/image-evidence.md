# 冻结图片证据

score-general-e2e 0.16.0、core 0.8.0支持独立静态图片读取、Codex图片查询及API图片内容块。保持原规则、Rubric和权重；传输通过不等于视觉判断正确，也不是四端执行或难度校准结果。

## 字节与解码

`read_image_evidence(path, expected_sha256=..., max_bytes=..., max_pixels=...)`只读PNG、JPEG、WebP及单帧GIF。评分CLI解释器需有Pillow；core初始化、普通文本评分和归档字节核验不导入Pillow。本轮开发验证使用Pillow 12.3.0，正式评分需在CLI环境预置并锁定版本。返回原文件SHA、字节数、真实格式/MIME、存储宽高、模式、EXIF方向、解码器版本及原始base64。

先验证扩展名与解码格式一致、容器完整、单帧及像素预算，再完整解码像素。默认及本实现上限为单图5,000,000字节、16,000,000像素、每边8000像素；这是本地保守门禁，不代表所有provider/model的当前上限。多帧不静默截取首帧，超限不自动缩图，EXIF方向不自动旋转。坐标以原文件存储像素为准；模型服务仍可能旋转/缩放，涉及精确坐标的任务必须另行校准。

`ImageEvidenceError`保留`IMAGE_EVIDENCE_INVALID`、`IMAGE_EVIDENCE_UNSUPPORTED`、`IMAGE_EVIDENCE_LIMIT`、`IMAGE_EVIDENCE_DIGEST_MISMATCH`和`IMAGE_EVIDENCE_DEPENDENCY_MISSING`。缺依赖和冻结SHA漂移必须阻断，不能改成候选零分。通用框架不因图片损坏直接决定业务分，须按原任务契约处理。

## Codex独立裁判

在已冻结的独立评分attempt中：

```bash
"<frozen-python>" -X utf8 <score-skill>/scripts/score_general_e2e.py query-evidence \
  --attempt-root "$PWD" --mode image --evidence-id evidence-0005
```

该命令核原件SHA及完整解码，返回`view_image_path`、宽高、格式和`pixel_inspection_required: true`；日志绑定evidence ID、来源SHA及解码器。不会向终端打印大块base64。图片是一项完整字节证据，offset只能为0。

裁判随后必须用看图工具实际打开返回的原始路径，优先保留原分辨率，在判定理由中说明实际区域/目标、支持证据及反例。若无看图工具或关键区域不可辨，保留`unresolved`。`mode image`只证明取得经核验的定位与描述，不证明人或模型看过、理解了像素；查询日志不能替代看图工具结果。仅catalog查询不能让`judged` criterion引用图片，新记录会以`SEMANTIC_IMAGE_QUERY_REQUIRED`拒绝；文字与原生文档仍走原分页查询。

## API显式开启

在原API配置中增加以下可选对象；不提供时保持原文本请求和图片元数据行为，不自动上传图片：

```json
{
  "image_input": {
    "max_images": 12,
    "max_image_bytes": 5000000,
    "max_total_bytes": 20000000,
    "max_pixels": 16000000,
    "detail": "high"
  }
}
```

以上是配置片段，须与`api-judge.md`的必需字段合并。五字段全部必填并进入冻结Judge配置。张数上限20，总原始字节上限20,000,000；单图与总量关系也校验。OpenAI transport的`detail`为`auto/low/high/original`，调用者须选择模型实际支持的值；Anthropic必须写`native`，不虚构其接受OpenAI detail参数。不自动切模型或provider。

`semantic/api-input.json`将原图片字节放到`image_attachments`，正文行只保留关联元数据。附件包含evidence ID、冻结路径、SHA、尺寸及完整base64；不挤占文本字符预算，不截成部分图片。总张数/字节超限记`image_omitted_budget`，无法解码/格式或单图超限记`image_unavailable`，均不进入`usable_evidence_ids`。视觉判断需要缺失证据时必须`unresolved`；省略不代表候选错误。缺解码依赖与SHA漂移继续阻断，不伪装成图片省略。

实际请求在图片前提供evidence ID/路径/SHA/尺寸标签，随后发送相同原字节：Anthropic为`image.source.base64`，Chat Completions为`image_url` data URL，Responses为`input_image` data URL。编码后再检查32 MB本地门禁；这不保证第三方网关或目标模型一定接受。选定provider返回不支持多模态/尺寸错误时，沿用真实失败，不降级成OCR或纯文本重判。

发送前重新对附件原字节、目录来源SHA、正文关联和尺寸/解码器元数据逐一验证。归档不需要Pillow，仍逐字节核附件与冻结文件，并对保存的每次provider请求重新比较实际body；重新计算局部哈希不能掩盖错图或丢图。网络请求回执证明发送内容，不证明模型正确解释图片。

## 协议来源与验证边界

2026-10-27核对[OpenAI图像输入说明](https://developers.openai.com/api/docs/guides/images-vision)、[Chat Completions官方OpenAPI](https://api.openai.com/v1/chat/completions)及[Claude Vision说明](https://platform.claude.com/docs/en/build-with-claude/vision)。本实现选择原字节base64，不上传Files API、不使用外部图片URL。

本地验证用自有图形fixture和loopback HTTP服务，核三种请求的真实字节、标识及归档链；响应为fixture，不是真实provider的图片理解或独立语义分。真实视觉Judge、四端图片传递及H007双标注仍须另行验收。
