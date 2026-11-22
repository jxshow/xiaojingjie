"""Local disk review console for Windows. Python 3.11+."""
import argparse
import json
import os
import secrets
import tempfile
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from catalog import discover, volumes
from actions import clean, act

ASSETS = Path(__file__).resolve().parents[1]/"assets"
LABEL = {"clean":"清除缓存","keep":"保留","hold":"暂存安装包","restore":"还原安装包","locate":"打开所在目录","storage":"打开系统存储","apps":"打开已安装的应用"}
lock = threading.RLock()
state = dict(phase="idle", rows=[], volumes=[], warnings=[], current="", done=0, total=0, results=[], delta=[], generation="", sample=False)
rows = {}
preview = None

def update(**values):
    with lock:
        state.update(values)

def scan():
    global rows
    try:
        started=time.monotonic()
        report = json.loads(args.report.read_text(encoding="utf-8-sig")) if args.report else {}
        found, warnings = discover(local, home, report, limits, lambda s:update(current=s), sample=args.sample)
        historical = []
        for item in report.get("top5", []):
            if not isinstance(item, dict) or not all(item.get(k) for k in ("name","path","size")):
                continue
            path = Path(item["path"])
            historical.append(dict(name=item["name"], path=str(path), size=str(item["size"]),
                                   note=item.get("note",""), category=item.get("type",""),
                                   protected=any(p == path or p in path.parents for p in limits)))
        overview=dict(scanned=time.strftime("%Y-%m-%d %H:%M:%S"), seconds=round(time.monotonic()-started,1),
                      systemDrive=os.environ.get("SystemDrive","C:"), priorTime=report.get("generated_at",""), ranking=historical[:5])
        with lock:
            rows = {r.key:r for r in found}
            update(phase="ready", rows=[r.public() for r in found], volumes=volumes(),
                   current="", warnings=warnings, generation=secrets.token_hex(8), overview=overview)
    except Exception as e:
        update(phase="error",current=str(e))

def begin_scan():
    global preview
    if state["phase"] in ("scan","run"):
        raise ValueError("操作进行中")
    preview = None
    update(phase="scan",current="检查磁盘",rows=[],volumes=[],results=[],delta=[],warnings=[],done=0,total=0,overview={})
    threading.Thread(target=scan,daemon=True).start()

def make_preview(body):
    global preview
    if state["phase"] != "ready" or body.get("generation") != state["generation"]:
        raise ValueError("清单已变化，请重新扫描")
    choices = body.get("choices")
    if not isinstance(choices,dict) or not choices or len(choices)>len(rows):
        raise ValueError("请选择操作")
    batch = []
    for key, op in choices.items():
        row = rows.get(key)
        if not row or op not in row.actions:
            raise ValueError("选择了不可用的操作")
        batch.append((row,op))
    token = secrets.token_urlsafe(20)
    preview = (token,batch)
    return dict(ticket=token,items=[dict(name=r.name,path=str(r.path),label=LABEL[op],
            count=len(r.files) if op=="clean" else 1, bytes=r.size if op=="clean" else 0) for r,op in batch])

