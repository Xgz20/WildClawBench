// Search/fetch cards are native presentation projections. The trajectory is
// the authoritative model call/result protocol, including any result omitted
// or reformatted by a card. Match input multiplicities; never invent a tool
// event or claim a per-result association for repeated identical inputs.
export function reconcileNativeSearchDisplays(blocks, events) {
  const groups = new Map(), results = new Map();
  for (const event of events.filter(e => e.kind === 'tool_result')) {
    const rows = results.get(event.call_id) || []; rows.push(event); results.set(event.call_id, rows);
  }
  const key = (name, input) => JSON.stringify([name, input]);
  for (const event of events.filter(e => e.kind === 'assistant_tool_call')) {
    const input = event.tool_name === 'general_search' ? event.arguments?.query
      : event.tool_name === 'web.fetch' ? event.arguments?.url : null;
    if (typeof input !== 'string') continue;
    const k = key(event.tool_name, input), group = groups.get(k) || { tool_name: event.tool_name, call_ids: [], blocks: [] };
    group.call_ids.push(event.call_id); groups.set(k, group);
  }
  for (const block of blocks) {
    if (!block.block_id || block.is_finish !== true || Object.entries(block.content || {}).some(([k,v]) =>
      !['search_query_result_block','link_reader_block'].includes(k) && !(k === 'pc_event_block' && v === ''))) continue;
    const search = block.content.search_query_result_block, fetch = block.content.link_reader_block;
    let k;
    if (block.block_type === 10025 && search && !fetch && Array.isArray(search.queries) && search.queries.length === 1
        && typeof search.queries[0] === 'string' && Array.isArray(search.results)
        && search.results.every(r => Object.keys(r).length === 1 && typeof r.text_card?.title === 'string'
          && (typeof r.text_card.url === 'string' || !Object.hasOwn(r.text_card,'url')
            && typeof r.text_card.doc_id === 'string' && r.text_card.doc_id.length > 0
            && /^(?:[1-9][0-9]*)$/u.test(String(r.text_card.index))))) {
      k = key('general_search', search.queries[0]);
    } else if (block.block_type === 10006 && fetch && !search && typeof fetch.summary === 'string'
        && (Array.isArray(fetch.items) && fetch.items.every(item => typeof item.summary === 'string')
          || !Object.hasOwn(fetch,'items') && fetch.extend_fields?.search_result_render_type === 2
            && fetch.tool_name === 'web.fetch' && typeof fetch.url === 'string')) {
      const prefix = ['已阅读内容: ','正在阅读内容: '].find(p => fetch.summary.startsWith(p));
      const explicit = fetch.tool_name === 'web.fetch' && typeof fetch.url === 'string' && fetch.url ? fetch.url : null;
      // A finished error card can retain its loading label. Its explicit URL
      // must still bind the original request; the SDK result decides outcome.
      if (explicit && prefix && fetch.summary.slice(prefix.length) !== explicit) continue;
      const input = explicit || (prefix === '已阅读内容: ' ? fetch.summary.slice(prefix.length) : null);
      if (input) k = key('web.fetch', input);
    }
    if (k && groups.has(k)) groups.get(k).blocks.push(block.block_id);
  }
  const matched_block_ids = [], matches = [];
  for (const group of groups.values()) {
    if (!group.blocks.length || group.blocks.length !== group.call_ids.length
        || new Set(group.blocks).size !== group.blocks.length || new Set(group.call_ids).size !== group.call_ids.length
        || !group.call_ids.every(id => results.get(id)?.length === 1 && typeof results.get(id)[0].content === 'string')) continue;
    matched_block_ids.push(...group.blocks); matches.push(group);
  }
  const scholarCalls=events.filter(e=>e.kind==='assistant_tool_call'&&e.tool_name==='execute_defer_tool'
    &&e.arguments?.toolName==='seed_scholar_search'&&typeof e.arguments.params?.query==='string');
  const scholarCards=blocks.filter(b=>{
    const s=b.content?.search_query_result_block;
    return b.block_type===10025&&b.is_finish===true&&b.block_id
      &&Object.entries(b.content||{}).every(([k,v])=>k==='search_query_result_block'||k==='pc_event_block'&&v==='')
      &&s?.summary==='没有搜索到相关结果'&&s.scene===1&&s.search_type===4
      &&s.extend_fields?.search_result_render_type===1
      &&Object.keys(s.extend_fields).every(k=>['search_result_render_type','thinking_idx'].includes(k))
      &&(!Object.hasOwn(s.extend_fields,'thinking_idx')||Number.isInteger(s.extend_fields.thinking_idx)&&s.extend_fields.thinking_idx>=0)
      &&['queries','results','vlm_rich_media_results'].every(k=>!Object.hasOwn(s,k)||Array.isArray(s[k])&&s[k].length===0)
      &&Object.keys(s).every(k=>['summary','scene','search_type','extend_fields','queries','results','vlm_rich_media_results','icon_url','icon_url_dark'].includes(k));
  });
  if(scholarCards.length&&scholarCards.length===scholarCalls.length
    &&new Set(scholarCards.map(b=>b.block_id)).size===scholarCards.length
    &&new Set(scholarCalls.map(c=>c.call_id)).size===scholarCalls.length
    &&scholarCalls.every(c=>results.get(c.call_id)?.length===1&&typeof results.get(c.call_id)[0].content==='string')){
    matched_block_ids.push(...scholarCards.map(b=>b.block_id));
    matches.push({tool_name:'execute_defer_tool',deferred_tool_name:'seed_scholar_search',
      call_ids:scholarCalls.map(c=>c.call_id),blocks:scholarCards.map(b=>b.block_id),
      mapping:'tool-kind multiset only; placeholder card does not determine model-result emptiness'});
  }
  return { profile: 'doubaowork-search-fetch-presentation-2.35.15/v2', matched_block_ids, matches,
    mapping: 'input-multiset; individual-result mapping is not asserted',
    model_result_source: 'original native trajectory; presentation cards do not replace tool results' };
}

