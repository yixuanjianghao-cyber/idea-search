import {test} from 'node:test';
import assert from 'node:assert/strict';
import {launchPlan,selectWindowsAsset} from '../lib/launch.mjs';
import {deployScript} from '../lib/deployment.mjs';
const repo={full_name:'example/app',html_url:'https://github.com/example/app'};
test('selects only same-repository Windows release assets for the current architecture',()=>{
 const asset=(name,url='https://github.com/example/app/releases/download/v1/'+name)=>({name,browser_download_url:url,size:100});
 const selected=selectWindowsAsset([asset('app-arm64.exe'),asset('app-macos.zip'),asset('app-x64-setup.exe'),asset('app.exe','https://bad.example/app.exe')],repo.full_name,'x64');
 assert.equal(selected.name,'app-x64-setup.exe');
 assert.equal(launchPlan(repo,'desktop','clone',[],selected).mode,'release');
});
test('only matching app-managed folders can be reused and source is never reset',()=>{
 const script=deployScript(repo,'python',['python -m venv .venv']);
 assert.match(script,/\.idea-search-managed/);assert.match(script,/findstr \/x \/l/);assert.doesNotMatch(script,/git (pull|reset)|rmdir|Remove-Item/);
});
test('type determines action and installation is never labelled startup without an entry',()=>{
 assert.equal(launchPlan(repo,'examples','python',[]).mode,'examples');
 assert.equal(launchPlan(repo,'prompts','clone',[]).mode,'browse');
 assert.equal(launchPlan(repo,'library','python',['python -m venv .venv']).mode,'environment');
 assert.equal(launchPlan(repo,'app','python',['.venv\\Scripts\\python.exe -m pip install .']).mode,'environment');
 assert.equal(launchPlan(repo,'app','compose',['docker compose up -d']).mode,'script');
 assert.equal(launchPlan(repo,'unknown','clone',[]).mode,'manual');
});
