/* Private control transport. Only an OS-authenticated backend child is accepted. */
const fs=require('node:fs'),net=require('node:net');
const [action,specPath]=process.argv.slice(2),spec=JSON.parse(fs.readFileSync(specPath,'utf8'));
if(!['spawn','watch','kill'].includes(action)||spec.contract!=='workbuddy-owned-executor-gateway/v1')throw Error('WB_EXEC_CLIENT_SPEC');
let input='';process.stdin.setEncoding('utf8');process.stdin.on('data',s=>{input+=s;if(input.length>1024*1024)throw Error('WB_EXEC_CLIENT_SIZE')});
process.stdin.on('end',()=>{
  const request=JSON.parse(input),socket=net.createConnection(spec.control_socket);let output='';
  socket.setTimeout(action==='watch'?0:15000,()=>socket.destroy(Error('WB_EXEC_CLIENT_TIMEOUT')));
  socket.on('connect',()=>socket.write(JSON.stringify({action,...request})+'\n'));
  socket.on('data',b=>{output+=b.toString('utf8');if(output.length>1024*1024)socket.destroy(Error('WB_EXEC_CLIENT_SIZE'))});
  socket.on('error',e=>{process.stderr.write(e.message+'\n');process.exitCode=2});
  socket.on('end',()=>{process.stdout.write(output);if(!output.trim())process.exitCode=2});
});
