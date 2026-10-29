# fnos-apps

把常用的 Docker 应用封装成 **fnOS（飞牛 OS）原生应用包（`.fpk`）** 的构建源码集合。

作者与维护者：**vinson023**（各包 `manifest` 里的 `maintainer` 字段同此值）。

封装后这些容器不再是「Docker 应用」里的一个条目，而是变成应用中心里的正式应用：有独立图标、
能出现在 fnOS 桌面、点击即打开（`type` 决定是桌面内 iframe 窗口还是新浏览器页签）、
随应用中心统一启停，并且可以通过 `appcenter-cli` 脚本化管理。

## 应用列表

| 应用 | appname | 端口 | 容器镜像 | 桌面打开方式 | 安装向导可配置 |
|---|---|---|---|---|---|
| AriaNg | `aria2ng` | 6880 | `nginx:alpine`（托管 AriaNg 静态站） | iframe 窗口 1280×860 | 无（界面里填，或写服务端 `rpc-config.js`） |
| Emby | `emby` | 8096 | `amilys/embyserver:latest` | 新页签 | 配置目录、媒体库目录 |
| Music-DL | `music-dl` | 8099 | `guohuiyuan/go-music-dl:latest` | 新页签 | 下载目录、数据目录 |
| ReClip | `video-download-reclip` | 8899 | `reclipd/reclip:latest` | 新页签 | 数据目录 |
| MeTube | `metube` | 8081 | `ghcr.io/alexta69/metube:latest` | 新页签 | 配置目录、下载目录 |
| RustDesk Server | `rustdesk` | 21115–21120 | `rustdesk/rustdesk-server:latest` | iframe 窗口 900×760 | 数据目录、中继地址、密钥、强制中继 |
| Motrix | `motrix` | 8080、16801、6881 | `motrixapp/motrix-server:latest` | iframe 窗口 1280×860 | 数据目录、下载目录、登录密码、对外地址 |
| MoviePilot | `moviepilot` | 3000 | `jxxghp/moviepilot-v2:latest` | iframe 窗口 1280×860 | 数据目录、媒体库、下载目录、管理员账号 |

**八个应用里七个带安装向导**：装的时候就能选数据目录、媒体库、下载目录这些路径，选完 compose 自动按选择生效，不用装完再改文件。机制见下面「安装向导」一节。
唯一没有向导的是 `aria2ng`——它是纯静态站点，没有任何需要配置的路径。

## 仓库结构

```
apps/<appname>/
├── manifest                # 应用元信息：名称、版本、端口、桌面入口
├── ICON.PNG / ICON_256.PNG # 应用中心与桌面图标
├── app/
│   ├── ui/
│   │   ├── config          # 桌面入口定义（type: iframe | url）
│   │   └── images/         # 图标
│   └── docker/
│       ├── docker-compose.yaml
│       └── ...             # 应用自有静态资源（如 aria2ng 的 html/ 与 default.conf）
├── cmd/                    # 生命周期钩子，main 需处理 start/stop/status
├── config/
│   ├── resource            # 必须含 docker-project 段，否则被识别为普通应用
│   └── privilege           # 运行身份
└── wizard/
    └── install             # 安装向导（八个应用都有，字段值经 ${wizard_xxx} 进 compose）
```

## 构建

需要 fnOS 官方的 `fnpack`：

```bash
fnpack build -d apps/aria2ng
# 产物落在当前工作目录：aria2ng.fpk
```

或一次构建全部：

```bash
./scripts/build.sh          # 产物统一输出到 dist/
```

## 安装与升级

`appcenter-cli` 使用**位置参数**，没有 `-a` 这种短选项：

```bash
appcenter-cli install-fpk aria2ng.fpk
appcenter-cli start aria2ng
appcenter-cli status aria2ng
```

**升级必须先卸载**：`install-fpk` 对同名已装应用不会重新解压 `/vol1/@appcenter/<app>/`，
直接覆盖会导致容器仍从旧 compose 启动。

