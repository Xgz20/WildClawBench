# 配置兼容迁移合同 v1

只修改project/config.py。三层配置优先级严格为defaults < project < user；None层表示该层缺失，根层非dict且非None抛ValueError。API保持migrate_config(config)以及merge_configs(defaults,project=None,user=None,*,with_audit=False)。不读取环境变量、磁盘用户配置或网络，不引入其它默认值。所有值为JSON树。

## 单层迁移（先逐层迁移，再合并，不能先合并旧键后改名）
已知旧键：timeout_ms→network.timeout_seconds（非bool有限非负数字除以1000）；retry_count→network.retries（非bool非负int）；cache_enabled→cache.enabled（bool）；workers→pipeline.workers（非bool非负int）；output_dir→output.directory（str，可为空串）。所有已知旧值也允许None并原样迁移为显式null。这些旧顶层键迁移后移除；不要删除任何其它未知键，包括未知嵌套dict、list、false、0、null和空对象。

同一层若目标新叶已存在，即使值为0/False/空串/None，也以新叶为准；若目标祖先已显式为None，也保留该None，不用旧键复活子树。被新键遮蔽的旧值可为旧无效值，只记录ignored，不验证或回退采用它。新分组为空dict时并未提供叶，允许旧键填入缺失叶。不同旧键不互相遮蔽。先按新键规则验证本层已有已知值，再处理未被遮蔽的旧值；不许悄悄把无效值改回默认。

已知network/cache/pipeline/output分组必须为dict或None；其已知叶类型同迁移结果：timeout_seconds为非bool有限非负数字或None，retries/workers为非bool非负int或None，enabled为bool或None，directory为str或None。已知无效值抛ValueError；未知键不做类型改写。config_version缺省/1/2均接受（若提供须为非bool整数1或2），输出始终为2。

## 合并和重复
dict+dict递归合并，列表和标量（包括0/False/空串/None）整体覆盖；缺失键才继承低层。空dict与已有dict合并不清空其子键。高层dict覆盖低层标量/None时从空dict开始，不能复活被中间None擦掉的默认子键。例如defaults.network={timeout_seconds:30,retries:2}，project.network=None，user.network={retries:0}，最终network只能是{retries:0}。

migrate_config(x)返回规范化独立副本；merge_configs(...,with_audit=False)只返回合并dict。必须保持所有输入在任意深度不变，修改返回的未知嵌套数据也不能反写输入。migrate_config(migrate_config(x))和merge_configs({}, {}, 已合并结果)稳定，不丢未知键。字典键顺序不影响结果；列表顺序与值类型有语义，不能把False和0互换。

## with_audit=True
返回{'config':规范化结果,'sources':来源字典,'migrations':事件list}。sources覆盖最终树的全部终端节点：标量、list和空dict；非空dict不单独记录。key采用JSON Pointer，~转义~0、/转义~1。普通来源为{'layer':'defaults'/'project'/'user','source_path':本层原始JSON Pointer}；通过旧键迁移的叶回指原旧键（如/timeout_ms）。config_version来源固定{'layer':'system','source_path':None}。

高层显式终端覆盖后来源也更新；空dict覆盖已有非空dict时仍记录保留的子叶来源。空dict覆盖已有空dict时，空节点来源为高层。每个出现的已知旧键保留一条migrations事件：{'layer':层名,'from':旧Pointer,'to':新Pointer,'action':'migrated','input':原值,'output':转换值}；被新叶或新祖先None遮蔽时为{'layer':层名,'from':...,'to':...,'action':'ignored','input':原值,'reason':'canonical_present'或'canonical_ancestor'}。事件顺序不限，不能漏事件或添加不存在的迁移。migrate_config自身只返回dict，不返回来源。

## 交付与验证
fixtures/configs目录每个JSON有固定case_id及defaults/project/user三层，覆盖新旧键、显式空值和未知键。project/test_public.py仅为旧接口基本兼容性，原工程也可能全绿。

执行python -B tools/run_migration_checks.py，实际生成results/migration_audit.json与results/tests.txt（后者同样JSON格式，扩展名保留.txt）。audit保留全部固定case_id的实际config/sources/migrations或错误，最终源码和全部输入SHA；tests保留实际命令、returncode、完整stdout/stderr、逐测试状态及最终源码/audit SHA。更改最终源码后须重跑。不能删失败项、写死测试或oracle结果，也不能因漏项改变分母；评分独立运行当前源码。

其它输入（包含公开测试、schema.md、fixtures、依赖锁与工具）保持原字节；不新增源码，报告仅写results。Python自动__pycache__/*.pyc可忽略。仅用Python3.11+标准库，不安装、不联网、不访问真实用户配置或账号；本题惰性合成数据不对应真实凭据。结论区分事实、推断、未知，不读取GT。
