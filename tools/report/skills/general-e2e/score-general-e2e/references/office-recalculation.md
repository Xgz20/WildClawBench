# 可信Office重算

## 标量数值中间量干预

score-general-e2e 0.22.0、core 0.14.0提供独立Profile：

```python
variant = prepare_xlsx_numeric_intervention(
    source,
    [{"sheet": "生效数据", "cell": "C7", "value": 136000}],
    evidence_root / "revenue-variant",
)
verify_xlsx_numeric_intervention(source, variant["path"], variant["audit"])
result = recalculate_xlsx(variant["path"], office_lock, evidence_root / "revenue-result")
```

适用于经规则独立核验基线值、身份及业务角色的普通标量公式和数值中间量。每步1至100个不同单元格，目标值须为现有数值协议支持的有限数（绝对值不超过1e15，非零数数量级不小于1e-15）。生成的目标格为数值类型；原公式、错误/缺失缓存、布尔或数值文本的完整原单元格XML保存在`original_cell`中。原始数值文本仅在其确为可解析数值时接受，不能把缺失标记当作数值源。

`numeric-intervention-audit.json`使用`wildclawbench.office-xlsx-numeric-intervention/v1`和`offline-xlsx-scalar-numeric-intervention/v1`，绑定父源SHA、变体SHA、完整原格与声明目标值。校验器重放原始单元格，不相信回执自己提供的历史；其它格/部件、原公式记录或目标值发生未声明变化，即使重新索引也拒绝。新Profile可与普通数值输入和二进制标记变体混用，仍按冻结来源依赖图授权，不依赖索引顺序。

这是下游计算依赖实验，不证明被覆盖公式本身正确，也不要求候选把合理的来源公式改成常量。任务必须单独核对来源提取、单位、版本和基线；只在其通过后选择真实业务中间量。共享/数组公式、处于这些公式范围的子格、元数据支持的单元格仍报`OFFICE_NUMERIC_INTERVENTION_UNSUPPORTED`，按评测运行时能力异常处理，不补为候选零分。原`prepare_xlsx_counterfactual()`继续只改字面数值，原marker Profile继续只接受0/1。

任务MD的frontmatter可声明`scoring_runtime: {office: true}`。该声明只进入私有评分契约，不要求被测端安装同一引擎，也不进入任务Env。没有声明的旧任务契约和冻结清单保持原字节。

评分core的`office_runtime.py`可逐字节复制到任务私有GT，作为标准库helper由可信规则调用。它清除全部单元格公式缓存，设置自动全量计算，调用锁定的headless LibreOffice打开并另存一次性副本。评分器读取重算副本中的值，仍可查看原件公式；不能以原件缓存替代重算，也不能禁止等价公式来规避计算。

## 冻结引擎

先准备可信的LibreOffice安装，再从Skill根运行：

```bash
python scripts/score_general_e2e.py bootstrap-office \
  --executable /absolute/path/to/soffice \
  --runtime-lock references/scoring-runtime-lock.json \
  --output /absolute/path/to/scoring-runtime-with-office.json
```

传入实际引擎程序，避免会转发到其它安装的包装脚本。命令探测版本并记录绝对路径及程序SHA，不下载或改写安装；输出不可覆盖。该锁识别程序和版本，未对安装中所有动态库逐文件锁定。正式校准仍须统一可信安装制品及平台，并在批次配置记录其身份，不能仅凭同名版本推断跨平台完全一致。

`prepare --runtime-lock /absolute/path/to/scoring-runtime-with-office.json`把组合锁冻结到attempt私有目录。后续`run-rules`或`run-api-score`自动使用它；现有编排同样可传入该组合锁。省略`bootstrap-office`的`--runtime-lock`会生成单独Office锁，可通过`run-rules --office-runtime-lock ...`显式使用；显式锁若与已冻结的组合锁冲突，执行拒绝。

## 可信规则调用

规则从Worker环境获取两个评分侧路径，不能从候选目录寻找同名配置：

```python
lock_path = Path(os.environ["GENERAL_E2E_OFFICE_LOCK"])
evidence_root = Path(os.environ["GENERAL_E2E_RULE_EVIDENCE_DIR"])
lock = json.loads(lock_path.read_text(encoding="utf-8"))
result = recalculate_xlsx(candidate_workbook, lock, evidence_root / "candidate")
# result["path"]是派生XLSX；result["audit_path"]是JSON回执。
```