```bash
docker rm -f aria2ng
appcenter-cli uninstall aria2ng
appcenter-cli install-fpk aria2ng.fpk
appcenter-cli start aria2ng
```

**带向导的应用用命令行安装时必须传 `-e`**，且要包含全部向导字段，
否则会直接报 `Something wrong with environment variables` 并拒绝安装（这反而是个安全网：
不会出现路径为空、挂载落到 `/` 的情况）。文件格式是纯 `KEY=value`：

```bash
cat > a.env <<'EOF'
wizard_data_dir=/vol1/1000/docker/emby
wizard_media_dir=/vol1/1000/video
EOF
appcenter-cli install-fpk emby.fpk -e a.env
```

两个坑：**不能加 `export` 前缀**（会失败），**不能有空值**（会让 CLI 段错误崩溃，
真实错误码要看 `/var/log/trim_app_center/error.log`）。在应用中心里点「手动安装」
走图形向导则不需要关心这些。

## 安装向导（wizard）

向导定义在 `wizard/install`，是一个 JSON 数组，每个元素是一个步骤。控件类型有
`text` / `password` / `radio` / `checkbox` / `select` / `switch` / `tips`，
`field` 名**就是环境变量名**（不带 `TRIM_` 前缀）。

让向导值真正影响容器的方式只有一条：

```
wizard/install 里的 field 名
        ↓
fnOS 在创建容器前，对 app/docker/docker-compose.yaml 做 ${wizard_xxx} 字符串替换
        ↓
volumes: - ${wizard_data_dir}/config:/config   ← 挂载真的落在用户选的路径上
```

关键点：**容器在 `install_callback` 之前就已经按 compose 建好了**，
所以在回调脚本里改写 compose 文件是无效的，必须用 `${wizard_xxx}` 占位符。

每个 `text` 字段都配了 `required` + `pattern` 规则（只允许绝对路径、禁止空格），
目的是挡住会导致挂载异常的值。`pattern` 里**不能允许空格**——中继地址这类值会被
当成参数传给容器内的进程，带空格可能被拆成多个参数。

容器由 fnOS 通过 Docker API 管理（`config/resource` 里的 `docker-project` 段），
生命周期脚本以「应用用户」身份运行、**没有 docker 权限**，所以不要在回调里
`docker compose up`，会报 `code 10237: Docker 服务未运行或无权限访问`。

## 各应用的挂载点

路径都在安装向导里选，默认值与 fnOS 标准布局一致。

`aria2ng` 是纯静态站点，**没有安装向导、也没有任何数据目录挂载**，所以不在下表内。

| 应用 | 向导字段 | 默认值 | 容器内 |
|---|---|---|---|
| `emby` | `wizard_data_dir` | `/vol1/1000/docker/emby` | `/config`（其下 `config` 子目录） |
| `emby` | `wizard_media_dir` | `/vol1/1000/video` | `/media` |
| `music-dl` | `wizard_download_dir` | `/vol1/1000/Download` | `/home/appuser/data/downloads` |
| `music-dl` | `wizard_data_dir` | `/vol1/1000/docker/music-dl` | `/home/appuser/data` |
| `video-download-reclip` | `wizard_data_dir` | `/vol1/1000/docker/reclip` | `/app/data`（其下 `reclip_data` 子目录） |
| `metube` | `wizard_data_dir` | `/vol1/1000/docker/metube` | `/config`（其下 `config` 子目录） |
| `metube` | `wizard_download_dir` | `/vol1/1000/docker/metube/downloads` | `/downloads` |
| `rustdesk` | 四个字段 | 见下 | 见下 |
| `motrix` | `wizard_data_dir` | `/vol1/1000/docker/motrix` | `/data`（其下 `data` 子目录） |
| `motrix` | `wizard_download_dir` | `/vol1/1000/Download` | `/downloads` |
| `motrix` | `wizard_operator_token` | 无（必须自己设） | Web 登录密码 |
| `motrix` | `wizard_public_url` | 留空 | 远程配对审批地址，非挂载 |
| `moviepilot` | `wizard_data_dir` | `/vol1/1000/docker/moviepilot` | `/config` 与 `/moviepilot/.cloakbrowser`（两个子目录） |
| `moviepilot` | `wizard_media_dir` | `/vol1/1000/video` | `/media` |
| `moviepilot` | `wizard_download_dir` | `/vol1/1000/Download` | `/downloads` |
| `moviepilot` | `wizard_superuser` / `wizard_superuser_password` | `admin` / 无（必须自己设） | 超级管理员账号，非挂载 |