export function reconcileNativePlatformNotices(blocks) {
  const text='本回答由AI生成，仅供参考，请仔细甄别，谨慎投资。';
  const matched=blocks.filter(b=>b.block_type===10053&&b.is_finish===true&&b.block_id
    &&Object.entries(b.content||{}).every(([k,v])=>k==='tips_block'||k==='pc_event_block'&&v==='')
    &&b.content.tips_block?.type===1
    &&Object.keys(b.content.tips_block).sort().join(',')==='text,type'
    &&typeof b.content.tips_block.text==='string'&&b.content.tips_block.text.trim()===text);
  if(new Set(matched.map(b=>b.block_id)).size!==matched.length)return {profile:'native-financial-platform-notice/v1',matched_block_ids:[]};
  return {profile:'native-financial-platform-notice/v1',matched_block_ids:matched.map(b=>b.block_id),
    classification:'Preserved native platform disclaimer; not a model tool call/result or an additional event'};
}

export function reconcileNativeGuiDisplays(blocks, protocol) {
  const names = new Map();
  for (const block of blocks) {
    const value = block.content?.gui_tool_block;
    if (block.block_type !== 10068 || block.is_finish !== true || !block.block_id || typeof value?.tool_name !== 'string'
        || typeof value.header?.summary !== 'string' || Object.entries(block.content).some(([k,v]) =>
          k !== 'gui_tool_block' && !(k === 'pc_event_block' && v === ''))) continue;
    const rows = names.get(value.tool_name) || []; rows.push(block.block_id); names.set(value.tool_name, rows);
  }
  const matched_block_ids = [], matches = [];
  for (const [name, ids] of names) {
    const calls = protocol.calls.filter(call => call.name === name);
    if (calls.length !== ids.length || new Set(ids).size !== ids.length) continue;
    matched_block_ids.push(...ids); matches.push({ tool_name: name, block_ids: ids, call_ids: calls.map(c => c.call_id) });
  }
  return { profile: 'doubaowork-gui-presentation-2.35.15/v1', matched_block_ids, matches,
    mapping: 'tool-name multiset; no arguments, results or additional calls are synthesized' };
}