每个输入使用不同且为空的输出目录。回执绑定原件、清除缓存后的输入、派生文件、引擎程序SHA与版本，记录清除数量和原件未变。Worker使用临时用户配置及白名单环境，不继承用户凭据。输出位于attempt的`worker/derived/`，保持候选和runtime初始树不变。

缺交付、空文件或无效业务内容按任务原契约处理；规则可在确认缺文件后给出相应分值，此时无需编造重算回执。依赖缺失、程序漂移、引擎超时或失败属于评分异常，不能用原缓存或人工猜测补分。外链、数据连接、宏及已识别的网络/主动公式不在此离线Profile支持范围，helper显式报错；任务制作者应在校准前处理这些兼容边界。此helper和受管Worker均不是恶意代码安全沙箱。

## 证据与验收边界

`rule-audit.json`索引派生文件的路径、大小和SHA。语义证据目录以`rule_derived_artifact`提供锁、XLSX及回执，可通过既有`query-evidence`读取单元格和定位。`finalize`及`verify-score`验证派生索引、字节、回执、引擎锁和原始候选/私有参考XLSX的SHA对应关系；业务正确性由冻结任务规则与独立Judge判断。

回传保留`worker/derived/`，仅排除runtime副本。`verify-score --archived`不要求原引擎仍存在，但继续核验锁结构与全部绑定字节，不重新计算或改写历史分数。

当前作者验证使用macOS受管LibreOfficeDev 26.8.0.0.alpha0，对H001参考原型清除20个缓存后重新保存，18个金额与独立calendar/Decimal标签一致。伪CLI回归只证明环境传递、缓存清除、原件保护和证据校验；没有据此证明真实计算正确。Windows、其它公式族、四端执行和正式语义评分仍需另行校准。

## 内嵌表格重算

score-general-e2e 0.15.0、core 0.7.0增加`read_embedded_xlsx(source_pptx, part)`与`extract_embedded_xlsx(source_pptx, part, output_dir)`。输入是普通冻结PPTX和经包内关系解析的具体XLSX部件名，不是外部URL；helper验证被动Office包并保留原始工作簿字节及缓存，不以引用路径猜测数据。

```python
original = extract_embedded_xlsx(candidate_pptx, embedded_part, evidence_root / "source")
calculated = recalculate_xlsx(original["path"], office_lock, evidence_root / "calculated")
```

提取目录保留`embedded.xlsx`和`embedded-xlsx-audit.json`，回执绑定源PPTX SHA、部件名、内嵌XLSX SHA及源未变。重算回执再绑定该工作簿的原始SHA和派生SHA。验证器只在提取回执存在时读取对应冻结PPTX的原部件，检查其与保留副本逐字节同源；重算源既可为原有独立XLSX，也可为经此验证的内嵌副本。移除提取回执、改成不存在/不同的部件、伪造父PPTX或只重新索引错误回执均不能通过。

归档保留两层文件及回执，`verify-score --archived`可在引擎不存在时检查这条链，不重新计算分数。合法等价公式仍应清缓存后真正运行；正确显示缓存不能替代实际公式结果。此操作只证明来源与计算观察，不证明图表类目、语义或可编辑应用行为；冻结任务规则与独立Judge仍须核验原生对象。

本Profile要求OPC content-type manifest有正确默认命名空间。前缀改写可能使XML仍可解析而Office无法加载；此类已识别包错误会显式报告`OFFICE_INPUT_INVALID`，不伪装成引擎可用性失败。UTF-16默认命名空间manifest同样支持。
## 数值输入扰动

score-general-e2e 0.19.0、grading-core 0.11.0支持从冻结XLSX建立可回溯的数值输入变体：

```python
variant = prepare_xlsx_counterfactual(
    source,
    [{"sheet": "Lines", "cell": "E6", "value": 2}],
    derived / "quantity-variant",
)
result = recalculate_xlsx(variant["path"], office_lock, derived / "quantity-result")
```

