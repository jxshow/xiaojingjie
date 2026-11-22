"use strict";
const el = id => document.getElementById(id);
const make = (tag, text, cls) => {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (cls) node.className = cls;
  return node;
};
const suppliedKey = location.hash.slice(1);
const hasKey = /^[A-Za-z0-9_-]{43}$/.test(suppliedKey);
const token = hasKey ? suppliedKey : sessionStorage.getItem("desk-key") || "";
if (hasKey) {
  sessionStorage.setItem("desk-key", token);
  history.replaceState(null, "", "/");
}
const names = {all:"全部项目",safe:"可清理",review:"谨慎处理",protected:"已保护"};
const ops = {clean:"清除缓存",keep:"保留",hold:"暂存，可还原",restore:"还原到下载目录",locate:"打开所在目录",storage:"打开系统存储设置",apps:"打开应用卸载面板"};
const fmt = n => {
  if (!n) return "0 B";
  const i = Math.min(4, Math.floor(Math.log(Math.abs(n))/Math.log(1024)));
  return (n/1024**i).toLocaleString("zh-CN",{maximumFractionDigits:2})+" "+["B","KiB","MiB","GiB","TiB"][i];
};
let model = {rows:[],phase:"idle",generation:""}, filter="all", choices={}, expanded=new Set(), ticket="", viewKey="", pending=false;
async function api(route, body) {
  const options = {headers:{"X-Desk-Key":token}};
  if (body !== undefined) {
    options.method="POST";
    options.headers["Content-Type"]="application/json";
    options.body=JSON.stringify(body);
  }
  const response=await fetch("/api/"+route,options);
  const data=await response.json();
  if (!response.ok) throw Error(data.error || "连接已失效，请重新打开启动地址。");
  return data;
}
function notice(error) {el("notice").textContent=error.message || String(error);}
function actions() {return Object.fromEntries(Object.entries(choices).filter(([key,op])=>model.rows.some(r=>r.id===key && r.actions.includes(op))));}
function summary() {
  const picked=actions();
  const finished=model.phase==="complete";
  const count=Object.keys(picked).length;
  el("chosen").previousElementSibling.textContent=finished?"已执行操作":"待执行操作";
  el("bytes").previousElementSibling.textContent=finished?"已清除文件量":"预计清除缓存";
  el("chosen").textContent=(finished?model.results.length:count)+" 项";
  el("bytes").textContent=fmt(finished?model.results.reduce((n,r)=>n+r.bytes,0):model.rows.reduce((n,r)=>n+(picked[r.id]==="clean"?r.size:0),0));
  if(model.phase==="ready"){
    el("percent").textContent=String(count);
    el("orbHint").textContent="项已选";
    el("orb").setAttribute("aria-label",count+" 项已选");
  }
  el("preview").disabled=model.phase!=="ready" || pending || !Object.keys(picked).length;
}
function decide(r,op) {
  if (op) choices[r.id]=op; else delete choices[r.id];
  sessionStorage.setItem("choices-"+model.generation,JSON.stringify(choices));
  summary();
}
function rowCard(r) {
  const card=make("article",undefined,"row "+r.kind);
  const line=make("div",undefined,"line");
  line.append(make("span",names[r.kind],"badge"),make("h3",r.name),make("span",r.estimate?"上次 "+r.estimate:r.size?fmt(r.size):"—","num"));
  const bot=make("div",undefined,"rowbot"),detail=make("div",undefined,"detail"),exp=make("button","查看详情 ▾","exp");
  detail.append(make("p",r.detail),make("code",r.path,"path"));
  if (r.errors) detail.append(make("p",r.errors+" 项读取失败，容量可能低估。"));
  const fold=()=>{detail.hidden=!expanded.has(r.id);exp.setAttribute("aria-expanded",String(!detail.hidden));exp.textContent=detail.hidden?"查看详情 ▾":"收起详情 ▴";};
  exp.onclick=()=>{if(expanded.has(r.id))expanded.delete(r.id);else expanded.add(r.id);fold();}; fold();
  const controls=make("div",undefined,"choice");
  if (r.kind==="safe") {
    for (const [op,label] of [["clean","✓ 清理"],["keep","× 跳过"]]) {
      const b=make("button",label,op==="keep"?"skip":"");
      b.dataset.action=op;
      b.setAttribute("aria-label",r.name+" "+label);
      b.setAttribute("aria-pressed",String(choices[r.id]===op));
      b.disabled=model.phase!=="ready";
      b.onclick=()=>{decide(r,op);for(const sibling of controls.children)sibling.setAttribute("aria-pressed",String(sibling===b));};
      controls.append(b);
    }
  } else if (r.kind==="review") {
    const select=make("select");select.setAttribute("aria-label",r.name+" 的处理方式");
    for(const op of ["","keep",...r.actions]) select.add(new Option(ops[op]||"选择处理方式",op));
    select.value=choices[r.id]||"";select.disabled=model.phase!=="ready";
    select.onchange=()=>{decide(r,select.value);expanded.add(r.id);fold();};
    controls.append(select);
  } else controls.append(make("small","已按你的要求保留","note"));
  bot.append(exp,controls);card.append(line);
  if(r.kind==="review" && r.detail) card.append(make("p",r.detail.split("。")[0]+"。","reason"));
  card.append(bot,detail);return card;
}
function renderList() {
  const nav=el("filters");nav.replaceChildren();
  for(const [key,label] of Object.entries(names)){
    const b=make("button",label);
    b.append(make("span",String(model.rows.filter(r=>key==="all"||r.kind===key).length)));
    b.setAttribute("aria-pressed",String(filter===key));
    b.onclick=()=>{filter=key;renderList();nav.querySelector('[aria-pressed="true"]').focus();};
    nav.append(b);
  }
  const rows=model.rows.filter(r=>filter==="all"||r.kind===filter);
  el("rows").replaceChildren(...rows.map(rowCard));
  if(!rows.length && model.phase!=="scan")el("rows").append(make("p","这一栏暂无候选项目。","empty"));
  el("title").textContent=filter==="all"?"清理清单":names[filter];
  el("intro").textContent=(model.sample?"临时样本 · ":"")+(
    model.phase==="scan"?"正在只读扫描。":model.phase==="complete"?"本轮处理已结束，可重新扫描检查剩余项。":"勾选要处理的项目，或逐项选择保留。");
  renderOverview(model);
  el("receipt").replaceChildren();
  if(model.phase==="complete"||model.phase==="error"&&model.results.length){
    const box=el("receipt");box.append(make("h2","执行记录"));
    for(const r of model.results){
      box.append(make("p",r.name+" · "+r.action+" · 成功 "+r.ok+" / 跳过 "+r.skipped+(r.bytes?" · "+fmt(r.bytes):"")));
      if(r.issues.length)box.append(make("small",r.issues.join(" ／ "),"path"));
    }
    if(model.delta.length)box.append(make("p","卷可用空间变化（含同期其他读写） · "+model.delta.map(v=>v.name+" "+(v.bytes>=0?"+":"")+fmt(v.bytes)).join("　")));
    if(model.phase==="complete")box.append(make("code",model.current,"path"));
  }
  summary();
}
function display(s) {
  if(s.generation!==model.generation){
    try{choices=JSON.parse(sessionStorage.getItem("choices-"+s.generation)||"{}");}catch{choices={};}
    expanded=new Set();
  }
  model=s;
  el("connection").textContent=s.sample?"临时样本":"本机已连接";
  const pct=s.total?Math.floor(100*s.done/s.total):0;
  const busy=s.phase==="scan"||s.phase==="run";
  el("rescan").disabled=busy||pending;
  el("percent").textContent=s.total?pct+"%":"—";
  el("orb").style.setProperty("--level",pct+"%");
  el("orbHint").textContent=({scan:"扫描中",ready:"等待选择",run:"执行中",complete:"处理完成",error:"需要检查"})[s.phase]||"正在连接";
  el("orb").setAttribute("aria-label",el("orbHint").textContent+(s.total?" "+pct+"%":""));
  el("progress").textContent=s.phase==="run"?s.done+" / "+s.total+" · "+s.current:
    s.phase==="scan"?s.current:s.phase==="complete"?s.done+" / "+s.total+" 已处理":"";
  const key=s.phase+s.generation;
  if(key!==viewKey){viewKey=key;renderList();el("notice").textContent=s.phase==="error"?s.current:s.warnings.join("　");}
  else if(s.phase==="ready")summary();
}
async function refresh(){display(await api("state"));}
async function poll(){
  try{await refresh();}catch(e){notice(e);el("connection").textContent="连接中断";el("preview").disabled=true;el("jump-safe").disabled=true;}
  setTimeout(poll,model.phase==="run"||model.phase==="scan"?200:1200);
}
el("rescan").onclick=async()=>{try{pending=true;el("rescan").disabled=true;await api("scan",{});await refresh();}catch(e){notice(e);}finally{pending=false;summary();}};
el("preview").onclick=async()=>{
  try{
    pending=true;summary();
    const plan=await api("preview",{generation:model.generation,choices:actions()});
    ticket=plan.ticket;
    el("warning").textContent=plan.items.some(i=>i.label===ops.clean)?"勾选的缓存文件将永久清除。已变化或正在使用的文件会跳过。":"暂存支持还原。打开目录或系统设置的操作需要你在相应窗口继续。";
    el("plan").replaceChildren(...plan.items.map(i=>{
      const row=make("div",undefined,"planrow");
      row.append(make("b",i.name),make("p",i.label+" · "+i.count+(i.label===ops.clean?" 个文件 · "+fmt(i.bytes):" 项")),make("code",i.path,"path"));return row;
    }));
    el("dialog").showModal();el("cancel").focus();
  }catch(e){notice(e);}finally{pending=false;summary();}
};
el("cancel").onclick=()=>el("dialog").close();
el("confirm").onclick=async()=>{
  el("confirm").disabled=true;
  try{await api("confirm",{ticket});el("dialog").close();await refresh();}
  catch(e){el("dialog").close();notice(e);}
  finally{el("confirm").disabled=false;}
};
const sectionLinks=document.querySelectorAll(".pages a");
function syncNav(){
  const current=el("workbench").getBoundingClientRect().top<innerHeight*0.45?"#workbench":"#overview";
  for(const link of sectionLinks){
    if(link.getAttribute("href")===current)link.setAttribute("aria-current","location");
    else link.removeAttribute("aria-current");
  }
}
addEventListener("scroll",syncNav,{passive:true});
poll();
