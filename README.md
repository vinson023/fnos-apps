# fnos-apps

把常用的 Docker 应用封装成 **fnOS（飞牛 OS）原生应用包（`.fpk`）** 的构建源码集合。

封装后这些容器不再是「Docker 应用」里的一个条目，而是变成应用中心里的正式应用：有独立图标、
能出现在 fnOS 桌面、点击即打开（`type` 决定是桌面内 iframe 窗口还是新浏览器页签）、
随应用中心统一启停，并且可以通过 `appcenter-cli` 脚本化管理。

## 应用列表

| 应用 | appname | 端口 | 容器镜像 | 桌面打开方式 | 安装向导可配置 |
|---|---|---|---|---|---|
| Aria2 Pro | `ariang` | 6880 | `nginx:alpine`（托管 AriaNg 静态站） | iframe 窗口 1280×860 | aria2 RPC 地址 |
| Emby | `emby` | 8096 | `amilys/embyserver:latest` | 新页签 | 配置目录、媒体库目录 |
| Music-DL | `music-dl` | 8099 | `guohuiyuan/go-music-dl:latest` | 新页签 | 下载目录、数据目录 |
| ReClip | `video-download-reclip` | 8899 | `reclipd/reclip:latest` | 新页签 | 数据目录 |
| MeTube | `metube` | 8081 | `ghcr.io/alexta69/metube:latest` | 新页签 | 配置目录、下载目录 |
| RustDesk Server | `rustdesk` | 21115–21120 | `rustdesk/rustdesk-server:latest` | iframe 窗口 900×760 | 数据目录、中继地址、密钥、强制中继 |
| Motrix | `motrix` | 8080、16801、6881 | `motrixapp/motrix-server:latest` | iframe 窗口 1280×860 | 数据目录、下载目录、登录密码、对外地址 |

**七个应用都带安装向导**：装的时候就能选数据目录、媒体库、下载目录这些路径，选完 compose 自动按选择生效，不用装完再改文件。机制见下面「安装向导」一节。

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
│       └── ...             # 应用自有静态资源（如 ariang 的 html/ 与 default.conf.template）
├── cmd/                    # 生命周期钩子，main 需处理 start/stop/status
├── config/
│   ├── resource            # 必须含 docker-project 段，否则被识别为普通应用
│   └── privilege           # 运行身份
└── wizard/
    └── install             # 安装向导（六个应用都有，字段值经 ${wizard_xxx} 进 compose）
```

## 构建

需要 fnOS 官方的 `fnpack`：

```bash
fnpack build -d apps/ariang
# 产物落在当前工作目录：ariang.fpk
```

或一次构建全部：

```bash
./scripts/build.sh          # 产物统一输出到 dist/
```

## 安装与升级

`appcenter-cli` 使用**位置参数**，没有 `-a` 这种短选项：

```bash
appcenter-cli install-fpk ariang.fpk
appcenter-cli start ariang
appcenter-cli status ariang
```

**升级必须先卸载**：`install-fpk` 对同名已装应用不会重新解压 `/vol1/@appcenter/<app>/`，
直接覆盖会导致容器仍从旧 compose 启动。

```bash
docker rm -f ariang
appcenter-cli uninstall ariang
appcenter-cli install-fpk ariang.fpk
appcenter-cli start ariang
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

路径都在安装向导里选，默认值与 fnOS 标准布局一致：

| 应用 | 向导字段 | 默认值 | 容器内 |
|---|---|---|---|
| `ariang` | `wizard_aria2_rpc` | `127.0.0.1:6800` | 反代目标，非挂载 |
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

Music-DL 的两个挂载点以镜像内的实际路径为准，不要随意改：

| 宿主机 | 容器内 | 用途 |
|---|---|---|
| `wizard_download_dir` | `/home/appuser/data/downloads` | 下载的音乐文件 |
| `wizard_data_dir` | `/home/appuser/data` | 配置、缓存、日志 |

镜像里**没有** `/app/data` 这个路径，挂到那里数据不会被读到。

## 桌面打开方式（iframe / 新页签）

由 `app/ui/config` 里 `.url.<id>.type` 决定：

