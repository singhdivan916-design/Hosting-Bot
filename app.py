"""
Multi-File Hoster — auto-assigns random ports, rewrites hardcoded ports
via Python sitecustomize / Node require shim. No file editing needed.
"""
import os, sys, zipfile, subprocess, threading, time, signal, shutil, secrets, json, random, socket
from pathlib import Path
from flask import Flask, request, jsonify, render_template_string

# ──────────────────────────────────────────────────────────── data dir (Termux-safe)
def default_data_dir():
    env = os.environ.get("DATA_DIR")
    if env: return Path(env)
    if "ANDROID_ROOT" in os.environ or "TERMUX_VERSION" in os.environ:
        return Path.home() / "hosted"
    return Path("/tmp/hosted")

DATA = default_data_dir()
try:
    DATA.mkdir(parents=True, exist_ok=True)
except Exception:
    DATA = Path.home() / "hosted"
    DATA.mkdir(parents=True, exist_ok=True)

PROJECTS_DIR = DATA / "projects"
PROJECTS_DIR.mkdir(exist_ok=True)
STATE_FILE   = DATA / "projects.json"

# shim directory for Python/Node port rewriting
SHIM_DIR = DATA / "_shims"
SHIM_DIR.mkdir(exist_ok=True)

# ──────────────────────────────────────────────────────────── port-rewrite shims
PY_SHIM = SHIM_DIR / "sitecustomize.py"
PY_SHIM.write_text('''
# Auto-loaded by Python. Rewrites the first wildcard bind() to $HOSTER_FORCE_PORT.
import os, socket
_real_bind = socket.socket.bind
_force = int(os.environ.get("HOSTER_FORCE_PORT", "0") or 0)
_done = False

def _patched_bind(self, address):
    global _done
    if _force and not _done:
        try:
            host = address[0]
            port = address[1]
            if host in ("0.0.0.0", "", "::", "0:0:0:0:0:0:0:0") and port and port > 0:
                address = (host, _force) + tuple(address[2:])
                _done = True
        except Exception:
            pass
    return _real_bind(self, address)

socket.socket.bind = _patched_bind
''')

NODE_SHIM = SHIM_DIR / "port-patch.js"
NODE_SHIM.write_text('''
// Rewrites the first listen(port) to HOSTER_FORCE_PORT.
const net = require('net');
const force = parseInt(process.env.HOSTER_FORCE_PORT || '0', 10);
if (force) {
  let done = false;
  const orig = net.Server.prototype.listen;
  net.Server.prototype.listen = function(...args) {
    if (!done && args.length > 0) {
      const a0 = args[0];
      if (typeof a0 === 'number' && a0 > 0) { args[0] = force; done = true; }
      else if (typeof a0 === 'object' && a0 && a0.port) {
        args[0] = Object.assign({}, a0, { port: force }); done = true;
      }
    }
    return orig.apply(this, args);
  };
}
''')

HOSTER_PORT = int(os.environ.get("PORT", 5000))
app = Flask(__name__)

# ──────────────────────────────────────────────────────────── project registry
PROJECTS = {}
LOCK = threading.RLock()

def pick_port():
    with LOCK:
        used = {p.get("port") for p in PROJECTS.values() if p.get("port")}
    used.add(HOSTER_PORT)
    for _ in range(300):
        port = random.randint(10000, 65000)
        if port in used: continue
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("0.0.0.0", port)); s.close()
            return port
        except OSError:
            continue
    return random.randint(10000, 65000)

def free_port(port):
    for cmd in (["fuser", "-k", f"{port}/tcp"], ["lsof", "-ti", f":{port}"]):
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=3, text=True)
            if cmd[0] == "lsof" and r.stdout.strip():
                for pid in r.stdout.strip().split():
                    try: os.kill(int(pid), signal.SIGKILL)
                    except Exception: pass
            return
        except FileNotFoundError:
            continue
        except Exception:
            continue

def save_state():
    with LOCK:
        data = {pid: {"name": p["name"], "entry": p["entry"],
                      "enabled": p["enabled"], "dir": str(p["dir"]),
                      "port": p.get("port")}
                for pid, p in PROJECTS.items()}
    try: STATE_FILE.write_text(json.dumps(data, indent=2))
    except Exception: pass

def load_state():
    if not STATE_FILE.exists(): return
    try: data = json.loads(STATE_FILE.read_text())
    except Exception: return
    for pid, meta in data.items():
        d = Path(meta["dir"])
        if not d.exists(): continue
        PROJECTS[pid] = {
            "name": meta["name"], "entry": meta.get("entry"),
            "enabled": meta.get("enabled", True), "dir": d,
            "proc": None, "log": [], "started": None, "exit": None,
            "port": meta.get("port") or pick_port(),
            "port_conflicts": 0,
        }

