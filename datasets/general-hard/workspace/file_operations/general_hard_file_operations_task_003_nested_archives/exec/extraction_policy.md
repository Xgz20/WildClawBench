# H037 受限提取规范

只读archives下六个ZIP和本文。压缩包都是原创惰性测试数据，归档成员即使越界/像链接也只是测试文本，不执行、不创建链接、不访问其目标。不要对原始归档直接extractall。

## 根与身份
目标只能是/tmp_workspace/results/staging。六个根归档固定编号：A01=archives/team-a/资料.zip；A02=archives/team-b/资料.zip；A03=archives/03-legacy.zip；A04=archives/04-path-boundaries.zip；A05=archives/05-limits.zip；A06=archives/06-nesting.zip。顶层容器depth=0，成员在各容器中央目录原始顺序从1编号，宽4位。member_id为容器编号.0001，嵌套子成员继续追加.0001，不按文件名或哈希合并。container_id为父容器ID。保留原中央目录raw_name_hex和当前容器原字节archive_sha256证据。

## 名称与边界
UTF-8标志bit11置位时严格UTF-8解码；未置位时本题明确按GB18030解码，不按默认CP437猜。编码不合法则reject/name_encoding，decoded_name=null，不解压。成功解码后NFC归一。任何NUL、反斜杠、绝对路径、盘符前缀、空组件、点/点点组件均reject/path_escape，目录末尾的一个/可去掉再检查。__nested__保留目录组件（不分大小写）不得来自归档普通路径，reject/reserved_path。Unix符号链接类型一律reject/link_type；不创建链接，不读取目标。先名称、路径、类型，再限制；坏成员不影响后续条目。

## 目标与冲突
顶层容器根为staging/<归档相对archives路径去掉最后.zip>，所以team-a/资料与team-b/资料分开。普通文件的目录组件做NFC并lower()，原basename做NFC且保留大小写；输出basename固定加mNNNN__前缀，NNNN为该容器成员原序号。例如容器内docs/a.txt第2项为<容器根>/docs/m0002__a.txt。同名、Unicode等价名和大小写名都不能覆盖；同容器此前见过NFC/lower等价原路径的文件，reason_code=collision_renamed，其它正常文件为ok。目录成员action=directory，目标为容器根/小写归一目录，actual_bytes=0、actual_state=complete、sha256=null。如目标有文件/目录类型冲突必须拒绝target_conflict，不可覆盖。

嵌套ZIP按实际PK签名字节识别，不由.zip后缀决定。可展开成员action=expand，reason_code=ok，目标子容器根固定为<当前容器根>/__nested__/mNNNN，容器字节不另保存为普通文件，递归成员保留完整ID链。文件名像.zip但内容为普通文本，按普通文件提取。

## 限制与观察
普通成员声明/实际上限4096字节；有ZIP签名的子容器声明/实际上限8192字节；最大子容器depth=2。深度超限先reject/depth_limit，不读取或猜其内部成员。每个顶层归档已接受的完整解压字节总额最多12288（包含子ZIP容器本身及其被接受子成员，深度优先、中央目录顺序累计；拒绝和目录不计）。声明长度超过对应单项上限reject/declared_size；声明长度加当前已接受总额超过12288则reject/total_budget，均在完整解压前拒绝。判ZIP类型时允许只受限观察开头4字节，不计为完整读取。

不能只相信头部长度：受限解压到上限+1即停，实际超上限reject/actual_size，actual_state=lower_bound，actual_bytes=上限+1，sha256=null，不写部分文件。实际解压完整但声明长度不符或CRC不符则reject/integrity，不写输出。工具对这类损坏项抛错且没有可信实际长度时，可如实actual_state=unknown、actual_bytes=null、sha256=null并reason_code=integrity；这是有损坏证据的合法未知，不是0，不得对正常项无理由跳过。实际完整正常项actual_state=complete、actual_bytes为实际字节数、sha256为实际原字节哈希；正常项必须提取/递归。未读的拒绝项actual_state=not_read、actual_bytes=null、sha256=null。

深度/大小/预算拒绝的子容器不继续列内部成员，不能伪造里面成员结果。审计只包含实际允许检查到的容器逐成员（拒绝子容器本身要记）；被拒绝容器在unvisited_containers中按member_id和reason_code说明。只读/未知能力不冒充成功，不执行或联网。

## 审计交付
results/extract_audit.json为JSON object，含executed=false、input_sha256（六ZIP+本文的原字节SHA）、members数组及unvisited_containers数组。members每项：member_id、container_id、member_index、top_archive、archive_sha256、raw_name_hex、decoded_name、depth、declared_bytes、compressed_bytes、action、reason_code、target_path、actual_state、actual_bytes、sha256。action为extract/directory/expand/reject；拒绝target_path=null。target_path为相对results的staging/...或等价/tmp_workspace/results/staging/...，固定根/成员命名不得任意改。原始名称可以含危险字符串，只记录，不当路径使用。unvisited_containers每项member_id/reason_code即可，不列不可知内部成员。

允许字段/成员重排、UTF-8 BOM、数值等价字符串、Unicode NFC/NFD、SHA/raw_hex大小写。中文键可直译；原因代码/动作/状态沿用本文英文枚举。原输入不移动、删除、改字节，所有新交付只放results。最终输入SHA不能证明瞬时动作，正式执行仍需真实工具轨迹。
