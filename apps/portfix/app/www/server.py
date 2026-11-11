#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PortFix：把飞牛桌面图标里记录的端口，一键改成应用的真实端口。

背景：飞牛在安装那一刻把 `app_service.url` 写死成包内 ui/config 的 port，
之后不管你把应用改到哪个端口，图标都还指向原来那个号。这个工具直接读
数据库里每条图标记录，跟应用 compose 里真实的端口比对，列出不一致的，
点一下就能改过来。

权限：容器以 root 运行，挂载宿主机的 /var/run/postgresql（pg_hba 里
`local all postgres peer map=trim_root` 把 root 映射成 postgres），
所以能读写 appcenter 库。只读挂载 /vol1/@appcenter 用来解析 compose。
"""
import json
import os
import re
import subprocess
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

APPS_ROOT = os.environ.get("APPS_ROOT", "/apps")
PG_SOCKET = os.environ.get("PG_SOCKET", "/var/run/postgresql")
PORT = int(os.environ.get("PORTFIX_PORT", "38090"))

PORT_RE = re.compile(r":(\d+)/")


def psql(sql):
    """执行 SQL，返回 (ok, 行列表)。"""
    try:
        r = subprocess.run(
            ["psql", "-h", PG_SOCKET, "-U", "postgres", "-d", "appcenter",
             "-A", "-F", "\t", "-t", "-c", sql],
            capture_output=True, text=True, timeout=15,
        )
    except Exception as e:  # noqa: BLE001
        return False, [str(e)]
    if r.returncode != 0:
        return False, [(r.stderr or r.stdout).strip()]
    rows = [line.split("\t") for line in r.stdout.splitlines() if line.strip()]
    return True, rows


WEB_HINTS = ("WEB", "MANAGER", "DASHBOARD", "GOPEED", "PORTFIX", "HTTP")


def _compose_path(app):
    return os.path.join(APPS_ROOT, app, "docker", "docker-compose.yaml")


def _container_name(app, txt):
    m = re.search(r"container_name://s*([A-Za-z0-9_.-]+)", txt)
    return m.group(1) if m else app


def _docker_inspect(name):
    try:
        r = subprocess.run(["docker", "inspect", name],
                           capture_output=True, text=True, timeout=10)
        if r.returncode != 0:
            return None
        data = json.loads(r.stdout)
        return data[0] if data else None
    except Exception:  # noqa: BLE001
        return None


def detect_ports(app):
    """返回 (候选端口列表, 首选端口)。候选来自容器的端口映射与环境变量。"""
    path = _compose_path(app)
    if not os.path.isfile(path):
        return [], None
    try:
        txt = open(path, encoding="utf-8", errors="ignore").read()
    except OSError:
        return [], None

    name = _container_name(app, txt)
    info = _docker_inspect(name)

    cands, preferred = [], None

    if info:
        # 1) bridge 模式：端口映射的宿主端口
        ports = (info.get("NetworkSettings") or {}).get("Ports") or {}
        for _, binds in ports.items():
            for b in (binds or []):
                hp = b.get("HostPort")
                if hp and hp.isdigit():
                    cands.append(int(hp))
        # 2) 环境变量里的 *PORT=（host 模式只能看这个）
        for kv in (info.get("Config") or {}).get("Env") or []:
            if "=" not in kv:
                continue
            k, v = kv.split("=", 1)
            if k.endswith("_PORT") or k == "PORT":
                if v.isdigit():
                    n = int(v)
                    cands.append(n)
                    if any(h in k for h in WEB_HINTS):
                        preferred = preferred or n

    # 3) 兜底：直接用 compose 里的字面量（没占位符的应用，如 emby "8096:8096"）
    for a, b in re.findall(r'-\s*"?(\d+):(\d+)"?', txt):
        cands.append(int(a))

    seen, out = set(), []
    for c in cands:
        if 1 <= c <= 65535 and c not in seen:
            seen.add(c)
            out.append(c)

    if preferred is None and out:
        preferred = out[0]
    return out, preferred


def build_list():
    ok, rows = psql(
        "select service_name, coalesce(title,''), url from app_service order by service_name"
    )
    if not ok:
        return {"ok": False, "error": rows[0] if rows else "psql 失败", "items": []}

    items = []
    for row in rows:
        if len(row) < 3:
            continue
        service, title, url = row[0], row[1], row[2]
        app = service.split(".")[0]
        m = PORT_RE.search(url)
        icon_port = int(m.group(1)) if m else None
        cands, preferred = detect_ports(app)

        if icon_port is None:
            status = "noport"          # 地址里没有端口（走 /app 网关），不用管
            real = None
        elif not cands:
            status = "unknown"         # 拿不到端口信息
            real = None
        elif icon_port in cands:
            status = "ok"              # 图标端口确实在用
            real = icon_port
        else:
            status = "mismatch"
            real = preferred

        items.append({
            "service": service, "title": title or service, "url": url,
            "icon_port": icon_port, "real_port": real, "status": status,
        })
    return {"ok": True, "items": items}


def fix_one(service, port):
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", service or ""):
        return False, "服务名不合法"
    if not (1 <= port <= 65535):
        return False, "端口超出范围"

    # 只允许数据库里已存在的记录
    ok, rows = psql("select count(*) from app_service where service_name = '%s'" % service)
    if not ok or not rows or rows[0][0].strip() != "1":
        return False, "数据库里没有这条记录：%s" % service

    sql = ("update app_service set url = regexp_replace(url, ':[0-9]+/', ':%d/') "
           "where service_name = '%s' and url ~ ':[0-9]+/'" % (port, service))
    ok, rows = psql(sql)
    if not ok:
        return False, rows[0] if rows else "更新失败"
    return True, "已把 %s 的图标地址改到 %d" % (service, port)


PAGE = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>端口修复</title>
<style>
:root{--bg:#f7f8fa;--card:#fff;--line:#e5e7eb;--text:#1f2328;--muted:#6b7280;
      --ok:#15803d;--warn:#b45309;--err:#b91c1c;--accent:#2563eb}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);
     font:14px/1.6 -apple-system,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif}
.wrap{max-width:1100px;margin:0 auto;padding:28px 20px 60px}
h1{font-size:20px;margin:0 0 6px}
.sub{color:var(--muted);margin:0 0 20px;font-size:13px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;overflow:hidden}
table{width:100%;border-collapse:collapse}
th,td{padding:10px 14px;text-align:left;border-bottom:1px solid var(--line);vertical-align:middle}
th{background:#fafbfc;font-weight:600;font-size:12px;color:var(--muted);
   text-transform:uppercase;letter-spacing:.03em}
tr:last-child td{border-bottom:none}
code{background:#f3f4f6;padding:1px 5px;border-radius:4px;font-size:12px}
.tag{display:inline-block;padding:1px 8px;border-radius:99px;font-size:12px;font-weight:500}
.t-ok{background:#dcfce7;color:var(--ok)}
.t-mismatch{background:#fef3c7;color:var(--warn)}
.t-noport{background:#eef2f7;color:var(--muted)}
.t-unknown{background:#eef2f7;color:var(--muted)}
button{border:1px solid var(--accent);background:var(--accent);color:#fff;
       padding:5px 12px;border-radius:6px;cursor:pointer;font-size:13px}
button:hover{opacity:.9}
button:disabled{background:#e5e7eb;border-color:#e5e7eb;color:#9ca3af;cursor:default}
input[type=number]{width:88px;padding:4px 8px;border:1px solid var(--line);border-radius:6px}
.hint{margin-top:16px;color:var(--muted);font-size:12.5px;line-height:1.8}
.toast{position:fixed;left:50%;bottom:28px;transform:translateX(-50%);
       background:#111827;color:#fff;padding:9px 18px;border-radius:8px;
       font-size:13px;opacity:0;transition:.25s;pointer-events:none}
.toast.show{opacity:1}
.empty{padding:36px;text-align:center;color:var(--muted)}
</style></head><body><div class="wrap">
<h1>端口修复</h1>
<p class="sub">飞牛桌面图标的地址是安装时写死的，改了应用端口后图标会打不开。这里列出所有图标记录，
跟应用实际端口比对，不一致的一键改过来。</p>
<div class="card"><table>
<thead><tr><th style="width:26%">应用</th><th style="width:28%">图标地址</th>
<th style="width:12%">图标端口</th><th style="width:12%">实际端口</th>
<th style="width:12%">状态</th><th style="width:10%"></th></tr></thead>
<tbody id="tb"><tr><td colspan="6" class="empty">读取中…</td></tr></tbody>
</table></div>
<p class="hint">
· <b>一致</b>：图标端口等于应用实际端口，不用动。<br>
· <b>不一致</b>：点「修复」把图标地址改成实际端口，立刻生效（重登桌面或强刷）。<br>
· <b>无端口</b>：走飞牛网关的应用（<code>http://host/app/xxx</code>），本来就不带端口，不用管。<br>
· <b>实际端口</b>是读应用目录里的 compose 猜出来的；猜不准时可以直接在输入框里填正确值再修复。<br>
· 重装应用后飞牛会按包内配置重写这条记录，需要再修一次。
</p></div>
<div class="toast" id="toast"></div>
<script>
function toast(msg){const t=document.getElementById('toast');t.textContent=msg;
  t.classList.add('show');clearTimeout(t._h);t._h=setTimeout(()=>t.classList.remove('show'),2200);}
const TAG={ok:['一致','t-ok'],mismatch:['不一致','t-mismatch'],
  noport:['无端口','t-noport'],unknown:['端口未知','t-unknown']};
function esc(s){return (s||'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));}
async function load(){
  const r=await fetch('/api/list');const d=await r.json();
  const tb=document.getElementById('tb');
  if(!d.ok){tb.innerHTML='<tr><td colspan="6" class="empty">'+esc(d.error||'读取失败')+'</td></tr>';return;}
  if(!d.items.length){tb.innerHTML='<tr><td colspan="6" class="empty">没有记录</td></tr>';return;}
  tb.innerHTML=d.items.map(it=>{
    const [label,cls]=TAG[it.status]||['?',''];
    const canFix=it.status==='mismatch'||it.status==='unknown';
    const port=it.real_port??'';
    return `<tr>
      <td><b>${esc(it.title)}</b><br><code>${esc(it.service)}</code></td>
      <td><code>${esc(it.url)}</code></td>
      <td>${it.icon_port??'—'}</td>
      <td>${canFix?`<input type="number" id="p_${esc(it.service)}" value="${port}" min="1" max="65535">`:(it.real_port??'—')}</td>
      <td><span class="tag ${cls}">${label}</span></td>
      <td>${canFix?`<button onclick="fix('${esc(it.service)}')">修复</button>`:''}</td>
    </tr>`;
  }).join('');
}
async function fix(service){
  const el=document.getElementById('p_'+service);
  const port=el?parseInt(el.value,10):NaN;
  if(!port||port<1||port>65535){toast('端口不合法');return;}
  const r=await fetch('/api/fix?service='+encodeURIComponent(service)+'&port='+port);
  const d=await r.json();
  toast(d.ok?d.msg:(d.error||'失败'));
  if(d.ok) load();
}
load();
</script></body></html>
"""


class Handler(BaseHTTPRequestHandler):
    server_version = "PortFix/1.0"

    def log_message(self, fmt, *args):  # 安静一点
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        raw = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)

        if path in ("/", "/index.html"):
            self._send(200, PAGE, "text/html; charset=utf-8")
            return

        if path == "/api/list":
            self._send(200, json.dumps(build_list(), ensure_ascii=False))
            return

        if path == "/api/fix":
            try:
                port = int(qs.get("port", ["0"])[0])
            except ValueError:
                port = 0
            service = qs.get("service", [""])[0]
            ok, msg = fix_one(service, port)
            self._send(200, json.dumps(
                {"ok": ok, "msg": msg if ok else "", "error": "" if ok else msg},
                ensure_ascii=False))
            return

        self._send(404, json.dumps({"ok": False, "error": "not found"}))


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
