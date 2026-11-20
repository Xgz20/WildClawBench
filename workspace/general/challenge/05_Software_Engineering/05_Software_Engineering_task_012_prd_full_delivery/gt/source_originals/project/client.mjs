// Prototype optimistically fabricates rows instead of consulting the backend.
export function createController(transport) {
  const model={actor:null,rows:[],form:{},error:null,loading:false};
  return {async load(){model.rows=[{id:'fake',name:'Demo',email:'demo@example.test',role:'admin',status:'active',version:1}];},
    async submit(operation,payload,key){model.form={};model.error=null;},snapshot(){return JSON.parse(JSON.stringify(model));}};
}
export function render(model){return '<table><tbody>'+model.rows.map(r=>'<tr data-id="'+r.id+'"><td>'+r.name+'</td></tr>').join('')+'</tbody></table>';}