Music-DL 的两个挂载点以镜像内的实际路径为准，不要随意改：

| 宿主机 | 容器内 | 用途 |
|---|---|---|
| `wizard_download_dir` | `/home/appuser/data/downloads` | 下载的音乐文件 |
| `wizard_data_dir` | `/home/appuser/data` | 配置、缓存、日志 |

镜像里**没有** `/app/data` 这个路径，挂到那里数据不会被读到。

## 桌面打开方式（iframe / 新页签）

由 `app/ui/config` 里 `.url.<id>.type` 决定：

- `"iframe"` → 在 fnOS 桌面内开窗口，可用 `width` / `height` 指定尺寸（AriaNg 用 1280×860）；
- `"url"` → 新开浏览器页签。

**已安装的应用改 `ui/config` 不会立即生效**。`open_type` 有三层数据源，且以数据库为根源：

```
appcenter.app_service.type      ← 根源，trim_sac 重启时据此重建下层
appcenter.app_open.open_type
trim_sac.entry.open_type        ← 展示层
```

只改 `trim_sac.entry` 会被覆盖回原值，必须从 `app_service` 改起。反过来，
**重新安装 fpk 时包里的 `ui/config` 会写回数据库**——所以源码里的值必须和期望一致，
否则每次重装都会被打回。本项目曾因 Emby 源码里遗留 `iframe` 而反复变回窗口模式。

## AriaNg 的五个注意点

1. **纯静态，没有任何反向代理**。`app/docker/default.conf` 只做静态托管，容器里没有
   `proxy_pass`。AriaNg 以浏览器的身份直接去连 aria2 的 RPC 端口，依赖 aria2 自带的
   CORS 头（`Access-Control-Allow-Origin: *`，标准 aria2 与 aria2-pro 镜像都默认开启，
   实测连 `OPTIONS` 预检都正常应答）。

   好处是这个应用**完全不需要知道 aria2 在哪**，没有预设地址、没有密钥下发、没有向导字段。
   代价是默认情况下**换设备或换浏览器访问时要重新填一次 RPC**（配置在 localStorage，按
   origin 隔离）——1.0.3 用「服务端配置」解决这个问题，见第 3 点。

2. **零补丁，只有一处默认语言**。`html/` 直接用官方 AriaNg v1.2.3 的 release 包，
   唯一改动是把 `ariaNgDefaultOptions.language` 从 `"en"` 改成 `"zh_Hans"`——一个常量，
   界面上随时能改回去。没有语言锁定、没有 RPC 锁定。

   这里踩过两个坑，值得记一笔：

   - **语言值必须是 `en` / `zh_Hans` / `zh_Hant` 三者之一**。语言 loader 第一句就是
     `if(!c[t.key]) return n.reject(t.key)`，传 `zh_CN` 会被直接 reject，整站回落到
     内置英文表。`zh_CN` 只是 `zh_Hans` 的别名，只有在 `b()` 做别名解析时才有效，
     不能当 loader 的 key。
   - **`try_files ... /index.html` 的兜底会把 index.html 当成语言文件返回**。
     缺失的 `langs/xxx.txt` 会返回 200 + HTML，AriaNg 解析出一堆垃圾键，同样表现为英文。
     所以 `default.conf` 给 `/langs/` 单独加了 `try_files $uri =404`。