def plog(pid, line):
    p = PROJECTS.get(pid)
    if not p: return
    p["log"].append(line)
    if len(p["log"]) > 1500: p["log"] = p["log"][-1500:]
    try: print(f"[{pid}] {line}", end="", flush=True)
    except Exception: pass

# ──────────────────────────────────────────────────────────── entrypoint detection
def find_entry(root: Path):
    for name in ("Procfile", "start.sh"):
        p = root / name
        if p.exists():
            first = p.read_text().strip().splitlines()
            if first: return first[0]
    for name in ("main.py", "app.py", "bot.py", "server.py", "run.py", "index.py"):
        if (root / name).exists(): return f"python3 {name}"
    pys = sorted(root.glob("*.py"))
    if pys: return f"python3 {pys[0].name}"
    if (root / "package.json").exists(): return "npm start"
    if (root / "index.js").exists(): return "node index.js"
    return None

# ──────────────────────────────────────────────────────────── process control
def stop_proc(pid, reason="manual"):
    p = PROJECTS.get(pid)
    if not p: return
    proc = p.get("proc")
    if proc and proc.poll() is None:
        plog(pid, f"[hoster] stopping ({reason})\n")
        try: os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except Exception:
            try: proc.terminate()
            except Exception: pass
        try: proc.wait(timeout=5)
        except Exception:
            try: os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except Exception: pass
    p["proc"] = None

def run_proc(pid, reason="start"):
    p = PROJECTS.get(pid)
    if not p: return
    stop_proc(pid, reason="restart")
    p["log"].append("\n──────── restart ────────\n")

    entry = find_entry(p["dir"])
    if not entry:
        plog(pid, "[hoster] no entrypoint found\n"); return
    p["entry"] = entry
    p["exit"] = None

    root = p["dir"]
    port = p.get("port") or pick_port()
    p["port"] = port

    free_port(port)

    req = root / "requirements.txt"
    if req.exists():
        plog(pid, "[hoster] pip install -r requirements.txt\n")
        try:
            r = subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-r", str(req)],
                               capture_output=True, text=True, timeout=180)
            if r.stdout: plog(pid, r.stdout)
            if r.stderr: plog(pid, r.stderr)
        except Exception as e:
            plog(pid, f"[hoster] pip failed: {e}\n")

    if (root / "package.json").exists() and shutil.which("npm"):
        plog(pid, "[hoster] npm install\n")
        try:
            subprocess.run("npm install --silent", shell=True, cwd=str(root),
                           capture_output=True, timeout=180)
        except Exception: pass

    plog(pid, f"[hoster] starting on port {port} (force-rewrite active): {entry}\n")

    # environment: force all binds to our random port
    env = {**os.environ,
           "PORT": str(port),
           "HOSTER_FORCE_PORT": str(port),
           "HOST": "0.0.0.0"}
    # prepend our Python shim so sitecustomize.py loads first
    old_py = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{SHIM_DIR}{os.pathsep}{old_py}" if old_py else str(SHIM_DIR)
    # node require shim
    old_node = env.get("NODE_OPTIONS", "")
    req_opt = f"--require {NODE_SHIM}"
    env["NODE_OPTIONS"] = f"{old_node} {req_opt}".strip()

    try:
        proc = subprocess.Popen(
            entry, shell=True, cwd=str(root), env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1,
            preexec_fn=os.setsid if hasattr(os, "setsid") else None)
        p["proc"] = proc
        p["started"] = time.time()
        threading.Thread(target=_reader, args=(pid, proc), daemon=True).start()
    except Exception as e:
        plog(pid, f"[hoster] failed to start: {e}\n")
        p["exit"] = -1

PORT_ERR_SIGNS = ("address already in use", "eaddrinuse",
                  "errno 98", "port is already allocated",
                  "only one usage of each socket address")

def _reader(pid, proc):
    conflict = False
    try:
        for line in iter(proc.stdout.readline, ""):
            if not line: break
            plog(pid, line)
            low = line.lower()
            if any(s in low for s in PORT_ERR_SIGNS):
                conflict = True
    except Exception: pass
    code = proc.poll()
    p = PROJECTS.get(pid)
    if p:
        p["exit"] = code if code is not None else 0
        p["proc"] = None
        if conflict or code == 98:
            p["port_conflicts"] = p.get("port_conflicts", 0) + 1
            old = p.get("port"); new = pick_port()
            p["port"] = new
            plog(pid, f"[hoster] port {old} was taken → reassigning to {new}\n")
            save_state()
            time.sleep(1)
            threading.Thread(target=run_proc, args=(pid, "port-conflict"), daemon=True).start()
            return
    plog(pid, f"[hoster] process exited (code {code})\n")

