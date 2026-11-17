# 离线SSE重放合同 v1

只修改project/stream.py、state.py、render.py。fixtures/events.jsonl每行是一组独立合成request_id及有序steps；没有网络、真实对话或真实账号。保护工具tools/replay.py执行真实字节重放和基础公开测试，输出results/replay.json。其它源码、夹具、合同、依赖锁均保持原字节，不增添源码模块。仅Python3.11+标准库。

## transport与SSEDecoder
SSEDecoder.feed(chunk:bytes)->list[{'id':str,'event':str,'data':str}]。用增量UTF-8严格解码，支持任意跨块字符、首字符BOM、LF/CRLF/CR及跨块换行。字段按首冒号分隔，最多去掉值开头一个空格；注释行(:开头)、retry及未知字段忽略。多行data用单个换行连接，data字段即使为空也计入一行；空行只在至少有data字段时派发。event缺省/空串为message，每条记录派发后重置event/data；id按SSE规则持久到下一记录，含NUL的id字段忽略。不得按chunk充当完整event。close()丢弃未完成UTF-8、行和记录，不派发、不视为完成；close后不得继续feed，重连创建新decoder。样例输入皆为有效UTF-8字节或断开前缀，不要求网络重试定时器。

## 应用事件与会话
state.new_state(request_id)返回内部状态（结构不限）；state.apply_event(state,envelope)、mark_disconnected(state)、mark_reconnected(state)均返回新/更新状态，允许内部可变，但先前交付的snapshot/render不得随以后事件改变。

应用data为JSON对象，当前request_id下必须有非空envelope.id、正整数seq（bool不算）、kind。body/reasoning带str text，分别原样追加至独立通道；done显式正常结束；error带str code/message并失败；cancel取消。其它kind/无效JSON/当前请求无效结构导致failed，error固定{'code':'invalid_event','message':'invalid_event'}。有效JSON且request_id不同则完全忽略，不占本请求去重ID/序号。

seq从1开始，只有连续前缀可应用；未来序号先缓冲，缺口填上后按seq顺序排空。future done不能提前成功。last_seq只指实际已应用的连续前缀，不能取见过的最大seq。重复event ID的同一规范化JSON payload忽略；相同seq即使换ID，只要payload相同也忽略。当前非终态下同ID或同seq对应不同payload均failed/invalid_event。JSON空格/键顺序差异不算payload冲突。

done/error/cancel应用后进入succeeded/failed/cancelled终态，后续事件、断开或重连均不得改终态或正文；error保留其code/message，done/cancel的error为None。seq完整的body/reasoning本身不等于完成。断开只把非终态改为interrupted，保留已输出正文/推理、连续游标、已收完整事件及去重记录；mark_reconnected只把interrupted恢复streaming，不重置历史。decoder的半条记录不能跨连接保留；重连会重新发完整帧。

snapshot(state)返回可JSON序列化的独立观察值，至少包含request_id/status/body/reasoning/last_seq/done/error。status初始streaming，done只在succeeded时为True。render.render_state(state)至少返回markdown(原样body)、reasoning(独立原样推理)、status、completed(仅succeeded)、error；不能把推理覆盖正文，不能把Markdown片段重写或把中断/失败/取消标成功。

## 真实重放与交付
steps的open创建新decoder并mark_reconnected，bytes按hex传入feed，对同块每个派发事件依次apply并立即保留snapshot；disconnect调用close与mark_disconnected。每步也保留state/render观察值，最后再序列化全部前缀，故共享同一可变snapshot对象会暴露中间状态错误。每个事件、字节step和断开/重连的前缀均有语义，不允许只重建最终文本。

运行python -B tools/replay.py生成results/replay.json：保留固定scenario_id的每步decoded/events后的states、step末state/render、final/final_render，以及最终三源码SHA、events输入SHA、真实公开测试命令/returncode/stdout/stderr/逐测试结果。改完最终源码须重跑。不得漏场景改变分母、写死观察结果或仅自述已运行；基础公开测试原工程也可能全绿。

报告仅写results，自动__pycache__/*.pyc可忽略。离线、不安装、不访问真实账号或外部服务，不读取GT；结论区分事实、推断、未知。内部结构和合法等价实现不限，额外观察元数据忽略；正文/推理及状态前缀按合同核验，字典顺序无关。
