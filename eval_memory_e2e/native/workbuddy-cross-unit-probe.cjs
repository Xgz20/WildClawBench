/* Synthetic old-unit files only. Executed inside the actual signed backend. */
exports.run = function(specPath) {
  const fs = require('node:fs');
  const path = require('node:path');
  const spec = JSON.parse(fs.readFileSync(specPath));
  const home = process.env.CODEBUDDY_CONFIG_DIR;
  if (spec.contract !== 'workbuddy-cross-unit-synthetic-probe/v1'
    || specPath !== home+'/admission-probe/cross-unit-spec.json'
    || spec.app_home !== home || spec.backend_pid !== process.pid) throw Error('WB_CROSS_UNIT_SCOPE');
  const tests = [];
  const control = fs.readFileSync(home+'/synthetic-control.txt','utf8');
  if (control !== 'SYNTHETIC-ALLOW\n') throw Error('WB_CROSS_UNIT_POSITIVE_CONTROL');
  for (const item of spec.old_files) {
    if (!item.file.startsWith(spec.debug_root+'/') || item.file.startsWith(path.dirname(home)+'/')
      || item.alias !== home+'/admission-probe/old-unit-'+item.label) throw Error('WB_CROSS_UNIT_OLD_TEST_FILE');
    const cases = {
      read: () => fs.readFileSync(item.file),
      stat: () => fs.statSync(item.file),
      enumerate: () => fs.readdirSync(path.dirname(item.file)),
      alias: () => fs.readFileSync(item.alias),
      write: () => fs.writeFileSync(path.dirname(item.file)+'/SYNTHETIC-DENIED-'+spec.unit_id, 'SYNTHETIC-NEGATIVE\n', {flag:'wx'}),
    };
    for (const [operation, action] of Object.entries(cases)) {
      try { action(); tests.push({label:item.label,operation,denied:false}); }
      catch (error) { tests.push({label:item.label,operation,denied:error.code==='EPERM',code:error.code}); }
    }
  }
  const result = {at:new Date().toISOString(),backend_pid:process.pid,positive_control:true,tests,
    pass:tests.length === spec.old_files.length*5 && tests.every(t=>t.denied),model_prompts_sent:0};
  fs.writeFileSync(home+'/admission-probe/cross-unit-result.json',JSON.stringify(result,null,2)+'\n',{flag:'wx',mode:0o600});
  return result;
};
