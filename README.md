# fnos-apps

把常用的 Docker 应用封装成 **fnOS（飞牛 OS）原生应用包（`.fpk`）** 的构建源码集合。

封装后这些容器不再是「Docker 应用」里的一个条目，而是变成应用中心里的正式应用：有独立图标、
能出现在 fnOS 桌面、点击即打开（`type` 决定是桌面内 iframe 窗口还是新浏览器页签）、
随应用中心统一启停，并且可以通过 `appcenter-cli` 脚本化管理。

## 应用列表

| 应用 | appname | 端口 | 容器镜像 | 桌面打开方式 |
|---|---|---|---|---|
| Aria2 Pro | `ariang` | 6880 | `nginx:alpine`（托管 AriaNg 静态站） | iframe 窗口 1280×860 |
| Emby | `emby` | 8096 | `amilys/embyserver:latest` | 新页签 |
| Music-DL | `music-dl` | 8099 | `guohuiyuan/go-music-dl:latest` | 新页签 |
| ReClip | `video-download-reclip` | 8899 | `reclipd/reclip:latest` | 新页签 |
| MeTube | `metube` | 8081 | `ghcr.io/alexta69/metube:latest` | 新页签 |

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
│       └── ...             # 应用自有静态资源（如 ariang 的 html/ 与 nginx.conf）
├── cmd/                    # 生命周期钩子，main 需处理 start/stop/status
├── config/
│   ├── resource            # 必须含 docker-project 段，否则被识别为普通应用
│   └── privilege           # 运行身份
└── wizard/                 # 安装向导（可选）
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

## 可配置项

数据目录默认取 fnOS 标准路径，可用环境变量覆盖：

| 变量 | 默认值 | 作用 |
|---|---|---|
| `FNOS_DATA_DIR` | `/vol1/1000/docker` | 各应用数据目录的父目录 |
| `MEDIA_DIR` | `/vol1/1000/video` | Emby 的媒体库目录 |
| `DOWNLOAD_DIR` | `/vol1/1000/Download` | Music-DL 的下载落盘目录 |

Music-DL 的两个挂载点以镜像内的实际路径为准，不要随意改：

| 宿主机 | 容器内 | 用途 |
|---|---|---|
| `$DOWNLOAD_DIR` | `/home/appuser/data/downloads` | 下载的音乐文件 |
| `$FNOS_DATA_DIR/music-dl` | `/home/appuser/data` | 配置、缓存、日志 |

镜像里**没有** `/app/data` 这个路径，挂到那里数据不会被读到。

Aria2 Pro 的 RPC 密钥不再硬编码，二选一：

- **推荐**：首次打开 AriaNg 后到 `AriaNg 设置 → RPC 密钥` 填一次，配置会存在浏览器 localStorage；
- 或在 `apps/ariang/app/docker/html/index.html` 里、注入脚本之前加一行
  `window.ARIA2_SECRET='你的密钥';`，随包固化（注意这是明文提交，仅适合自建自用）。

## Aria2 Pro 的两个特殊处理

1. **反代 RPC**：`app/docker/nginx.conf` 把同源的 `/aria2/jsonrpc` 反代到 `127.0.0.1:6800`。
   这样内网 IP、外网域名、IPv4/IPv6 都共用同一个相对地址，不需要在 AriaNg 里写死主机。
2. **语言与 RPC 自愈**：AriaNg 的偏好存在 localStorage 里，而 localStorage 按 origin 隔离——
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
3. **下载目录默认落在数据目录下**（`$FNOS_DATA_DIR/metube/downloads`），不是媒体库。
   想让成品直接进媒体库，把这条挂载改到 `$MEDIA_DIR` 之类的位置即可；
   `TEMP_DIR` 与 `DOWNLOAD_DIR` 保持同一磁盘可避免合并时跨设备拷贝。

## 关于第三方代码

`apps/ariang/app/docker/html/` 是 [AriaNg](https://github.com/mayswind/AriaNg) 的发行版
（MIT License，原始许可证保留在 `html/LICENSE`），仅为离线自包含而内联进包。
其余各应用仅为容器镜像的封装配置，不含镜像内代码。

## 脱敏说明

本仓库由实际部署环境整理而来，发布前已做以下处理：

- 移除硬编码的 aria2 RPC 密钥（原为固定字符串），改为空值 + `ARIA2_SECRET` 可选项；
- 主机绝对路径（`/vol1/1000/...`）改为 `${FNOS_DATA_DIR:-...}` / `${MEDIA_DIR:-...}` 形式，
  默认值与 fnOS 默认布局一致，因此行为不变但不再绑定具体机器；
- 剔除构建产物（`*.fpk`、`app.tgz`）与个人目录结构信息。

## 免责声明

本项目仅提供打包配置，不包含也不分发任何第三方应用的源码或二进制。
各容器镜像的使用须遵守其各自许可；封装配置按原样提供，使用风险自负。