3. **1.0.3 起：配置放在服务端，所有设备看到同一份**。这是用户明确要求的行为——
   「这个应用装在飞牛上，设置就不该随着我在哪台设备、哪个地址打开而变化，要像远程桌面一样」。

   做法是新增 `app/docker/html/rpc-config.js`（nginx 托管，随包发布，`host` 留空）：

   ```js
   window.ARIA2NG_RPC = {
       host: "",          // 留空 = 不启用，退回「在界面里手动填」
       port: "6800",
       interface: "jsonrpc",
       protocol: "http",
       secret: ""         // 明文，页面自己转 base64
   };
   ```

   `index.html` 的 `<head>` 内联脚本（`<meta charset>` 之后、Angular 之前）在**每次加载**时
   读它并覆盖 localStorage 里的 `AriaNg.Options`。填了 `host` 就以服务端为准，连语言都锁成
   简体中文；`host` 留空则完全不介入，走下面的手动/迁移逻辑。

   nginx 侧必须给这个文件**精确匹配 + 禁缓存 + 缺失时 404**：

   ```nginx
   location = /rpc-config.js {
       try_files $uri =404;
       add_header Cache-Control "no-cache, no-store, must-revalidate";
       expires -1;
   }
   ```

   三个坑：`location =` 要写在 `location ~* \.(js|css|html|txt)$` 附近，精确匹配优先级更高；
   少了 `no-store`，改完配置刷新不生效；**少了 `=404` 会被 `try_files ... /index.html` 兜底成
   200 + HTML**，浏览器拿 HTML 当 JS 执行，配置静默失效、界面一片空白。

   配置的持久化交给三个钩子：`install_callback` / `upgrade_callback` 从
   `$TRIM_PKGETC/rpc-config.js` 还原，`uninstall_callback` 卸载前先备份过去。
   否则每次重装升级都会被包里的空模板覆盖。

4. **1.0.2 起有一段一次性配置迁移 + 启动前置配置**，写在 `index.html` 的 `<head>` 里
   （内联，`<meta charset>` 之后、Angular 之前）。只在第 3 点未启用（`host` 为空）时生效。
   两个动因：

   **(a) 旧版 Aria2 Pro 的残留**。它的 appname 是 `ariang`，和本应用**同端口、同 origin**，
   浏览器把两者的配置存在同一份 `AriaNg.Options` 里。旧版把 `rpcInterface` 写死成
   `aria2/jsonrpc`、语言写成 `zh_CN`、密钥清成空串，这些残留直接表现为
   「界面英文 + 接口填错 + 连不上」。

   **(b) AriaNg 的语言默认值其实无效**。`ariaNgSettingService` 里，无配置时走的是

   ```js
   if (!t) { t = angular.extend({}, o); t.language = y(); /* y() = 浏览器语言 */ }
   ```

   也就是**用浏览器语言覆盖 `ariaNgDefaultOptions.language`**。所以只改那个默认常量没用：
   清一次缓存就退回浏览器语言，英文环境的浏览器整站变英文。而「跑在 Angular 之前」的迁移
   在那一刻还没有配置可改，只能空转。

   所以脚本做两件事：

   - **没有配置时，直接写一份完整的 27 字段默认配置**（含 `language: "zh_Hans"`）。
     AriaNg 于是走「有配置」分支，不再拿浏览器语言覆盖，语言才真正生效。
   - **有配置时，只纠正已知错误值**，跑一次就写 `AriaNg.Migrate` 标记：

   | 字段 | 从 | 到 |
   |---|---|---|
   | `language` | `zh_CN` / `en` / `en-US` 等 | `zh_Hans`（`zh_Hant` 保留） |
   | `rpcInterface` | `aria2/jsonrpc` | `jsonrpc` |
   | `rpcPort` | 等于本页端口（如 6880） | `6800` |
   | `protocol` | 缺失或非法 | 按本页协议补 `http` / `https` |
   | `rpcHost` | **仅当为空** | 当前 hostname（占位，之后不再自动改） |

   **`rpcHost` 不再按访问地址改写**。1.0.1 曾经把它设成 `location.hostname`，结果内网 IP
   和域名分裂成两份配置——从哪个地址打开就用哪个地址。1.0.2 起地址只由用户填一次，
   填什么就是什么。

   **`secret` 永远不动**，用户自定义的反代路径（如 `my/jsonrpc`）也不动。想重跑：
   `localStorage.removeItem("AriaNg.Migrate")` 再刷新。

   `protocol` 那条兜底不是可有可无：`getCurrentRpcUrl()` 是
   `e.protocol + "://" + e.rpcHost + ":" + e.rpcPort + "/" + e.rpcInterface` 直接拼的，
   缺 `protocol` 会拼出 `undefined://host:6800/jsonrpc`，界面上只显示「未连接」，
   从现象完全看不出原因。

