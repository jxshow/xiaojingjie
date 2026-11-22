"use strict";
function renderOverview(s){
  const data=s.overview||{}, volumes=s.volumes||[], safe=s.rows.filter(r=>r.kind==="safe");
  const drive=volumes.find(v=>v.name===data.systemDrive)||volumes[0];
  const scan=s.phase==="scan", finished=s.phase==="complete", failed=s.phase==="error";
  const inVolume=(row,v)=>row.path.toUpperCase().startsWith(v.name.toUpperCase()+"\\");
  const cacheBytes=v=>safe.filter(r=>inVolume(r,v)).reduce((n,r)=>n+r.size,0);
  el("scan-meta").textContent=scan?"正在只读扫描…":data.scanned?(s.sample?"临时样本 · ":"")+"本次扫描 "+data.scanned+"　·　耗时 "+data.seconds+" 秒":"等待读取本机数据";
  el("hero-drive").textContent=drive?(drive.name===data.systemDrive?"系统盘 ":"本地磁盘 ")+drive.name:"磁盘空间";
  const tight=drive && drive.free/drive.total<0.1;
  el("hero-status").textContent=scan?"正在分析磁盘":drive?tight?"可用空间偏紧":"当前可用空间":"暂未读取到磁盘";
  const reading=drive?(drive.free/1024**3).toLocaleString("zh-CN",{maximumFractionDigits:2}):"—";
  el("hero-number").textContent=reading;
  el("hero-unit").textContent=drive?"GiB":"";
  el("hero-caption").textContent=drive?"可用空间 / 共 "+fmt(drive.total)+"　·　剩余 "+(100*drive.free/drive.total).toFixed(1)+"%":"正在读取容量";
  const targets=(drive?safe.filter(r=>inVolume(r,drive)):safe).sort((a,b)=>b.size-a.size);
  const sum=targets.reduce((n,r)=>n+r.size,0);
  el("opportunity").textContent=scan||finished||failed?"—":fmt(sum);
  el("opportunity-label").textContent=finished?"等待重新扫描":(drive?drive.name+" · ":"")+targets.length+" 项缓存候选";
  el("advice-copy").textContent=scan?"正在核对缓存目录及保护范围。":failed?"扫描或执行中遇到问题，详情见工作台。":finished?"本次操作已结束。重新扫描可以核对剩余缓存和可用容量。":targets.length?
    "优先查看 "+targets[0].name+"，约占本盘缓存候选的 "+(sum?Math.round(100*targets[0].size/sum):0)+"%。"+(tight && drive?"如全部清除，预计可用空间约为 "+fmt(drive.free+sum)+"。":"可在工作台逐项勾选。"):
    "本盘未发现当前规则可清除的缓存。可以到工作台复核较大的下载文件和安装包。";
  el("jump-safe").disabled=s.phase!=="ready"&&s.phase!=="complete";
  el("jump-safe").firstChild.textContent=finished?"重新核对缓存 ":targets.length?"查看可清理项 ":"查看谨慎项 ";
  el("jump-safe").onclick=()=>{if(finished){el("rescan").click();return;}filter=targets.length?"safe":"review";renderList();el("workbench").scrollIntoView();};
  el("drive-count").textContent=volumes.length?volumes.length+" 个磁盘":"";
  el("drives").replaceChildren(...volumes.map(v=>{
    const block=make("div",undefined,"drive"), head=make("div",undefined,"drivehead"), bar=make("div",undefined,"volbar");
    const freePct=100*v.free/v.total, cached=scan||finished?0:Math.min(cacheBytes(v),v.total-v.free);
    head.append(make("b",v.name+"　"+(v.name===data.systemDrive?"系统盘":"数据盘")),make("span",(100-freePct).toFixed(0)+"% 已用"));
    const used=make("i",undefined,"used"), cache=make("i",undefined,"cache");used.style.width=100*(v.total-v.free-cached)/v.total+"%";cache.style.width=100*cached/v.total+"%";bar.append(used,cache);
    const foot=make("div",undefined,"drivefoot");foot.append(make("span","已用 "+fmt(v.total-v.free)),make("span","可用 "+fmt(v.free)+" / "+fmt(v.total)));
    block.append(head,bar,foot);return block;
  }));
  const historical=data.ranking&&data.ranking.length;
  const current=[...s.rows].filter(r=>r.size>0&&!r.estimate).sort((a,b)=>b.size-a.size).slice(0,5);
  const ranked=historical?data.ranking:current;
  el("rank-source").textContent=scan?"读取中":historical?"上次磁盘分析":"本次已测候选";
  el("rank-note").textContent=historical?"历史报告 · "+(data.priorTime||"时间未记录")+"　/　展开可查看位置与说明。":ranked.length?"按本次已测候选的文件大小排序。":"";
  const largest=ranked[0], otherDrive=largest && volumes.find(v=>inVolume(largest,v));
  const context=el("drive-insight");
  context.textContent=otherDrive && drive && otherDrive.name!==drive.name?
    (historical?"上次排行":"本次候选")+"中占用最大的「"+largest.name+"」位于 "+otherDrive.name[0]+" 盘。要给系统盘腾空间，应优先查看 "+drive.name[0]+" 盘的候选项。":"";
  context.hidden=!context.textContent;
  el("ranks").replaceChildren(...ranked.map((r,i)=>{
    const det=make("details",undefined,"rank"), top=make("summary"), label=make("div",undefined,"ranklabel");
    label.append(make("b",r.name),make("small",historical?[r.category,r.protected?"已保护":""].filter(Boolean).join(" · "):names[r.kind]));
    top.append(make("span",String(i+1).padStart(2,"0"),"rankno"),label,make("span",historical?r.size:fmt(r.size),"rankvalue"),make("span","⌄","chev"));
    det.append(top,make("code",r.path,"path"),make("p",r.note||r.detail||""));return det;
  }));
  if(!ranked.length)el("ranks").append(make("p",scan?"正在统计候选项目…":"暂无可排行的扫描数据。","empty"));
}
