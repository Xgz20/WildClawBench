# 预约导入契约 1.3

只修改project/store.py，Python 3.11+、sqlite3标准库。保持create_schema(conn)、import_batch(conn,batch,*,fail_after=None)及BatchError公开API。输入、公开测试及本契约不可修改；数据库用于本题临时演示和独立测试，不连接真实数据库或账号。

## 业务结构与约束

people(id TEXT PRIMARY KEY, name TEXT NOT NULL)，rooms(id TEXT PRIMARY KEY, capacity INTEGER NOT NULL)，bookings(id TEXT PRIMARY KEY, person_id TEXT NOT NULL, room_id TEXT NOT NULL, seats INTEGER NOT NULL)。create_schema可重复调用，保留这三个公开表的列/类型/主键，不得增加任何外键声明、表、触发器或用改schema绕过应用校验；可增加普通索引。不要提交调用者尚未提交的事务。

batch恰含people/rooms/bookings三个list，允许为空，JSON字段顺序任意。每条record必须恰含上列字段。所有id及关联id匹配ASCII `[a-z][a-z0-9_-]{0,31}`，不修剪/改写。name必须为strip后非空字符串，保存原文。capacity、seats必须为正JSON整数，不接受bool/浮点数。

按people→rooms→bookings处理，各组保持列表顺序。相同id及全部业务字段相同视为已存在，不写库、计入skipped；同批相同记录重复也如此。相同id但字段不同为E_ID_CONFLICT，不能覆盖既有记录。每条booking的person和room须在当前库（含本批已处理父记录）存在。每个room已保存及本批新booking的seats总和不得超过capacity；同id重试不再占座。

## 事务、错误和故障注入

成功返回且只返回`{"inserted":{"people":P,"rooms":R,"bookings":B},"skipped":{...}}`，均为非负整数、按输入记录计数。没有调用者事务时，成功批次须已提交并可从独立连接读到。有调用者事务时，成功后该事务仍打开，调用者可整体rollback；import_batch不得提交调用者的先前写入。失败仅回滚本批更改，调用者先前写入和事务可继续使用。不要用无条件conn.commit()/conn.rollback()破坏外层事务。

所有业务/注入错误抛BatchError，其code、entity、index属性可读；index为该实体list内从0开始的索引。错误同时存在时，按以下顺序选择，选择后整批回滚：

1. fail_after不是None或非负int（bool不算int）：E_CONFIG，entity=batch、index=None；优先于batch结构。
2. batch根字段/类型非法：E_SCHEMA，batch/None。
3. fail_after=0：在本批任何修改前抛E_INJECTED，batch/None。
4. 按组、记录顺序逐条检查：record字段结构错误E_ROW；字段值错误E_FIELD；同id业务字段冲突E_ID_CONFLICT。booking再依次检查person存在E_PERSON、room存在E_ROOM、总座位上限E_CAPACITY。entity和index指向当前记录。不能以SQL报错/错误字符串代替这些公开业务错误。
5. fail_after为正N时，完成第N次实际INSERT之后立即抛E_INJECTED，entity/index指向这条记录；全部插入均回滚。skipped不推进计数。如果实际insert数不足N，不注入。即便N恰好等于全部新记录数，也须失败回滚。

失败的部分父表写入、最后一条booking写入、错误日志或重试状态均不能残留在业务表中。实现可采用等价SQLite事务策略，但须满足本题所有调用者事务边界。

## 演示与交付

fixtures/batch.json给出people、rooms、bookings的合成演示批次。请在独立临时数据库实际运行：首次导入、完全相同的重试、缺失person关联失败、fail_after=2注入失败。用查询记录每一步之前/之后的三个表数据、成功返回或BatchError属性，写入results/db_audit.json。表记录按id排序，people/rooms/bookings各为SQL列顺序的二维数组，不能只记录行数。

db_audit.json根字段为source_sha256和steps；source_sha256是最终store.py字节SHA-256。steps为上述四步，按顺序包含label、before、after、result；label依次为first/retry/orphan/injected。result为成功计数字典，或`{"error":{"code":...,"entity":...,"index":...}}`。orphan步骤使用fixtures内orphan批次，injected使用fixtures内injected批次。四步在同一个新临时数据库上顺序执行；故障批次不得影响之前成功记录。

在project执行`python3 -m unittest -v test_public`，将原始stdout/stderr及实际命令、退出码和最终源码SHA写入results/tests.txt；文本前三行固定为`source_sha256=<64位SHA>`、`returncode=<整数>`与`command=<实际命令的JSON字符串数组>`，后续保留实际日志。失败也如实记录。允许Python生成__pycache__，其它新文件只写results，临时演示DB放系统临时目录或results。禁止联网和依赖安装。