5. **「固定 RPC 地址」要填域名，别填内网 IP**。Chrome 的 Private Network Access 会拦截
   「从公网域名打开的页面 → 请求内网地址」，浏览器直接拒绝，aria2 那边连请求都收不到，
   界面只显示「未连接」。实测三种组合：

   | 页面地址 | RPC 地址 | 结果 |
   |---|---|---|
   | 域名 | **域名** | 已连接 |
   | 域名 | 内网 IP | 未连接（被浏览器拦） |
   | 内网 IP | 内网 IP | 已连接 |

   所以想「内网外网用同一份配置」，就把 `rpc-config.js` 里的 `host` 固定成域名，
   家里和外面都开域名访问。

   **验证方法**（CDP 驱动无头 Chrome，比肉眼看可靠；用 `--lang=en-US` 起浏览器，
   才能证明服务端配置确实压过了浏览器语言）：

   | 场景 | 期望 |
   |---|---|
   | `localStorage.clear()` 后重开（英文浏览器） | 中文界面 + 已连接，写入完整配置 |
   | 外网域名 / 内网 IP 两个入口各开一次 | 配置与状态**完全一致**（`AriaNg.Migrate = server`） |
   | 在界面里把地址/端口/密钥改错，刷新 | 被 `rpc-config.js` 拉回，仍「已连接」 |
   | `host` 留空 + 种入旧 ariang 残留（`zh_CN` + `aria2/jsonrpc` + 内网 IP + 缺 `protocol`） | 语言/接口/端口/协议被纠正，**地址与密钥不动** |
   | 迁移后再把语言改成 `en` | 原样保留，迁移不再触发 |

## MeTube 的三个注意点

1. **不要给它加安全加固**。镜像的 entrypoint 以 root 启动，先对 `$DOWNLOAD_DIR` / `$STATE_DIR`
   做 `chown -R $PUID:$PGID`，再用 `gosu` 降权到该 UID/GID 运行 `python3 app/main.py`。
   加 `cap_drop: [ALL]` 会让 chown 失败，加 `no-new-privileges` 会让降权失效——容器能起来但写不进文件。
   同理**没有**设 `mem_limit`：合并大体积视频时内存占用明显抬升，硬上限容易 OOM 失败。
2. **host 网络 + `PORT` 环境变量**。容器内 `PORT=8081` 直接占用宿主机 8081，不做端口映射。
   要换端口得同时改三处：compose 里的 `PORT`、`manifest` 的 `service_port`、`app/ui/config` 的 `port`，
   漏改一处就会出现「应用中心显示已启动但点开是空白」。
3. **下载目录默认落在数据目录下**（`wizard_download_dir`，默认
   `/vol1/1000/docker/metube/downloads`），不是媒体库。
   想让成品直接进媒体库，安装时把它填成媒体库路径即可；
   `TEMP_DIR` 与 `DOWNLOAD_DIR` 保持同一磁盘可避免合并时跨设备拷贝。

## RustDesk Server：安装向导如何影响 compose

