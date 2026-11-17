// Original display incorrectly treats page length as every total.
export function present(s: any) {
  const rows = s.data ? s.data.items : [];
  const total = rows.length;
  return {query:s.query,rows,total,counts:{all:total,pending:rows.filter((r:any)=>r.status==='pending').length,approved:rows.filter((r:any)=>r.status==='approved').length},
          pageCount:1,loading:s.pending!==null,needsRefresh:s.needsRefresh,error:s.error,empty:rows.length===0,previous:s.query.page>1,next:false};
}