输入为1至100项不重复的`sheet/cell/value`编辑；只接受已存在、非公式、非布尔/文本的数值单元格，数值须有限且在支持范围内。不能用该接口改公式、插入缺失输入、修复候选或修改原始文件。目标字段必须属于题目明确允许编辑的模型输入，规则应先核对实际源参数和交付契约，再选择扰动位置；接口本身不证明该单元格具有业务意义。

`prepared.xlsx`保留原公式及其缓存，`counterfactual-audit.json`绑定源/变体SHA和每个输入的原值、新值。后续可信Office入口才清空缓存并实际重算。目录内文件不可覆盖；缺引擎、helper或回执漂移保持评测异常。候选模型缺少可编辑数值输入、写死输出或计算错误，则按该任务已冻结的业务规则评分，不擅自把环境故障计为候选零分。

语义catalog、合分和归档验证先从冻结候选或私有参考找到源工作簿，再重放声明编辑：不变部件逐字节比对，目标worksheet比对完整XML语义，仅允许声明的数值变化。ZIP压缩和XML前缀差异不决定业务正确性；修改公式、旧缓存、其它输入、样式、工作簿配置或新增部件都会拒绝。只有验证成功的变体SHA才可作为重算来源；删除变体回执、重新索引错误父源或错误原值均不能绕过来源校验。未知变体或内嵌工作簿仍不能直接冒充冻结源；0.21起，已逐层验证的连续变体可按下节协议成为父源。

作者仍须用独立计算路径比较扰动后的实际重算结果，覆盖承诺的输入与边界。该机制证明来源和实际重算链，不证明公式关系、预算口径、语义质量或目标Excel应用可用性。`verify-score --archived`无需原Office安装，但继续核验上述全部绑定字节。

## 连续变体与二进制标记干预

score-general-e2e 0.21.0、core 0.13.0支持连续派生父源。归档索引可以先列子源；验证器从冻结候选或私有GT工作簿出发，按依赖顺序重放所有变体，只有完全核验的`prepared.xlsx`才加入可信父源集合。未扎根或无法从合法父源解析的循环、同一prepared路径绑定多个变体回执、源/变体摘要漂移或未声明修改均拒绝。每个attempt最多1024个变体回执；每步普通数值编辑仍最多100处。旧单步Profile及其字面数值限制保持不变。

题级有效/命中标记可由普通标量公式计算。需要验证汇总是否依赖这些标记时，使用独立API：

```python
intervention = prepare_xlsx_marker_intervention(
    source,
    [{"sheet": "题级底稿", "cell": "E8", "value": 0}],
    derived / "marker-step",
)
verify_xlsx_marker_intervention(source, intervention["path"], intervention["audit"])
result = recalculate_xlsx(intervention["path"], office_lock, derived / "marker-result")
```

该操作是对声明中间标记的受控干预。规则必须先独立核验原始基线标记与其业务身份，再选择题面允许的字段；它不修复原候选，也不证明原标记公式正确。不能用它绕过数值输入接口的非公式限制，或将任意错误输出替换成正确值后声称候选模型通过。

每次接受1至100个不重复的sheet/cell/0或1编辑。普通标量公式可以有陈旧、错误或缺失缓存；原公式、缓存、类型与样式等单元格XML完整记录在`marker-intervention-audit.json`的`original_cell`。字面二进制数值、布尔和文本标记也可干预，文本仍输出文本、布尔仍输出布尔。变体只覆盖声明单元格的值/公式内容，所有其它单元格、包内共享字符串和部件继续核验。新回执使用`wildclawbench.office-xlsx-marker-intervention/v1`与`offline-xlsx-binary-marker-intervention/v1`，不混用旧counterfactual回执。

对整个中间标记向量做干预时，应完整声明该向量的目标格，包括当前值已经等于干预值的公式格；未被冻结的公式可能因其它标记变化而重算出新值。题目规则须独立构造完整的预期向量，不能只改当前非零项。

共享/数组公式范围（含非公式子格）及带cell/value元数据的标记当前报告`OFFICE_MARKER_INTERVENTION_UNSUPPORTED`，不隐式展开或破坏其它格。任务规则应保留此类运行时能力异常，不能据此给合法候选补零或强制其改用字面标记。新增支持需要单独Profile和真实引擎验收。纯归档重放无需Office安装；实际评分仍须固定Office清缓存并重算，独立比较干预后的完整业务结果。
