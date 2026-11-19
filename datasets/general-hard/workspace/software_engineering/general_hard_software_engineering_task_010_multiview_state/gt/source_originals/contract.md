# 查询与状态契约（h050/v1）

仅可修改 project/api.py、project/store.ts、project/view.ts；其他输入原路径原字节保护，新文件只写 results。数据原创合成、离线。Python 为无 IO 纯函数；读取 profile.py 的支持范围。TypeScript 为同步 JSON 函数，仅这两个模块彼此相对导入（./store.ts 或 ./view.ts），可用原生可擦除 TS 类型；无包、FS、网络、process、动态导入、定时器、Promise/async 或外部模块。内部结构、辅助函数、不可变/局部缓存可自行选择。原生 VM 不是 OS 安全沙箱，合法但超出支持 profile 的源码保留 typed 未评估。

## API

query_records(records, query, snapshot_version) 返回 query/items/total/counts/page/pageSize/lastPage/version。records ID 唯一，status 可为 pending/approved/rejected，createdSeq 整数；排序为 (createdSeq,id) 升序。查询 status 不在 all/pending/approved 时回退 all；term 非字符串变空串，只 trim ASCII 空白（空格 TAB CR LF VT FF），只转换 ASCII A-Z；匹配 title 或 owner 子串（同规则转换），中文及非ASCII大小写不转换。整数 page（不含bool）至少1，非整数回退1；pageSize 整数夹到1..10，非整数回退3。不得改输入。

先按 term 过滤全量，再统计 term 范围内的 all/pending/approved（all包含rejected，因此未必等于后两项相加）；随后按状态过滤得到 total，再分页。lastPage=max(1,ceil(total/pageSize))，实际 page=min(requestedPage,lastPage)，空结果 page=lastPage=1。query 回显规范化的**请求页**，page 是夹紧的实际页；items 为原记录全部字段，稳定顺序，version 回显 snapshot_version。

## Store

createState(initialQuery={})、reduce(state,action)、getSnapshot(state)。reduce 可返回新 state 或原地变更再返回；不修改 action，getSnapshot 返回独立 JSON 数据。getSnapshot 字段：query（规范化当前查询）、pending（当前 opaque token 或 null）、minVersion（已通知的最新提交修订，初值0）、needsRefresh（初值false）、error（null或request_failed）、data（null或完整API响应，可保留旧缓存）。可附加私有字段，评分只观察上述协议和**可用数据**，不绑定内部清空/缓存策略。不同 Store 实例互不污染。

request={type:'request',token,patch}：token由调用方给出且每次唯一，patch合并当前query后规范化；status/term/pageSize任一规范值改变时 page 重置1（即使patch也指定page），仅page改变则保留该页。pending=token、needsRefresh=false、error=null；等待时旧缓存不可见。

resolve={type:'resolve',token,result}：只有token等于非null当前pending、result.query逐字段等于当前规范请求query、result.version>=minVersion时才接受，否则完全忽略。接受后pending=null、needsRefresh=false、error=null，query.page采用result.page（服务器夹紧），data保存响应。可用数据匹配时只比较status/term/pageSize和data.page==当前query.page；data.query.page可能是夹紧前请求页，不能因此误判。

invalidate={type:'invalidate',event_id,revision}：重复event_id或revision<=minVersion不改变可观察状态；event_id只在该实例去重。新修订更新minVersion并取消pending；若现有数据版本>=revision且匹配当前查询，则无需刷新，否则needsRefresh=true。提交是服务器按修订顺序发生，通知可以乱序/重复；version=N快照包含先前全部提交。不能要求客户端知道尚未通知的未来提交。

reject={type:'reject',token}：只有当前非null pending的token匹配才生效，pending=null、error=request_failed、needsRefresh=true；旧失败忽略。下一次request清掉error。

## View

present(snapshot) 返回 query,rows,total,counts,pageCount,loading,needsRefresh,error,empty,previous,next。query为当前query，loading=(pending!==null)。有pending、有error、needsRefresh、data为空、data.version<minVersion或data与当前status/term/pageSize/实际page不符时，rows=[]、total=counts=pageCount=null、empty=false、previous=next=false（未知不冒充0/空结果）。否则 rows=data.items（全部字段）、total=data.total、counts=data.counts、pageCount=data.lastPage，empty=(total===0)，previous=(query.page>1)、next=(query.page<lastPage)。不得改snapshot输入。

## 回放与交付

fixtures/records.json 提供初始记录及按revision顺序的提交。fixtures/public_scenarios.json 是固定公开回放：request发出时记录getSnapshot.query；capture用当时服务器快照和该已发出查询调用实际api；deliver在指定顺序向实际Store注入捕获响应；commit更新服务器，notify才通知客户端。step每步用实际present取文本/状态观察。不存在真实DOM、浏览器、网络、Harness或视觉输入。

python -B -m unittest discover -s tests_public 可检查原型窄正常路径；python -B replay.py --output results/scenarios.json 用冻结Node、当前Python及三份实际源码重放两套公开情境，输出固定schema的源码SHA/夹具SHA/实际请求响应/每步view。不要写死情境答案。候选可交付失败的真实回放，其真实性与业务正确性分开；报告补行不能稀释固定公开情境义务。JSON对象键/情境行顺序、BOM、SHA大小写可等价；数组内交互步骤有序且数量固定。900秒为元数据，不是能力分墙钟阈值。
