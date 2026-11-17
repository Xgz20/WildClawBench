// Original prototype; it accepts every response and filters its cached page.
export function createState(initial: any = {}) {
  return {query: {status:'all',term:'',page:1,pageSize:3,...initial}, pending:null,
          minVersion:0, needsRefresh:false, error:null, data:null};
}
export function reduce(state: any, action: any) {
  if (action.type === 'request') {
    const query = {...state.query,...action.patch};
    const data = state.data && {...state.data,items:state.data.items.filter((r:any)=>query.status==='all'||r.status===query.status)};
    return {...state,query,pending:action.token,data,error:null};
  }
  if (action.type === 'resolve') return {...state,pending:null,data:action.result};
  if (action.type === 'reject') return {...state,pending:null,error:'request_failed'};
  return state;
}
export function getSnapshot(state: any) { return JSON.parse(JSON.stringify(state)); }
