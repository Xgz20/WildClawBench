# 交付结构

mapping.json为UTF-8 JSON object，含selections数组和source_images数组。source_images逐图记scene_id、image_path和原PNG的sha256；selections逐条含scene_id、source_path（含source_tree的相对路径或/tmp_workspace绝对路径）、sha256、target_path（相对results的selected_files/...或/tmp_workspace/results绝对路径）、visual_evidence对象。visual_evidence至少包含active_panel、selected_row和ancestor_chain三个证据角色，每个角色以bbox或polygon表达图像局部，ancestor_chain允许多个区域；各区域用原像素坐标或声明coordinate_space=normalized的0–1坐标，说明图像ID、可见对象和选择关系。

原始图为1800×1100；矩形用[x0,y0,x1,y1]，多边形用[[x,y],...]，坐标必须在图内并定位实际区域。可自定区域ID并建立可解析表；允许合理中文字段、UTF-8 BOM、字段/行重排和绝对映射路径。未知不得伪造，无法定位时说明范围和原因，不能对不确定对象全选。

所有35个输入保持原字节和成员；selected_files只保存正确普通副本，不创建链接或运行内容。格式与坐标本身不证明实际看图，正式运行需结合实际轨迹；本题不提供OCR文本、活动面板索引或选中路径答案。
