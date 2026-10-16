/** Read only the persisted current-device work directory in the verified 2.32.4 UI. */
import {sha256Text,workspaceReadbackMatches} from './lib.mjs';
import {homedir} from 'node:os';

export const PROJECT_DIRECTORY_SOURCE_SHA256='42509c53ecae5694fa1f1f085180f1a8047d6fc977604efd81123f17a8db4b5d';

export function verifyProjectDirectory(snapshot,projectId,workspace) {
  if(snapshot.source_sha256!==PROJECT_DIRECTORY_SOURCE_SHA256)throw Error('DOUBAOWORK_PROJECT_DIRECTORY_PROFILE_UNSUPPORTED');
  if(snapshot.project?.projectId!==projectId||!snapshot.deviceId||snapshot.loading!==false||snapshot.failed!==false)throw Error('DOUBAOWORK_PROJECT_DIRECTORY_NOT_READY');
  const folders=snapshot.project.folders?.filter(f=>f.folderDeviceId===snapshot.deviceId&&f.isPrimary===true)??[];
  if(folders.length!==1||folders[0].projectId!==projectId||!workspaceReadbackMatches(folders[0].workspace,workspace,homedir()))throw Error('DOUBAOWORK_PROJECT_DIRECTORY_MISMATCH');
  return {path:folders[0].workspace,source:'native-project-store-current-device-primary-directory',
    project_id_sha256:sha256Text(projectId),device_id_sha256:sha256Text(snapshot.deviceId),
    project_version:snapshot.project.version??null,folder_version:folders[0].version??null,
    source_sha256:snapshot.source_sha256,observed_at:new Date().toISOString()};
}

export async function readProjectConfigurationDirectory(page,{section,more,projectId,projectName,workspace}) {
  // Close only the menu opened by this exact project's verified trigger.
  const menuId=await more.getAttribute('aria-controls');
  if(!menuId)throw Error('DOUBAOWORK_PROJECT_DIRECTORY_MENU_UNBOUND');
  const menu=page.locator('[id='+JSON.stringify(menuId)+']');
  if(await menu.count()!==1)throw Error('DOUBAOWORK_PROJECT_DIRECTORY_MENU_AMBIGUOUS');
  await menu.press('Escape');await menu.waitFor({state:'hidden',timeout:5000});
  const home=section.getByRole('button',{name:'项目主页',exact:true});
  if(await home.count()!==1)throw Error('DOUBAOWORK_PROJECT_DIRECTORY_HOME_AMBIGUOUS');
  await home.evaluate(e=>e.click());
  await page.waitForURL(url=>url.pathname==='/chat/workspace/'+projectId,{timeout:10000});
  const main=page.locator('main'),config=main.getByText('项目配置',{exact:true});
  if(await main.count()!==1||await config.count()!==1)throw Error('DOUBAOWORK_PROJECT_DIRECTORY_CONFIG_AMBIGUOUS');
  await config.click();
  const buttons=main.getByRole('button',{name:/^查看工作目录：/u});
  await buttons.first().waitFor({state:'visible',timeout:10000});
  const witnesses=await buttons.evaluateAll((elements,id)=>elements.map(element=>{
    let f=element[Object.keys(element).find(k=>k.startsWith('__reactFiber$'))];
    let primary=false,loading=null,failed=null,project=null,deviceId=null,source=null;
    for(let level=0;f&&level<16;level++,f=f.return){
      const props=f.memoizedProps||{};
      if(props.item)primary=props.item.isPrimary===true&&props.item.isCurrentDevice===true;
      if(Array.isArray(props.items)&&'loading' in props){loading=props.loading;failed=props.failed;}
      if(props.projectId!==id||typeof f.type!=='function')continue;
      let hook=f.memoizedState;
      for(let index=0;hook&&index<50;index++,hook=hook.next){
        const value=hook.memoizedState;
        for(const state of [value,value?.value,value?.[0]]){
          const record=state?.projectsById?.[id];
          if(record){project={projectId:record.projectId,version:record.version,folders:record.folders?.map(folder=>({
            projectId:folder.projectId,folderDeviceId:folder.folderDeviceId,isPrimary:folder.isPrimary,workspace:folder.workspace,version:folder.version}))};source=f.type.toString();}
          if(state?.deviceId)deviceId=state.deviceId;
        }
      }
    }
    return {primary,loading,failed,project,deviceId,source};
  }),projectId);
  const candidates=witnesses.filter(w=>w.primary);
  if(candidates.length!==1)throw Error('DOUBAOWORK_PROJECT_DIRECTORY_PRIMARY_AMBIGUOUS');
  const snapshot=candidates[0];snapshot.source_sha256=sha256Text(snapshot.source||'');delete snapshot.source;
  const proof=verifyProjectDirectory(snapshot,projectId,workspace);
  // Return to a fresh draft in the same verified project before any send.
  const title=page.getByTestId('project-grouped-section').getByTitle(projectName,{exact:true});
  const current=title.locator('xpath=ancestor::section[@data-project-id]');
  if(await current.count()!==1||await current.getAttribute('data-project-id')!==projectId)throw Error('DOUBAOWORK_PROJECT_DIRECTORY_ROUTE_DRIFT');
  await title.locator('xpath=ancestor::*[@role="button" and @aria-roledescription="draggable"]').hover();
  const fresh=current.getByRole('button',{name:'新对话',exact:true});
  if(await fresh.count()!==1)throw Error('DOUBAOWORK_PROJECT_DIRECTORY_NEW_TASK_AMBIGUOUS');
  await fresh.click();await page.waitForURL(url=>['/chat','/chat/'].includes(url.pathname),{timeout:10000});
  await page.getByTestId('chat_input').getByRole('button',{name:projectName,exact:true}).waitFor({state:'visible',timeout:10000});
  return proof;
}