RustDesk 是这套向导机制最典型的例子（四个字段全部参与），细节见上面「安装向导」一节。
它的特殊之处在于中继地址和密钥也进了 compose：

```yaml
command: hbbs -r ${wizard_relay_host}:21117
environment:
  - KEY=${wizard_key}
  - ALWAYS_USE_RELAY=${wizard_force_relay}
```

配套的四个坑：

1. **必须声明 `docker-project`**。生命周期脚本以「应用用户」身份运行（没有 docker 权限，
   `/var/run/docker.sock` 是 `root:docker 660`），在 `install_callback` 里 `docker compose up`
   必然失败，表现为安装报 `code 10237: Docker 服务未运行或无权限访问`。
   正确做法是让 fnOS 通过 Docker API 管容器，回调只负责写配置。
2. **`RELAY-SERVERS` 环境变量不生效**。实测 `RELAY-SERVERS` 与 `RELAY_SERVERS` 两种写法，
   日志里都是 `relay-servers=[]`；只有命令行 `hbbs -r <host>:21117` 会被解析。
3. **`-r` 会解析主机名，不可解析的域名被静默忽略**（`-r rd.example.com:21117` → `[]`）。
   所以填中继地址时该地址必须能被本机 DNS 解析，否则等于没填，而日志看起来「正常」。
   留空时拼出来是 `-r :21117`，hbbs 会把它当空值忽略，因此 compose 里不需要做条件判断。
4. **自定义 `KEY` 时不生成 `id_ed25519.pub`**。`KEY=-` / `_` 才由 hbbs 首次启动生成密钥对；
   填了自定义 KEY 后，信息页的 `/key` 路由会返回纯文本 404，页面改从 `/meta.txt` 里的配置值显示。

信息页是包内自带的静态页（nginx:alpine 托管，端口 21120），
展示 ID 服务器 / 中继 / Key / 端口清单，`nginx.conf` 只开放指向**公钥**的那一条路由，
私钥虽在同一挂载目录下但没有任何路由可读。安装时写入的配置存在两处：
`$PKGETC/info.txt`（持久，供排查）与 `$APPDEST/docker/info/meta.txt`（供页面 fetch，
因为配置目录的 ACL 让 nginx worker 读不到）。

## Motrix 的六个注意点

1. **登录密码必须在向导里设，否则得 SSH 上去翻文件**。Motrix 服务器版首次打开会要求输入
   operator token；不设 `MOTRIX_OPERATOR_TOKEN` 时程序自己生成一个随机值写到
   `/data/operator-token`（0600），而 fpk 的生命周期钩子以应用用户身份运行、读不到它，
   没法替你显示出来。所以向导里把它设成必填，装完直接用这个密码解锁。
   安装时还会在 `$PKGETC/info.txt` 留一份，忘记密码可以到 NAS 上查
   （`/vol1/@appconf/motrix/info.txt`，需 root 或管理员权限）。
   **改密码 = 重新安装**（数据目录不删就不会丢）——应用用户没有 docker 权限，
   无法在回调里重建容器，所以没做 `wizard/config` 配置页。
2. **只能以 root 运行**。官方推荐 `user: 1000:1000`，但那要求 `/data` 与 `/downloads`
   的属主是 1000；本仓库的安装钩子对 `/vol1/1000/docker` 没有写权限，无法替你 `chown`，
   而 Docker 创建缺失目录时是 `root:root`。权衡后选 root（与 emby / reclip 一致）。
   镜像自带的 `read_only`、`no-new-privileges`、tmpfs `/tmp` 仍然保留。
3. **`MOTRIX_DEFAULT_SAVE_DIR` 要填容器内路径**。这个值不是宿主机路径，
   用户选的下载目录靠 `volumes` 映射到 `/downloads`。填成宿主机路径会让启动直接失败：
   `fatal AppError: Save directory cannot be created: /vol1/... (ENOENT: mkdir '/vol1')`
   —— 容器里没有 `/vol1`。`MOTRIX_ALLOWED_SAVE_DIRS` 同理，且必须包含前者。