def auto_restart_loop():
    while True:
        time.sleep(6)
        with LOCK:
            for pid, p in list(PROJECTS.items()):
                if not p["enabled"]: continue
                proc = p.get("proc")
                if proc and proc.poll() is None: continue
                if not find_entry(p["dir"]): continue
                plog(pid, "[hoster] auto-restart\n")
                run_proc(pid, "auto-restart")

# ──────────────────────────────────────────────────────────── HTML
HTML = """
<!DOCTYPE html><html><head><meta charset="utf-8">
<title>Multi Hoster</title><meta name="viewport" content="width=device-width,initial-scale=1">
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:system-ui,sans-serif;background:#0b0d11;color:#c9d1d9;min-height:100vh;padding:32px 20px}
.wrap{max-width:1000px;margin:0 auto}
h1{color:#fff;font-size:22px;margin-bottom:6px}
p.sub{color:#6e7681;font-size:13px;margin-bottom:22px}
.drop{border:2px dashed #2a303d;border-radius:12px;padding:44px 20px;text-align:center;
  transition:.15s;cursor:pointer;background:#11141a;margin-bottom:20px}
.drop:hover,.drop.over{border-color:#3b82f6;background:#141a24}
.drop h2{color:#fff;font-size:15px;margin-bottom:6px}
.drop span{color:#6e7681;font-size:13px}
.prog{height:4px;background:#1f2430;border-radius:2px;overflow:hidden;margin-top:12px;display:none}
.prog>div{height:100%;background:#3b82f6;width:0;transition:.2s}
.proj{background:#11141a;border:1px solid #1f2430;border-radius:10px;
  padding:14px 16px;margin-bottom:12px;transition:.15s}
.proj:hover{border-color:#2a303d}
.head{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap}
.name{color:#fff;font-weight:600;font-size:14px;display:flex;align-items:center;gap:9px}
.dot{width:8px;height:8px;border-radius:50%;flex-shrink:0}
.dot.on{background:#10b981;box-shadow:0 0 8px #10b981}
.dot.off{background:#6e7681}
.meta{color:#6e7681;font-size:12px;margin-top:4px}
.meta b{color:#9ca3af;font-weight:500}
.meta .err{color:#fca5a5}
.meta .port{color:#a78bfa;font-weight:600}
.btns{display:flex;gap:6px;flex-wrap:wrap}
.btn{background:#1f2430;color:#c9d1d9;border:0;border-radius:6px;padding:6px 11px;
  font-size:12px;cursor:pointer;font-weight:500;transition:.12s}
.btn:hover{background:#2a303d}
.btn.blue{background:#2563eb;color:#fff}.btn.blue:hover{background:#1d4ed8}
.btn.red{background:#dc2626;color:#fff}.btn.red:hover{background:#b91c1c}
.btn.green{background:#059669;color:#fff}.btn.green:hover{background:#047857}
.log{background:#05070a;border:1px solid #1f2430;border-radius:8px;padding:10px 12px;
  margin-top:12px;font-family:monospace;font-size:11.5px;line-height:1.5;
  height:260px;overflow:auto;white-space:pre-wrap;color:#c9d1d9;display:none}
.log.on{display:block}
.empty{text-align:center;color:#6e7681;padding:40px 20px;font-size:13px}
</style></head><body><div class="wrap">
<h1>Multi Hoster</h1>
<p class="sub">Drop multiple .py or .zip files. Each runs as its own project on a random port.</p>
<div class="drop" id="drop">
  <h2>Drop files here</h2>
  <span>or click to browse · multiple allowed</span>
  <input type="file" id="file" hidden accept=".py,.zip" multiple>
  <div class="prog" id="prog"><div></div></div>
</div>
<div id="list"></div>
</div>
<script>
const drop=document.getElementById('drop'), file=document.getElementById('file');
drop.onclick=()=>file.click();
['dragover','dragenter'].forEach(e=>drop.addEventListener(e,ev=>{ev.preventDefault();drop.classList.add('over')}));
['dragleave','drop'].forEach(e=>drop.addEventListener(e,ev=>{ev.preventDefault();drop.classList.remove('over')}));
drop.addEventListener('drop',ev=>{if(ev.dataTransfer.files.length)upload(ev.dataTransfer.files)});
file.onchange=()=>file.files.length&&upload(file.files);
const openLogs = new Set();
async function upload(files){
  const prog=document.getElementById('prog'); prog.style.display='block';
  const bar=prog.querySelector('div'); const total=files.length;
  for(let i=0;i<total;i++){
    const fd=new FormData(); fd.append('file',files[i]);
    bar.style.width=((i/total)*100)+'%';
    await fetch('/upload',{method:'POST',body:fd});
  }
  bar.style.width='100%';
  setTimeout(()=>{prog.style.display='none';bar.style.width='0';refresh()},300);
}
async function ctl(pid,action){await fetch(`/p/${pid}/${action}`,{method:'POST'});refresh()}
async function del(pid){if(!confirm('Delete project '+pid+'?'))return;
  await fetch(`/p/${pid}/delete`,{method:'POST'});refresh()}
function toggleLog(pid){
  if(openLogs.has(pid)) openLogs.delete(pid); else openLogs.add(pid);
  const el=document.getElementById('log-'+pid); if(el) el.classList.toggle('on');
}
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function refresh(){
  const r=await fetch('/status'); const j=await r.json();
  const list=document.getElementById('list'); const pids=Object.keys(j.projects);
  if(!pids.length){list.innerHTML='<div class="empty">No projects yet. Upload a file above.</div>';return}
  let html='';
  for(const pid of pids){
    const p=j.projects[pid];
    const dot=p.running?'dot on':'dot off';
    const st=p.running?'running':'stopped';
    const up=p.uptime?` · up ${p.uptime}`:'';
    const auto=p.enabled?'auto-restart on':'auto-restart off';
    const exitInfo = (!p.running && p.exit!==null && p.exit!==undefined)
      ? `<div class="meta err">exited with code ${p.exit}${p.port_conflicts?` · ${p.port_conflicts} port reassignment(s)`:''}</div>` : '';
    const logOpen = openLogs.has(pid) ? ' on' : '';
    const portInfo = p.port ? `<span class="port">:${p.port}</span>` : '';
    html+=`<div class="proj"><div class="head"><div>
      <div class="name"><span class="${dot}"></span>${esc(p.name)} ${portInfo}</div>
      <div class="meta"><b>id:</b> ${pid} · <b>entry:</b> ${esc(p.entry||'—')} · ${st}${up} · ${auto}</div>
      ${exitInfo}</div>
      <div class="btns">
        ${p.running?`<button class="btn" onclick="ctl('${pid}','stop')">Stop</button>`
                    :`<button class="btn green" onclick="ctl('${pid}','start')">Start</button>`}
        <button class="btn blue" onclick="ctl('${pid}','restart')">Restart</button>
        <button class="btn" onclick="ctl('${pid}','newport')">New Port</button>
        <button class="btn" onclick="ctl('${pid}','toggle')">${p.enabled?'Disable':'Enable'}</button>
        <button class="btn" onclick="toggleLog('${pid}')">Log</button>
        <button class="btn red" onclick="del('${pid}')">Delete</button>
      </div></div>
      <div class="log${logOpen}" id="log-${pid}">${esc((p.log||[]).join(''))}</div></div>`;
  }
  list.innerHTML=html;
  openLogs.forEach(pid=>{const el=document.getElementById('log-'+pid);
    if(el) el.scrollTop=el.scrollHeight;});
}
setInterval(refresh,1500); refresh();
</script></body></html>
"""