def run(batch):
    results = []
    try:
        before = {v["name"]:v["free"] for v in volumes()}
        done = 0
        for row, action in batch:
            result = dict(name=row.name,path=str(row.path),action=LABEL[action],ok=0,skipped=0,bytes=0,issues=[])
            for entry in (row.files if action=="clean" else [None]):
                update(current=str(entry.path) if entry else row.name)
                try:
                    if entry:
                        clean(entry,row.path,limits)
                        result["bytes"] += entry.size
                    else:
                        act(row,action,home,limits)
                    result["ok"] += 1
                except (OSError,ValueError) as e:
                    result["skipped"] += 1
                    if len(result["issues"]) < 5:
                        result["issues"].append(str(e))
                done += 1
                update(done=done)
            results.append(result)
            update(results=results.copy())
        after = volumes()
        delta = [dict(name=v["name"],bytes=v["free"]-before[v["name"]]) for v in after if v["name"] in before]
        receipt=dict(time=time.strftime("%Y-%m-%d %H:%M:%S"),sample=args.sample,results=results,delta=delta)
        location=args.session_dir/("receipt-"+time.strftime("%Y%m%d-%H%M%S")+"-"+secrets.token_hex(3)+".json")
        location.write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding="utf-8")
        update(phase="complete",current=str(location),volumes=after,delta=delta)
    except Exception as e:
        update(phase="error",current=str(e),results=results)

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*_):
        pass

    def reply(self,status,data,mime="application/json"):
        payload=data if isinstance(data,bytes) else json.dumps(data,ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type",mime if mime.startswith("image/") else mime+"; charset=utf-8")
        self.send_header("Cache-Control","no-store")
        self.send_header("X-Content-Type-Options","nosniff")
        self.send_header("Referrer-Policy","no-referrer")
        self.send_header("Content-Security-Policy","default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
        self.send_header("Content-Length",str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def authorized(self):
        return secrets.compare_digest(self.headers.get("X-Desk-Key",""),secret)

    def do_GET(self):
        global last_seen
        if self.headers.get("Host") != host:
            return self.reply(403,{})
        route=urlsplit(self.path).path
        if route=="/api/state" and self.authorized():
            last_seen=time.monotonic()
            with lock:
                snapshot=json.dumps(state,ensure_ascii=False).encode()
            return self.reply(200,snapshot)
        static={"/":("index.html","text/html"),"/desk.js":("desk.js","text/javascript"),"/desk.css":("desk.css","text/css"),
                "/overview.js":("overview.js","text/javascript"),"/whale.webp":("whale.webp","image/webp")}
        if route in static:
            name,mime=static[route]
            return self.reply(200,(ASSETS/name).read_bytes(),mime)
        self.reply(404,{})

    def do_POST(self):
        global preview,last_seen
        if self.headers.get("Host")!=host or self.headers.get("Origin")!="http://"+host or not self.authorized():
            return self.reply(403,{"error":"请使用本次启动地址"})
        try:
            length=int(self.headers.get("Content-Length","0"))
            if not 0<length<=100000 or self.headers.get_content_type()!="application/json":
                raise ValueError("无效请求")
            body=json.loads(self.rfile.read(length))
            if not isinstance(body,dict):
                raise ValueError("无效请求")
            last_seen=time.monotonic()
            with lock:
                result={}
                if self.path=="/api/scan":
                    begin_scan()
                elif self.path=="/api/preview":
                    result=make_preview(body)
                elif self.path=="/api/confirm":
                    if state["phase"]!="ready" or not preview or body.get("ticket")!=preview[0]:
                        raise ValueError("预览已过期")
                    _,batch=preview
                    preview=None
                    update(phase="run",done=0,total=sum(len(r.files) if op=="clean" else 1 for r,op in batch),current="开始执行")
                    threading.Thread(target=run,args=(batch,),daemon=True).start()
                else:
                    return self.reply(404,{})
            self.reply(200,result)
        except (ValueError,TypeError,KeyError) as e:
            self.reply(400,{"error":str(e)})

if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-dir",type=Path,required=True)
    parser.add_argument("--report",type=Path)
    parser.add_argument("--protect",type=Path,action="append",default=[])
    parser.add_argument("--sample",action="store_true")
    parser.add_argument("--no-open",action="store_true")
    args=parser.parse_args()
    args.session_dir=args.session_dir.resolve()
    args.session_dir.mkdir(parents=True,exist_ok=True)
    home,local=Path.home(),Path(os.environ["LOCALAPPDATA"])
    if args.sample:
        if args.report:
            parser.error("样本模式不能导入真实报告")
        home=Path(tempfile.mkdtemp(prefix="sample-",dir=args.session_dir))
        local=home/"AppData/Local"
        for sub in ("Google/Chrome/User Data/Default/Cache","NVIDIA/DXCache"):
            cache=local/sub
            cache.mkdir(parents=True)
            for i in range(32):
                (cache/f"sample-{i}").write_bytes(b"sample"*8192)
        (home/"Downloads").mkdir()
        (home/"Downloads/sample-installer.msi").write_bytes(b"disk review test fixture")
    limits=[p.absolute() for p in args.protect]
    settings=ASSETS.parent/"local-settings.json"
    if settings.is_file() and not args.sample:
        protected=json.loads(settings.read_text(encoding="utf-8-sig"))["protected"]
        if not isinstance(protected,list) or not all(isinstance(p,str) and Path(p).is_absolute() for p in protected):
            parser.error("本机保护清单必须使用绝对路径")
        limits.extend(Path(p) for p in protected)
    state["sample"]=args.sample
    service=ThreadingHTTPServer(("127.0.0.1",0),Handler)
    host="127.0.0.1:"+str(service.server_port)
    secret=secrets.token_urlsafe(32)
    url="http://"+host+"/#"+secret
    last_seen=time.monotonic()
    service.timeout=1
    begin_scan()
    (args.session_dir/"address.txt").write_text(url,encoding="utf-8")
    if not args.no_open:
        webbrowser.open(url)
    while time.monotonic()-last_seen<1800 or state["phase"] in ("scan","run"):
        service.handle_request()
    service.server_close()
