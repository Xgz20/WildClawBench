# 可信PPTX渲染

score-general-e2e 0.14.0、grading-core 0.6.0支持把PPTX的一次性原字节副本转换为PDF。任务私有frontmatter声明`scoring_runtime: {office: true, office_render: true}`；生成器、静态门禁和分包器验证两个boolean，`office_render: true`必须同时声明`office: true`。这些字段不进入被测端输入、Skills或Env，旧任务不增加依赖。

## 冻结Office与字体

先按[可信Office重算](office-recalculation.md)生成Office程序锁，再从本Skill根运行：

```bash
python scripts/score_general_e2e.py bootstrap-office-render \
  --office-runtime-lock /absolute/path/to/office-runtime.json \
  --font-file /absolute/path/to/ChineseFont.ttf \
  --font-directory /absolute/path/to/office-install/fonts/truetype \
  --runtime-lock references/scoring-runtime-lock.json \
  --output /absolute/path/to/scoring-runtime-with-rendering.json
```

正式命令沿用已冻结的评分CLI解释器前缀。`--font-file`与`--font-directory`可重复，至少提供一份可用字体；支持TTF、OTF、TTC，合计最多512个文件、16个目录。目录内字体成员及每份字体的路径、大小、SHA均冻结，新增、删除或替换会拒绝正常运行。应把Office自带字体目录纳入清单，不能假定设置一份CJK字体后就没有其它回退字体。

输出为新的Python/runtime组合锁，保留`office_runtime`并增加`office_render_runtime`。独立渲染锁为`wildclawbench.office-render-runtime-lock/v1`，嵌套原Office锁；两者的Office身份必须一致。原XLSX锁的schema与Profile不变，已有GT helper和冻结attempt按原契约使用。`prepare --runtime-lock`冻结组合锁，新任务在启动Worker前检查渲染依赖；不从候选目录读取同名配置。

字体文件只在受管临时目录使用，不复制进候选、正式exec/gt或数据集发行包。程序锁与字体清单不逐文件冻结Office全部动态库、平台及其它系统资源；正式校准仍须统一并记录可信安装制品和平台。字体名可能发生替换，任务还要核对实际PDF字体与规定字体的关系，不能把清单本身当作全部字形已正确呈现的证明。

## 可信规则调用

```python
root = Path(kwargs["workspace_path"])
lock = json.loads(Path(os.environ["GENERAL_E2E_OFFICE_RENDER_LOCK"]).read_text(encoding="utf-8"))
derived = Path(os.environ["GENERAL_E2E_RULE_EVIDENCE_DIR"])
result = render_pptx_pdf(root / "results/annual.pptx", lock, derived / "annual")
```

helper可作为同SHA的`office_runtime.py`复制到私有GT并通过`runpy`读取。它校验被动PPTX及嵌入XLSX，用原字节副本渲染，不先修订图表或重算嵌入缓存。宏、其它OLE嵌入和外部数据/素材超出本Profile，显式拒绝；普通超链接不会被点击。格式或任务交付问题由冻结规则按原业务契约分类，不能把缺交付和缺渲染环境混为一谈。该helper不是恶意代码安全沙箱。

渲染在临时用户配置、字体副本和Fontconfig目录中运行，不继承用户凭据。固定导出包含隐藏幻灯片、排除备注页；源文件不改，`rendered.pdf`及`render-audit.json`不覆盖已有文件。回执记录PPTX/PDF SHA、源声明页数、Office程序身份、渲染锁摘要、字体资产、导出选项与操作边界。PDF实际页数、文字溢出、字号、颜色和图表结论仍须独立检查。

## 证据与验证

Worker把两个运行时锁及`worker/derived/`派生文件加入证据。语义catalog、合分、回传和`verify-score`核验源PPTX属于冻结候选或私有参考、PDF SHA及回执与锁一致。仅重新索引被篡改回执，不能使错误源、字体或导出选项通过。缺交付可以没有PDF回执，由任务原规则计分；缺引擎、字体漂移、超时或转换失败不补能力零分。

`verify-score --archived`不要求原引擎和字体仍存在，但继续检查完整锁结构及全部绑定字节，不重新渲染或改变旧分数。PDF文本查询仍要求**冻结评分CLI解释器**具备pypdf；转换用的规则Worker可只用标准库。文字提取不等于视觉检查，API文本包不能证明遮挡、图像含义或原生可编辑性。

当前macOS作者验证通过实际受管LibreOfficeDev 26.8.0.0.alpha0渲染仓库一份现有4页PPTX，锁定一份CJK字体与127份Office内置字体。原件未变，实际4页PDF、页文本与字体名已独立核对，全部4页已渲染为PNG检查。另将末页设为隐藏的QA变体仍导出4页、包含该页文字，8段仅在备注中的文字未进入PDF。伪转换器回归只验证运行时、依赖和归档绑定，不证明版式正确。尚未据此完成H005素材、GT、独立语义评分、四端兼容或难度校准。
