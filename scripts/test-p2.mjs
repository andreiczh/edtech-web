import assert from 'node:assert/strict'
import {mkdtemp,rm} from 'node:fs/promises'
import {pathToFileURL} from 'node:url'
import path from 'node:path'
import {build} from 'esbuild'
import React from 'react'
import renderer from 'react-test-renderer'

globalThis.IS_REACT_ACT_ENVIRONMENT = true
const dir=await mkdtemp(path.resolve('.p2-tests-'))
let count=0
function check(ok,label){assert.ok(ok,label);count++;console.log('OK  ',label)}
async function bundle(file,name,plugins=[]){
 await build({entryPoints:[file],outfile:`${dir}/${name}.mjs`,bundle:true,format:'esm',platform:'node',packages:'external',plugins,define:{'import.meta.env':'{}'}})
 return import(pathToFileURL(`${dir}/${name}.mjs`))
}
const mocks={name:'services',setup(b){
 b.onResolve({filter:/\/max\/bridge$/},()=>({path:'bridge',namespace:'mock'}))
 b.onResolve({filter:/\.\.\/(account\/me|auth\/auth)$/},a=>({path:a.path,namespace:'mock'}))
 b.onLoad({filter:/.*/,namespace:'mock'},a=>({contents:a.path==='bridge'?'export const isMaxLaunch=()=>false;':a.path.includes('account')?'export const getSettings=()=>({persona:"tutor"}); export const fetchMeStats=async()=>({totals:{tasks:1},streak:{days:1}}); export const fetchMeAnalytics=async()=>globalThis.qaAnalytics;':'export const authHeaders=()=>({Authorization:"Bearer synthetic"}); export const currentUser=()=>({nickname:"QA"});'}))
}}
try{
 const {aggregate}=await bundle('src/account/statsSeries.ts','series')
 const hist=[{d:'2026-11-01',k:'reading',p:100},{d:'2026-10-31',k:'reading',p:0}]
 let data=aggregate(hist,'month','2026-11-01')
 check(data.labels.length===30,'month shows 30 days, not six months')
 check(data.series[0].points.at(-1)===100 && data.series[0].points.at(-2)===0,'month boundary keeps both days')
 data=aggregate(hist,'year','2026-11-01')
 check(data.labels.at(-1)==='Ноя' && data.series[0].points.at(-1)===100,'current month is not shifted back by timezone')
 check(data.series[0].points.at(-2)===0,'previous month remains a separate bucket')
 const listeners=new Set()
 const mq={matches:false,addEventListener:(_,f)=>listeners.add(f),removeEventListener:(_,f)=>listeners.delete(f)}
 globalThis.window={location:{search:''},matchMedia:()=>mq}
 const {useMobileShell}=await bundle('src/mini/useMobileShell.ts','shell',[mocks])
 const Probe=({locked})=>React.createElement('output',null,String(useMobileShell(locked)))
 let tree
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Probe,{locked:false}))})
 check(tree.toJSON().children[0]==='false','wide idle screen uses desktop shell')
 await renderer.act(async()=>{mq.matches=true;for(const f of listeners)f(mq)})
 check(tree.toJSON().children[0]==='true','idle resize switches to mobile')
 await renderer.act(async()=>{tree.update(React.createElement(Probe,{locked:true}))})
 await renderer.act(async()=>{mq.matches=false;for(const f of listeners)f(mq)})
 check(tree.toJSON().children[0]==='true','active task keeps its shell across rotation')
 await renderer.act(async()=>{tree.update(React.createElement(Probe,{locked:false}))})
 check(tree.toJSON().children[0]==='false','leaving task applies current viewport')
 await renderer.act(async()=>tree.unmount())
 const {HomeScreen}=await bundle('src/screens/HomeScreen.tsx','home',[mocks])
 const {TASKS}=await bundle('src/ege2/tasks.ts','tasks',[mocks])
 const variantId=TASKS[40].variants[0].id
 globalThis.qaAnalytics={history:[{k:'dialogue',v:variantId,s:1,m:4}],kinds:{}}
 let chosen
 await renderer.act(async()=>{tree=renderer.create(React.createElement(HomeScreen,{onMistakes:items=>chosen=items}))})
 const repeat=tree.root.findAllByType('button').find(b=>b.children.some(x=>typeof x==='string'&&x.includes('Повторить задания')))
 check(repeat && !repeat.props.disabled,'mistakes CTA is enabled for a real failed variant')
 await renderer.act(async()=>repeat.props.onClick())
 check(chosen?.[0]?.variantId===variantId && chosen?.[0]?.taskId===40,'mistakes CTA opens exactly the failed variant')
 await renderer.act(async()=>tree.unmount())
 const {requestTaskFeedback}=await bundle('src/ege2/feedback.ts','feedback',[mocks])
 const originalTimer=globalThis.setTimeout
 globalThis.setTimeout=(fn,ms,...args)=>originalTimer(fn,ms===180000?1:ms,...args)
 try{
  globalThis.fetch=(_,init)=>new Promise((_,reject)=>init.signal.addEventListener('abort',()=>reject(new Error('abort'))))
  await assert.rejects(requestTaskFeedback(new Blob(['test']),'reading',{}),/трёх минут/);count++
  globalThis.fetch=async(_,init)=>({ok:true,status:200,json:()=>new Promise((_,reject)=>init.signal.addEventListener('abort',()=>reject(new Error('abort'))))})
  await assert.rejects(requestTaskFeedback(new Blob(['test']),'reading',{}),/три минуты/);count++
  globalThis.fetch=async()=>Response.json({transcript:'test',feedback:{score:1,max:1}})
  check((await requestTaskFeedback(new Blob(['test']),'reading',{})).feedback.score===1,'successful grading survives watchdog')
 }finally{globalThis.setTimeout=originalTimer}
 console.log(`P2 frontend: ${count} checks passed`)
}finally{await rm(dir,{recursive:true,force:true})}
