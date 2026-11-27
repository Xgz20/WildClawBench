# 晓法法律场景评测集

本集包含30道工作任务，面向企业法务与执业律师在晓法中的真实工作形态。以《产品成效价值》和《用户好评表》为主要需求来源，围绕案卷整理、诉讼分析、文书生成、合同审查、电子取证、法律交付六类各5题。目标是检验能否根据材料形成可复核、可编辑、可交接的法律工作成果。

- [30题目录](TASK_INDEX.md)
- [评分指标与验收口径](METRICS.md)
- [来源阅读、图片提取及适用边界](SOURCES.md)
- [图片逐项核对记录](evidence/primary_image_audit.json)
- [数据集注册定义](dataset.yaml)
- [逐题来源与改编记录](task_sources.yaml)
- [验证记录](VALIDATION.md)

## 格式与接入

沿用 General 的 Markdown/frontmatter、`Prompt`、`Expected Behavior`、`Grading Criteria`、`Automated Checks`、`LLM Judge Rubric`、`Workspace Path`、`Skills`、`Env`、`Warmup` 结构。`exec/`只含公开输入，`gt/`含独立事实答案、判据和评分脚本。借鉴 Web 用例“前置材料—核对操作—预期结果”的验收表达；法律题不标`web-site-gen`，因为仓库该标签表示网站生成。

注册系列为`xiaofa-legal`，发布版本为`xiaofa-legal30-v1`，任务和素材位于`tasks/legal/xiaofa`与`workspace/legal/xiaofa`。全部为hybrid；L2/L3/L4均为设计预估，非实测校准。`case-library.yaml`的cli/e2e表示使用现有入口选题，不代表已经完成任何客户端端到端验收。

```bash
python tools/report/skills/validate-eval-dataset/scripts/validate_eval_dataset.py \
  --dataset-id xiaofa-legal --fail-on review
python -m eval_general_e2e.datasets.bundle build \
  --dataset-id xiaofa-legal --output /tmp/xiaofa-legal30-v1.dataset.zip
python -m eval_general_e2e.datasets.bundle verify \
  --bundle /tmp/xiaofa-legal30-v1.dataset.zip
python datasets/legal/xiaofa/authoring/check_controls.py
```

运行正式评测时，通过既有CLI/E2E选择器选`xiaofa-legal`或显式发布ID，并提供项目原有模型、执行器和judge配置。不同执行器仍需具备Word、PDF、图片、二维码和视频读取工具；不能因执行器未安装解码器就把多模态输入改成文字答案。示例bundle是执行和评分分离的分发包，不可把其中gt提供给被测Agent。

## 内容与范围

所有题内交易、客户身份、聊天、视频、门户和合同均为自建合成数据。真实用户原件、头像、姓名、账号、联系方式和私有案卷不入库；仓库保留来源URL、段落/单元格定位、原图哈希、脱敏内容摘记和改编理由。官方指导案例180号单独标明真实来源。

每题都有实际输入材料与独立参考判据，不以空附件、待下载链接或模型自评代替。短视频为16秒无声合成屏幕录制，测时间定位、画面文字和上下文保留，不测语音识别或长视频性能。法院领取和网页取证为离线模拟，不测真实平台登录、验证码、网络、线上批量下载或司法存证。X06与X10用固定历史记录测信息利用和结论修正，不测真实多轮追问。

现有30题是可复现的v1基准，不覆盖原材料中152字段全量登记、200页以上大卷宗、13049条历史案件导入或全年产品运营指标的规模测试。六类等配额用于初版回归，不声称代表线上使用频率。

冻结表示任务内容、输入和评分契约的版本锁定，不表示已获法律专家认证或被测模型已经达标。律师对法律判据的独立复核、真实Agent试跑、judge一致性与运行成本标定是下一轮验收事项。修改冻结内容须发布新版本，不能覆盖v1锁。