- `"iframe"` → 在 fnOS 桌面内开窗口，可用 `width` / `height` 指定尺寸（Aria2 Pro 用 1280×860）；
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

## Aria2 Pro 的三个特殊处理

1. **反代 RPC**：`app/docker/default.conf.template` 把同源的 `/aria2/jsonrpc` 反代到
   安装向导里填的 aria2 地址（默认 `127.0.0.1:6800`）。
   这样内网 IP、外网域名、IPv4/IPv6 都共用同一个相对地址，不需要在 AriaNg 里写死主机。

   模板里的 `${ARIA2_RPC}` 由容器启动时 nginx 镜像自带的 envsubst 渲染成实际值。
   注意必须同时设 `NGINX_ENVSUBST_FILTER=ARIA2_RPC` 白名单：不加的话，模板里的
   `$remote_addr` / `$uri` / `$scheme` 这些 nginx 内置变量会被一并替换成空值，配置直接失效。
2. **RPC 密钥不随包分发**。首次打开 AriaNg 后到 `AriaNg 设置 → RPC 密钥` 填一次，
   配置存在浏览器 localStorage（按 origin 隔离，换域名要重填）。
   也可以在自己的副本里改 `apps/ariang/app/docker/html/index.html`、在注入脚本之前加一行
   `window.ARIA2_SECRET='你的密钥';` 随包固化——但那是明文提交，不适合放进公开仓库。
3. **语言与 RPC 自愈**：AriaNg 的偏好存在 localStorage 里，而 localStorage 按 origin 隔离——
   换一个域名访问就是一份全新的空配置，会回落到英文且 RPC 地址为空（表现为「未连接」）。
   因此对 `aria-ng-*.min.js` 打了三处函数级补丁（标记 `ARIANG_LOCK_ZH`）：
   - 语言固定为中文，不再跟随浏览器语言；
   - 已有配置一律强制改写 language；
   - `T()` 从 `location` 推导 rpcHost/rpcPort/protocol/interface，避免空值卡死。

   补丁在压缩产物上直接改，改完可用 `node --check` 验证语法。

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

与 Aria2 Pro 的关系：两者都是 aria2 前端，但**不冲突**。Motrix 用容器内的 aria2
（`16800`，只监听 loopback），和独立部署的 `aria2-pro`（`6800`）是两个互不相干的引擎。
Motrix 额外提供原生 BT/磁力、插件体系、tracker 订阅，以及 `@motrix/cli` / AI agent 的
device-code 远程配对。

## 关于第三方代码

`apps/ariang/app/docker/html/` 是 [AriaNg](https://github.com/mayswind/AriaNg) 的发行版
（MIT License，原始许可证保留在 `html/LICENSE`），仅为离线自包含而内联进包。

`apps/motrix/app/docker/patch/app-settings-<hash>.js` 是 Motrix 官方镜像里
`/app/dist/renderer-web/assets/` 下的同名前端 chunk，**仅替换了一个常量**
（默认语言 `en-US` → `zh-CN`，两者等长，文件字节数不变，其余逐字节一致），
用于让登录前的解锁页也显示中文。Motrix 以 MIT 协议发布，该文件不单独再分发，
仅作为官方镜像的运行时覆盖层使用；镜像更新后此文件即失效，需按同目录 README 重做。

其余各应用仅为容器镜像的封装配置，不含镜像内代码。

## 脱敏说明

本仓库由实际部署环境整理而来，发布前已做以下处理：

- 移除硬编码的 aria2 RPC 密钥（原为固定字符串），改为空值 + `ARIA2_SECRET` 可选项；
- 主机绝对路径不再写死在 compose 里，改为安装向导字段（`${wizard_data_dir}` 等），
  默认值与 fnOS 默认布局一致，因此行为不变但不再绑定具体机器；
- 向导字段的 `initValue` 保留 fnOS 标准路径作为默认值——向导只接受字面量、
  无法引用环境变量，这是脱敏规则里唯一的例外，安装时可随时改成自己的路径；
- 剔除构建产物（`*.fpk`、`app.tgz`）与个人目录结构信息。

## 免责声明

本项目仅提供打包配置，不包含也不分发任何第三方应用的源码或二进制。
各容器镜像的使用须遵守其各自许可；封装配置按原样提供，使用风险自负。
