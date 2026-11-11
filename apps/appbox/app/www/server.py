#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""appbox —— 容器商店后端（标准库实现，无第三方依赖）。

做四件事：
  1. 搜 Docker Hub / 读镜像标签，选镜像
  2. 生成 docker-compose.yaml 并启动容器
  3. 把用户上传的图标压成 256/64 两档，放进 appbox 自己的 ui/images
  4. 往 appcenter.app_service 写一行，重启应用中心 —— 桌面就多出一个图标

只操作自己创建的东西：容器名前缀 appbox-，数据目录在 DATA/apps/<slug>，
删除时也只删这些 + 对应的 app_service 行。
"""
import base64
import json
import os
import re
import shutil
import subprocess
import threading
import time
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DATA = os.environ.get("APPBOX_DATA", "/data")
APPS = os.path.join(DATA, "apps")
ICONS = os.environ.get("APPBOX_ICONS", "/icons")
PORT = int(os.environ.get("PORT", "38095"))
STATE = os.path.join(DATA, "state.json")
PUBLIC = os.environ.get("APPBOX_WWW", "/www")
PREFIX = "appbox-"
SERVICE_SUFFIX = ".main"
ICON_TEMPLATE = "ui/images/%s_{0}.png"

_lock = threading.Lock()


# ---------------------------------------------------------------- 基础工具
def sh(cmd, timeout=600, cwd=None):
    """执行命令，返回 (rc, 输出)。"""
    try:
        p = subprocess.run(cmd, shell=isinstance(cmd, str), cwd=cwd,
                           capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, "超时：%s" % (cmd if isinstance(cmd, str) else " ".join(cmd))
    except Exception as exc:  # noqa: BLE001
        return 1, str(exc)


def load_state():
    try:
        with open(STATE, encoding="utf-8") as fp:
            return json.load(fp)
    except Exception:  # noqa: BLE001
        return {"apps": []}


def save_state(state):
    os.makedirs(DATA, exist_ok=True)
    tmp = STATE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fp:
        json.dump(state, fp, ensure_ascii=False, indent=2)
    os.replace(tmp, STATE)


_COMPOSE = None


def compose_cmd():
    """优先用 docker compose 插件，没有就退回独立的 docker-compose。"""
    global _COMPOSE
    if _COMPOSE:
        return _COMPOSE
    for cand in (["docker", "compose"], ["docker-compose"]):
        rc, _ = sh(cand + ["version"], timeout=20)
        if rc == 0:
            _COMPOSE = cand
            return cand
    _COMPOSE = ["docker", "compose"]
    return _COMPOSE


def compose(path, *args, **kw):
    return sh(compose_cmd() + ["-f", path] + list(args), **kw)


def psql(sql):
    return sh(["psql", "-h", "/var/run/postgresql", "-U", "postgres",
               "-d", "appcenter", "-tAc", sql], timeout=30)


def sql_quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def slugify(text):
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return s[:32] or "app"


def valid_slug(slug):
    return bool(re.fullmatch(r"[a-z0-9][a-z0-9-]{1,31}", slug or ""))


def container_exists(name):
    rc, _ = sh(["docker", "inspect", name], timeout=15)
    return rc == 0


def app_id():
    rc, out = psql("select app_id from app_service where service_name='appbox.main' limit 1")
    if rc == 0 and out.strip().isdigit():
        return int(out.strip())
    rc, out = psql("select app_id from app_service order by id limit 1")
    return int(out.strip()) if rc == 0 and out.strip().isdigit() else 1


def control_json():
    rc, out = psql("select control from app_service where service_name='appbox.main' limit 1")
    out = (out or "").strip()
    if rc == 0 and out.startswith("{"):
        return out
    return ('{"show":0,"showRoute":0,"auth":0,"port":0,"path":0,"fullUrl":0,'
            '"accessPerm":"editable","portPerm":"editable","pathPerm":"editable",'
            '"fullUrlPerm":"editable"}')


def register_desktop(slug, title, port, icon_base):
    """插一行 app_service，然后重启应用中心让桌面出现图标。"""
    svc = slug + SERVICE_SUFFIX
    icon = ICON_TEMPLATE % slug
    url = "http://${host}:%d/" % port
    sql = (
        "insert into app_service (app_id, service_name, title, \"desc\", icon, type, url, "
        "default_url, is_admin, control, feature, file_types, no_display) values (%d, %s, %s, '', "
        "%s, 'url', %s, %s, true, %s, '{}', '[]', false) on conflict do nothing;"
        % (app_id(), sql_quote(svc), sql_quote(title), sql_quote(icon),
           sql_quote(url), sql_quote(url), sql_quote(control_json()))
    )
    rc, out = psql(sql)
    if rc != 0:
        return False, out.strip()
    return True, ""


def unregister_desktop(slug):
    psql("delete from app_service where service_name=%s" % sql_quote(slug + SERVICE_SUFFIX))


def reload_appcenter():
    """用一次性特权容器 nsenter 进宿主机重启应用中心（服务端缓存了服务列表）。"""
    rc, out = sh(["docker", "run", "--rm", "--privileged", "--pid=host",
                  "alpine:3.20", "nsenter", "-t", "1", "-m", "-p",
                  "systemctl", "restart", "trim_app_center"], timeout=180)
    return rc == 0, out.strip()[-300:]


def save_icons(slug, data_url):
    """把上传的图片存成 <slug>_256.png / <slug>_64.png，返回文件名列表。"""
    if not data_url:
        return []
    raw = data_url.split(",", 1)[-1]
    blob = base64.b64decode(raw)
    if len(blob) > 6 * 1024 * 1024:
        raise ValueError("图标不能超过 6MB")
    os.makedirs(ICONS, exist_ok=True)
    path256 = os.path.join(ICONS, "%s_256.png" % slug)
    path64 = os.path.join(ICONS, "%s_64.png" % slug)
    try:
        from PIL import Image  # noqa: PLC0415
        import io  # noqa: PLC0415
        img = Image.open(io.BytesIO(blob)).convert("RGBA")
        side = min(img.size)
        img = img.crop(((img.width - side) // 2, (img.height - side) // 2,
                        (img.width + side) // 2, (img.height + side) // 2))
        img.resize((256, 256), Image.LANCZOS).save(path256, "PNG")
        img.resize((64, 64), Image.LANCZOS).save(path64, "PNG")
    except Exception:  # noqa: BLE001
        with open(path256, "wb") as fp:
            fp.write(blob)
        with open(path64, "wb") as fp:
            fp.write(blob)
    return [os.path.basename(path256), os.path.basename(path64)]


def remove_icons(slug):
    for suffix in ("_256.png", "_64.png"):
        try:
            os.remove(os.path.join(ICONS, slug + suffix))
        except OSError:
            pass


def compose_yaml(app):
    lines = [
        "services:",
        "  app:",
        "    image: %s:%s" % (app["image"], app["tag"]),
        "    container_name: %s%s" % (PREFIX, app["slug"]),
        "    restart: unless-stopped",
        "    ports:",
        '      - "%d:%d"' % (app["hostPort"], app["containerPort"]),
    ]
    env = [line.strip() for line in app.get("env", []) if line.strip()]
    if env:
        lines.append("    environment:")
        lines += ['      - %s' % json.dumps(item, ensure_ascii=False) for item in env]
    vols = [line.strip() for line in app.get("volumes", []) if line.strip()]
    if vols:
        lines.append("    volumes:")
        lines += ['      - %s' % json.dumps(item, ensure_ascii=False) for item in vols]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- 部署 / 删除
def do_deploy(payload):
    image = (payload.get("image") or "").strip()
    tag = (payload.get("tag") or "latest").strip()
    title = (payload.get("title") or "").strip() or image.split("/")[-1]
    slug = slugify(payload.get("slug") or title)
    if not image or "/" not in image and ":" not in image:
        return False, "镜像名不合法"
    if not valid_slug(slug):
        return False, "名称只能用 2-32 位小写字母、数字、短横线"
    if container_exists(PREFIX + slug):
        return False, "容器 %s%s 已存在" % (PREFIX, slug)

    host_port = int(payload.get("hostPort") or 0)
    cont_port = int(payload.get("containerPort") or 0)
    if not (1 <= host_port <= 65535 and 1 <= cont_port <= 65535):
        return False, "端口不合法"

    logs = []
    rc, out = sh(["docker", "pull", "%s:%s" % (image, tag)], timeout=1800)
    logs.append(out.strip()[-600:])
    if rc != 0:
        return False, "拉取镜像失败：\n" + logs[-1]

    app = {
        "slug": slug, "title": title, "image": image, "tag": tag,
        "hostPort": host_port, "containerPort": cont_port,
        "env": payload.get("env") or [], "volumes": payload.get("volumes") or [],
        "createdAt": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    app_dir = os.path.join(APPS, slug)
    os.makedirs(app_dir, exist_ok=True)
    compose_path = os.path.join(app_dir, "docker-compose.yaml")
    with open(compose_path, "w", encoding="utf-8") as fp:
        fp.write(compose_yaml(app))

    rc, out = compose(compose_path, "up", "-d", timeout=600)
    logs.append(out.strip()[-600:])
    if rc != 0:
        return False, "启动失败：\n" + logs[-1]

    icons = save_icons(slug, payload.get("icon"))

    registered = False
    if icons:
        registered, err = register_desktop(slug, title, host_port, slug)
        if registered:
            ok, msg = reload_appcenter()
            logs.append("桌面图标已注册" + ("，应用中心已重启" if ok else "，但重启应用中心失败：" + msg))
        else:
            logs.append("写数据库失败，跳过桌面图标：" + err)
    else:
        logs.append("未上传图标，只部署容器、不注册桌面图标")

    app["icon"] = bool(icons)
    app["registered"] = registered
    with _lock:
        state = load_state()
        state["apps"] = [a for a in state["apps"] if a["slug"] != slug] + [app]
        save_state(state)
    return True, "\n".join(x for x in logs if x)


def do_remove(slug):
    if not valid_slug(slug):
        return False, "名称不合法"
    with _lock:
        state = load_state()
        app = next((a for a in state["apps"] if a["slug"] == slug), None)
        if not app:
            return False, "没找到这个应用"
        app_dir = os.path.join(APPS, slug)
        compose_path = os.path.join(app_dir, "docker-compose.yaml")
        logs = []
        if os.path.isfile(compose_path):
            rc, out = compose(compose_path, "down", timeout=300)
            logs.append(out.strip()[-300:])
        sh(["docker", "rm", "-f", PREFIX + slug], timeout=120)
        shutil.rmtree(app_dir, ignore_errors=True)
        remove_icons(slug)
        unregister_desktop(slug)
        ok, msg = reload_appcenter()
        logs.append("已从桌面移除" + ("" if ok else "（重启应用中心失败：" + msg + "）"))
        state["apps"] = [a for a in state["apps"] if a["slug"] != slug]
        save_state(state)
    return True, "\n".join(x for x in logs if x)


def list_apps():
    state = load_state()
    out = []
    for app in state.get("apps", []):
        name = PREFIX + app["slug"]
        rc, txt = sh(["docker", "inspect", "-f",
                      "{{.State.Status}}", name], timeout=15)
        app = dict(app)
        app["status"] = txt.strip() if rc == 0 else "missing"
        out.append(app)
    return out


# ---------------------------------------------------------------- Docker Hub
def hub_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "appbox/1.0",
                                               "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=12) as resp:
        return json.load(resp)


def search_images(query):
    data = hub_json("https://hub.docker.com/v2/search/repositories/?query=%s&page_size=12"
                    % urllib.parse.quote(query))
    out = []
    for item in data.get("results", []):
        out.append({
            "image": item.get("repo_name"),
            "name": item.get("name") or item.get("repo_name", "").split("/")[-1],
            "description": (item.get("short_description") or "")[:120],
            "stars": item.get("star_count", 0),
            "official": bool(item.get("is_official")),
            "pulls": item.get("pull_count", 0),
        })
    return out


def list_tags(image, limit=25):
    url = ("https://hub.docker.com/v2/repositories/%s/tags?page_size=%d&ordering=last_updated"
           % (image, limit))
    data = hub_json(url)
    out = []
    for item in data.get("results", []):
        out.append({
            "tag": item.get("name"),
            "updated": (item.get("last_updated") or "")[:10],
            "size": item.get("full_size") or 0,
        })
    return out


def image_info(image, tag):
    ref = "%s:%s" % (image, tag)
    rc, _ = sh(["docker", "image", "inspect", ref], timeout=15)
    if rc != 0:
        rc, out = sh(["docker", "pull", ref], timeout=1800)
        if rc != 0:
            return {"ok": False, "error": out.strip()[-300:]}
    rc, out = sh(["docker", "image", "inspect", ref], timeout=30)
    if rc != 0:
        return {"ok": False, "error": "inspect 失败"}
    try:
        info = json.loads(out)[0]
    except Exception:  # noqa: BLE001
        return {"ok": False, "error": "解析 inspect 输出失败"}
    cfg = info.get("Config") or {}
    ports = [p.split("/")[0] for p in (cfg.get("ExposedPorts") or {})]
    return {
        "ok": True,
        "ports": ports,
        "volumes": list((cfg.get("Volumes") or {}).keys()),
        "env": [e for e in (cfg.get("Env") or []) if not e.startswith(("PATH=", "HOME="))][:12],
    }


# ---------------------------------------------------------------- HTTP
class Handler(BaseHTTPRequestHandler):
    server_version = "appbox/1.0"

    def log_message(self, fmt, *args):  # noqa: A003
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False))

    def _body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def do_GET(self):  # noqa: N802
        path = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(path.query)
        try:
            if path.path in ("/", "/index.html"):
                with open(os.path.join(PUBLIC, "index.html"), "rb") as fp:
                    return self._send(200, fp.read(), "text/html; charset=utf-8")
            if path.path == "/api/apps":
                return self._json({"apps": list_apps()})
            if path.path == "/api/search":
                return self._json({"results": search_images(qs.get("q", [""])[0])})
            if path.path == "/api/tags":
                return self._json({"tags": list_tags(qs.get("image", [""])[0])})
            if path.path == "/api/inspect":
                return self._json(image_info(qs.get("image", [""])[0],
                                             qs.get("tag", ["latest"])[0]))
            if path.path == "/api/health":
                return self._json({"ok": True, "port": PORT})
            return self._json({"error": "not found"}, 404)
        except Exception as exc:  # noqa: BLE001
            return self._json({"error": str(exc)}, 500)

    def do_POST(self):  # noqa: N802
        path = urllib.parse.urlparse(self.path).path
        try:
            payload = self._body()
        except Exception as exc:  # noqa: BLE001
            return self._json({"ok": False, "error": "请求体解析失败：%s" % exc}, 400)
        try:
            if path == "/api/deploy":
                ok, msg = do_deploy(payload)
                return self._json({"ok": ok, "log": msg})
            if path == "/api/remove":
                ok, msg = do_remove((payload.get("slug") or "").strip())
                return self._json({"ok": ok, "log": msg})
            return self._json({"ok": False, "error": "not found"}, 404)
        except Exception as exc:  # noqa: BLE001
            return self._json({"ok": False, "error": str(exc)}, 500)


if __name__ == "__main__":
    os.makedirs(APPS, exist_ok=True)
    print("appbox listening on 0.0.0.0:%d" % PORT, flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
