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
        && search.results.every(r => Object.keys(r).length === 1 && typeof r.text_card?.url === 'string' && typeof r.text_card?.title === 'string')) {
      k = key('general_search', search.queries[0]);
    } else if (block.block_type === 10006 && fetch && !search && typeof fetch.summary === 'string'
        && fetch.summary.startsWith('已阅读内容: ') && Array.isArray(fetch.items)
        && fetch.items.every(item => typeof item.summary === 'string')) {
      k = key('web.fetch', fetch.summary.slice('已阅读内容: '.length));
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
  return { profile: 'doubaowork-search-fetch-presentation-2.35.15/v1', matched_block_ids, matches,
    mapping: 'input-multiset; individual-result mapping is not asserted',
    model_result_source: 'original native trajectory; presentation cards do not replace tool results' };
}