4. **BT 端口 6881 是懒绑定的**。aria2 只在第一个 BT/磁力任务开始时才打开 6881 的
   TCP/UDP 监听，空闲时 `ss` 看不到它，这是正常现象。路由器的端口映射照做即可
   （映射是静态的，不依赖进程当前是否在监听）。
5. **官方镜像不含 FFmpeg**。依赖它的插件（转码、音轨提取之类）用不了；
   要支持就得基于官方镜像派生一层装 `ffmpeg` 并设 `MOTRIX_FFMPEG_PATH`，
   那需要自己维护镜像，不在本仓库范围内。
6. **界面默认中文是打补丁实现的，升级镜像后可能失效**。上游把前端初始语言
   写死成 `en-US`（`app-settings-<hash>.js` 里的 `b=\`en-US\``），而设置里的
   `app.language` 要登录后才能读到，所以**解锁页永远是英文**；选「跟随系统」
   （`system`）时也会落到这个常量。包里带了一份只改这一个常量的 chunk，
   通过 `volumes` 挂到 `/app/dist/renderer-web/assets/app-settings-D3X0vjxd.js`
   上，`MOTRIX_HOST_LANGUAGE=zh-CN` 负责服务端侧的语言。
   **镜像更新后 chunk 的 hash 会变**，挂载点就变成没人引用的旧文件——
   表现为界面退回英文，功能不受影响（失败安全）。重新打补丁的方法见
   `apps/motrix/app/docker/patch/README.md`。

与 AriaNg 的关系：两者都是 aria2 前端，但**不冲突**。Motrix 用容器内的 aria2
（`16800`，只监听 loopback），和独立部署的 `aria2-pro`（`6800`）是两个互不相干的引擎。
Motrix 额外提供原生 BT/磁力、插件体系、tracker 订阅，以及 `@motrix/cli` / AI agent 的
device-code 远程配对。

## MoviePilot 的七个注意点

1. **前后端是两个端口**。镜像里 FastAPI 后端监听 `3001`、nginx 前端监听 `3000`，
   对外只映射 `3000`。compose 里把 `NGINX_PORT` / `PORT` 都显式写出来了，
   避免以后镜像改默认值时静默错位。健康检查走的是**后端 3001**
   （`/api/v1/system/global?token=moviepilot`），所以「前端 200」不等于「后端就绪」，
   刚启动那几十秒 API 会返回 502。
2. **首次启动要下 206MB 浏览器内核，解压后 717MB**。这是 CloakBrowser（站点认证用的
   隐身 Chromium），默认落在容器内的 `$HOME/.cloakbrowser`，**容器一重建就没了**。
   所以单独把 `${wizard_data_dir}/cloakbrowser` 挂到 `/moviepilot/.cloakbrowser`：
   实测首次启动要几分钟，挂上之后重建容器 **19–25 秒**就绪，`Download progress` 一行都不会出现。
   代价是数据目录要多留 700MB。
3. **`MOVIEPILOT_AUTO_UPDATE=false`**。默认值是 `release`，容器每次启动都会去 GitHub
   拉新版覆盖自己，fpk 的版本号就失去意义了。关掉启动自更新后，界面里「重启并更新」
   仍然可用——它走的是 `/config/temp/moviepilot.pending_update` 一次性标记，不受这个变量影响。
4. **管理员账号靠环境变量在首次启动时建好**。`SUPERUSER` / `SUPERUSER_PASSWORD`
   由入口脚本写进 `app.env` 并入库，装完直接登录，不用走 Web 初始化向导。
   密码只在安装时出现一次，所以写进了 `/vol1/@appconf/moviepilot/info.txt`。
   注意 `SUPERUSER` 只是 MoviePilot 自己的用户名，**不会**同步到 Emby / Jellyfin；
   但如果同时用 Jellyfin，建议填成和 Jellyfin 管理员同名，否则联动功能会提示找不到账号。
