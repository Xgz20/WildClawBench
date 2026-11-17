# H038 恢复契约

输入source_tree的60份文件、partial_archive中的受控中断副本、manifest.tsv旧部分登记及state.json检查点都只读。检查点只是声明，不能当作已完成证据。不要修改或删除任何输入，不跟随其它路径/链接，不联网。

## 身份与真值
幂等key=source_tree以下相对路径的Unicode NFC形式，区分大小写，不用basename、序号或SHA代替key。相同内容但不同key仍是两份独立对象。source_tree当前原字节与SHA256是最终权威。原始partial_archive/<key>是中断副本；旧manifest的路径/哈希/状态不能证明副本正确。不要按旧表中的越界路径打开文件。来源key必须来自实际source_tree，不存在或路径不安全的表项忽略并报告；partial_archive的非来源孤儿只报告、不导入结果，也不删除原件。

## 初始状态纠正
逐key计算partial_archive真实字节SHA：相等为correct，不等为corrupt，不存在为missing；不同NFC key不可合并。对旧manifest仅统计原key匹配的记录，重复登记优先纠正。resolution按优先级：copy_state=correct且无登记为adopt_unregistered；correct且多行是dedupe_index；correct且唯一行字段/状态均有效为reuse_verified；correct但唯一登记的SHA/bytes/source_path/status不符为correct_index；corrupt为repair_corrupt；missing且有登记为recopy_missing；missing且无登记为copy_missing。所有最终副本须与source_tree哈希相等，不能仅补缺文件而保留坏hash。所有source key最终恰一行status=verified，不能续跑追加重复行。

state.claimed_complete_keys只作待验证集合。报告其错误完成key及实际已正确复制但未被检查点声明的key；state.completed_count不能代替实际correct数量。恢复前观察值与最终60完成值分别保留，不改输入state。

## 三主交付
results/archive/为60个原字节普通副本，每key独立目标，即使内容SHA相同也不能把两个key合成一个副本；不要硬链接或symlink。目标可用任意无碰撞安全archive/...路径，不要求固定文件名。results/manifest.tsv是UTF-8/BOM、tab分隔，列key/source_path/archive_path/sha256/bytes/status；source_path含source_tree/，archive_path相对results的archive/...或/tmp_workspace/results/archive/...。列/行重排、中文列键/十六进制大小写/整数等价均可；中文列键为幂等键/原路径/归档路径/内容哈希/字节数/状态。key/source_path可用NFC/NFD等价，SHA必须实际对应文件。

results/recovery.json含initial、files、final、input_sha256。initial包含source_count、initial_copy_verified_count、partial_file_count、initial_manifest_row_count、duplicate_index_keys、ignored_manifest_rows（1起数据行号，不含表头）、orphan_partial_paths（相对partial_archive）、claimed_complete_keys、false_complete_keys、unclaimed_verified_keys、checkpoint_declared_complete_count、observed_complete_before_resume。files逐key包含key/resolution/initial_copy_state/initial_index_row_count/source_sha256/initial_archive_sha256（missing=null，不填0）。final包含verified_count、unique_keys、archive_file_count、complete=true、missing_keys=[]、corrupt_keys=[]。input_sha256绑定本题全部原输入原字节。中文键可直译，顺序不限；允许不影响这些事实的解释字段，但不可把推断或未知填成已完成。

## 可重调辅助入口
另交results/resume_entry.json和本地自包含Python入口，入口文件名称自由。描述符为{"api":"h038-resume/v1","language":"python","script":"任意相对results脚本.py","args":[]}；可给固定字符串args数组。实际调用为python -I -S <script> --workspace <隔离工作区> [args...]。入口必须只读该workspace内上述输入，只在其results写；从原受控中断副本重建、从已交付结果重跑、从结果中被再次损坏的副本/重复索引修复都应正确。不得依赖当前宿主绝对路径、GT、网络、用户目录或pip。脚本只是恢复验收辅助，主要交付仍副本/索引/报告。

每次先检查已有结果的真实SHA/索引唯一性；完整重跑不能重复追加，坏副本即使登记完成也必须修复。初始中断分析仍描述只读原输入，不因重跑改成“全部reuse”。幂等状态定义为archive路径-字节SHA集合、规范化manifest记录集合及recovery JSON事实，忽略JSON/TSV行序、BOM、键序和十六进制/整数等价；其余解释字段也不得随重试递增。记录中不写当前时间/运行计数这种易变项。文件mtime不是完成证明，也不纳入状态相等。

## 入口执行限制
评分在隔离副本实际调用该候选入口，并记录当前候选树/脚本SHA、命令、返回码和前后原字节及语义状态；不会在原输入或原候选交付上执行。入口仅Python标准库，可导入argparse/collections/csv/hashlib/json/os/pathlib/shutil/sys/unicodedata/typing/io/stat/re/math/time/datetime/tempfile及已加载标准模块。不得使用网络、ctypes、子进程、系统命令、动态本地包或外部依赖。Python审计钩子限制读取为该副本与必要标准库、写入为副本results，禁网络/执行新进程；另有限时/资源上界。这是本地Python受限执行验收，不宣称OS安全沙箱。一般正常60小文件处理应很快；超时或入口违规属候选恢复失败，缺可信probe/helper/受管环境属评测异常，不能补0。
