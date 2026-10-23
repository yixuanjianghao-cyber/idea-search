import {test} from 'node:test';
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {createServer} from 'node:net';
import {mkdtempSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';

test('AI key is rejected in GitHub settings and never persisted',async()=>{
 const probe=createServer();await new Promise(r=>probe.listen(0,'127.0.0.1',r));const port=probe.address().port;await new Promise(r=>probe.close(r));
 const child=spawn(process.execPath,['server.mjs'],{windowsHide:true,stdio:'ignore',env:{...process.env,HOST:'127.0.0.1',PORT:String(port),GITHUB_TOKEN:'',GH_TOKEN:'',GHF_DATA_DIR:mkdtempSync(join(tmpdir(),'idea-search-config-test-'))}});
 const base='http://127.0.0.1:'+port;
 try{
  let ready=false;
  for(let i=0;i<60;i++){try{ready=(await fetch(base+'/api/health')).ok;if(ready)break;}catch{}await new Promise(r=>setTimeout(r,50));}
  assert.equal(ready,true);
  for(const path of ['/api/config','/api/check-github-token']){
   const result=await fetch(base+path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:'sk-fixture-not-real'})});
   assert.equal(result.status,400);assert.match((await result.json()).error,/AI/);
  }
  assert.equal((await(await fetch(base+'/api/config')).json()).hasToken,false);
 }finally{child.kill();await new Promise(r=>child.once('exit',r));}
});