@app.route("/")
def home(): return render_template_string(HTML)

@app.post("/upload")
def upload():
    f = request.files.get("file")
    if not f: return jsonify(ok=False, error="no file"), 400
    pid = secrets.token_hex(3)
    proj_dir = PROJECTS_DIR / pid
    proj_dir.mkdir(parents=True, exist_ok=True)
    tmp = DATA / f"{pid}_{f.filename}"
    f.save(str(tmp))
    if f.filename.lower().endswith(".zip"):
        try:
            with zipfile.ZipFile(tmp) as z: z.extractall(proj_dir)
            items = list(proj_dir.iterdir())
            if len(items) == 1 and items[0].is_dir():
                inner = items[0]
                for c in inner.iterdir(): shutil.move(str(c), str(proj_dir / c.name))
                inner.rmdir()
        except Exception as e:
            shutil.rmtree(proj_dir, ignore_errors=True)
            return jsonify(ok=False, error=f"bad zip: {e}"), 400
        finally:
            try: tmp.unlink()
            except Exception: pass
    else:
        shutil.move(str(tmp), str(proj_dir / f.filename))
    name = f.filename.rsplit(".", 1)[0]
    with LOCK:
        PROJECTS[pid] = {"name": name, "entry": None, "enabled": True,
            "dir": proj_dir, "proc": None, "log": [], "started": None,
            "exit": None, "port": pick_port(), "port_conflicts": 0}
    save_state()
    threading.Thread(target=run_proc, args=(pid,), daemon=True).start()
    return jsonify(ok=True, id=pid)

