# 晓法法律30题验证记录

验证日期：2026-11-27。发布ID：xiaofa-legal30-v1。

## 已完成

- 仓库静态校验：30题，通过`--fail-on review`。检查题面/frontmatter、必需章节、评分key和权重、能力映射、来源登记、Workspace/exec/gt、全量统计与素材引用。
- 评分作者控制：30题、246项断言通过；包括结构正例、空输出、错误事实、错误来源/哈希、改动输入、缺交付、损坏JSON、缺GT异常传播，以及合同正文不变与指定批注修订。
- 15份DOCX输入使用运行时内置LibreOffice渲染15页并逐页检查。初次Songti字体出现缺字，改用Noto Sans SC并去除Title样式残留边框；最终正文、表格和编号可读。批注另检OOXML锚点、关系与内容。
- 3份PDF输入解析、文本抽取及逐页渲染检查通过。
- 6份PNG可解析并逐张检查；2个二维码由独立zxing-cpp解码器验证出两个不同URL。系统Vision解码器在本机ANE计划创建失败，改用zxing-cpp通过，没有据生成字符串直接宣布二维码可用。
- 2段16秒MP4完整解码，共320帧；检查全部8个不同画面，争议片段起点与反证上下文可定位。均无音轨，本版不测ASR。
- 两份主材料23个图片位置逐一查看，含22个不同图片哈希，另读1份Word附件；原始图片和私有附件未提交仓库。

结果明细见[evidence/control_results.json](evidence/control_results.json)、[evidence/asset_qa.json](evidence/asset_qa.json)和[evidence/qr_decode_check.json](evidence/qr_decode_check.json)。冻结后构建及验包结果另记在`evidence/bundle_verification.json`。

## 结果含义

控制测试的正例使用结构测试替身，验证的是评分逻辑，不是30份法律参考成稿。它不代表模型已完成题目，也不能证明法律判据已经律师审核。图像语义、司法适配、原生文档视觉效果及严重错误需要正式运行中的独立评审。

本次未启动真实模型或客户端，不产生模型准确率、通过率、耗时或费用结论。未访问真实法院、未上传案卷、未发送或提交任何文书。未做律师盲审、judge一致性测量和难度标定；这些限制已同步记录在来源、任务和指标文档。