5. **下载目录必须和下载器里配的路径指向同一个宿主机目录**。两边路径不一致时，
   硬链接、秒传、做种校验全部失效，整理入库会退化成跨盘复制（很慢且占双倍空间）。
6. **没有挂 `docker.sock`**。挂上之后 MoviePilot 会额外起一个 nginx docker 代理，
   等于把宿主机 root 权限交给容器，默认不开。确实需要（个别插件要管容器）时，
   自己在 compose 里加 `- /var/run/docker.sock:/var/run/docker.sock:ro`。
7. **镜像只有 amd64**，ARM 机器（如某些 arm64 NAS）装不了。另外 `/dev/shm` 默认只有 64MB，
   如果站点认证用的浏览器偶发崩溃，可以给 compose 加 `shm_size: 1gb` 再试。

另外两点实现细节：入口脚本自带 `tini`，compose 里**不能**再加 `init: true`（会变成双份 init）；
`PUID`/`PGID` 默认 0，想改成普通用户直接改这两个值即可，入口脚本会自动 chown `/config`。

## 关于第三方代码

`apps/aria2ng/app/docker/html/` 是 [AriaNg](https://github.com/mayswind/AriaNg) v1.2.3
官方 release 包的原样内联（MIT License，原始许可证保留在 `html/LICENSE`），仅为离线自包含。
改动有三处，都记在 `README` 的「AriaNg 的五个注意点」里：

1. `js/aria-ng-*.min.js` 里 `ariaNgDefaultOptions.language` 由 `"en"` 改为 `"zh_Hans"`
   （默认语言，界面可改），其余字节与上游完全一致；
2. `index.html` 的 `<head>` 最前面加了一段启动前置脚本（服务端配置覆盖 + 一次性配置迁移），
   并给 css/js 引用加了 `?v=<版本>` 查询串（绕开浏览器里旧 `ariang` 留下的同名缓存文件）；
3. 新增 `rpc-config.js`——**空的配置模板**（`host: ""`，不含任何地址与密钥），
   由使用者自己填。它不改变 AriaNg 上游代码的任何行为。

`apps/motrix/app/docker/patch/app-settings-<hash>.js` 是 Motrix 官方镜像里
`/app/dist/renderer-web/assets/` 下的同名前端 chunk，**仅替换了一个常量**
（默认语言 `en-US` → `zh-CN`，两者等长，文件字节数不变，其余逐字节一致），
用于让登录前的解锁页也显示中文。Motrix 以 MIT 协议发布，该文件不单独再分发，
仅作为官方镜像的运行时覆盖层使用；镜像更新后此文件即失效，需按同目录 README 重做。

其余各应用仅为容器镜像的封装配置，不含镜像内代码。

## 脱敏说明

本仓库由实际部署环境整理而来，发布前已做以下处理：

- `aria2ng` 里**没有任何凭据**：它是官方原版 AriaNg 静态站，RPC 地址、端口、密钥全部由用户
  自己填——可以填在浏览器界面里，也可以填在 `html/rpc-config.js`（仓库里这份是空模板，
  `host: ""` 即不启用），包里没有预设值，也不含反向代理；
- 主机绝对路径不再写死在 compose 里，改为安装向导字段（`${wizard_data_dir}` 等），
  默认值与 fnOS 默认布局一致，因此行为不变但不再绑定具体机器；
- 向导字段的 `initValue` 保留 fnOS 标准路径作为默认值——向导只接受字面量、
  无法引用环境变量，这是脱敏规则里唯一的例外，安装时可随时改成自己的路径；
- 剔除构建产物（`*.fpk`、`app.tgz`）与个人目录结构信息。

## 免责声明

本项目仅提供打包配置，不包含也不分发任何第三方应用的源码或二进制。
各容器镜像的使用须遵守其各自许可；封装配置按原样提供，使用风险自负。
