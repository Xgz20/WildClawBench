# 可信Office重算

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