@app.post("/p/<pid>/start")
def p_start(pid):
    if pid not in PROJECTS: return jsonify(ok=False), 404
    threading.Thread(target=run_proc, args=(pid,), daemon=True).start()
    return jsonify(ok=True)

@app.post("/p/<pid>/stop")
def p_stop(pid):
    if pid not in PROJECTS: return jsonify(ok=False), 404
    stop_proc(pid, reason="user stop"); return jsonify(ok=True)

@app.post("/p/<pid>/restart")
def p_restart(pid):
    if pid not in PROJECTS: return jsonify(ok=False), 404
    threading.Thread(target=run_proc, args=(pid,), daemon=True).start()
    return jsonify(ok=True)

@app.post("/p/<pid>/newport")
def p_newport(pid):
    p = PROJECTS.get(pid)
    if not p: return jsonify(ok=False), 404
    old = p.get("port"); new = pick_port(); p["port"] = new
    plog(pid, f"[hoster] port reassigned {old} → {new} (manual)\n")
    save_state()
    threading.Thread(target=run_proc, args=(pid, "manual-port"), daemon=True).start()
    return jsonify(ok=True, port=new)

@app.post("/p/<pid>/toggle")
def p_toggle(pid):
    p = PROJECTS.get(pid)
    if not p: return jsonify(ok=False), 404
    p["enabled"] = not p["enabled"]; save_state()
    return jsonify(ok=True, enabled=p["enabled"])

@app.post("/p/<pid>/delete")
def p_delete(pid):
    p = PROJECTS.get(pid)
    if not p: return jsonify(ok=False), 404
    stop_proc(pid, reason="delete")
    shutil.rmtree(p["dir"], ignore_errors=True)
    with LOCK: PROJECTS.pop(pid, None)
    save_state(); return jsonify(ok=True)

@app.get("/status")
def status():
    out = {}; now = time.time()
    with LOCK:
        for pid, p in PROJECTS.items():
            proc = p.get("proc")
            running = bool(proc and proc.poll() is None)
            up = None
            if running and p.get("started"):
                s = int(now - p["started"])
                up = f"{s//3600}h{(s%3600)//60}m{s%60}s"
            out[pid] = {"name": p["name"], "entry": p["entry"],
                "running": running, "uptime": up,
                "enabled": p["enabled"], "log": p["log"][-400:],
                "exit": p.get("exit"), "port": p.get("port"),
                "port_conflicts": p.get("port_conflicts", 0)}
    return jsonify(projects=out)

@app.get("/healthz")
def hz(): return "ok"

# ──────────────────────────────────────────────────────────── boot
if __name__ == "__main__":
    load_state()
    test_dir = PROJECTS_DIR / "test"
    if not test_dir.exists():
        test_dir.mkdir(parents=True, exist_ok=True)
        (test_dir / "main.py").write_text(
            "from http.server import BaseHTTPRequestHandler, HTTPServer\n"
            "class H(BaseHTTPRequestHandler):\n"
            "    def do_GET(self):\n"
            "        self.send_response(200)\n"
            "        self.send_header('Content-Type','text/plain')\n"
            "        self.end_headers()\n"
            "        self.wfile.write(b'Hello from hardcoded-port test!\\n')\n"
            "    def log_message(self, *a): pass\n"
            "print('binding to HARDCODED port 5000...', flush=True)\n"
            "HTTPServer(('0.0.0.0', 5000), H).serve_forever()\n"
        )
        with LOCK:
            PROJECTS["test"] = {"name": "test-web", "entry": None, "enabled": True,
                "dir": test_dir, "proc": None, "log": [], "started": None,
                "exit": None, "port": pick_port(), "port_conflicts": 0}
        save_state()
    for pid, p in list(PROJECTS.items()):
        if p["enabled"] and find_entry(p["dir"]):
            threading.Thread(target=run_proc, args=(pid,), daemon=True).start()
    threading.Thread(target=auto_restart_loop, daemon=True).start()
    print(f"[hoster] data dir: {DATA}")
    print(f"[hoster] python shim: {PY_SHIM}")
    print(f"[hoster] node shim:   {NODE_SHIM}")
    print(f"[hoster] hoster on http://0.0.0.0:{HOSTER_PORT}")
    app.run(host="0.0.0.0", port=HOSTER_PORT, threaded=True)
