# fnos-apps

把常用的 Docker 应用封装成 **fnOS（飞牛 OS）原生应用包（`.fpk`）** 的构建源码集合。

封装后这些容器不再是「Docker 应用」里的一个条目，而是变成应用中心里的正式应用：有独立图标、
能出现在 fnOS 桌面、点击在桌面窗口内直接打开（iframe，不跳浏览器页签）、随应用中心统一启停，
并且可以通过 `appcenter-cli` 脚本化管理。

## 应用列表

| 应用 | appname | 端口 | 容器镜像 | 桌面打开方式 |
|---|---|---|---|---|
| Aria2 Pro | `ariang` | 6880 | `nginx:alpine`（托管 AriaNg 静态站） | iframe 窗口 1280×860 |
| Emby | `emby` | 8096 | `amilys/embyserver:latest` | iframe 窗口 |
| Music-DL | `music-dl` | 8099 | `guohuiyuan/go-music-dl:latest` | 新页签 |
| ReClip | `video-download-reclip` | 8899 | `heizicao/reclip:latest` | 新页签 |

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

## 可配置项

数据目录默认取 fnOS 标准路径，可用环境变量覆盖：

| 变量 | 默认值 | 作用 |
|---|---|---|
| `FNOS_DATA_DIR` | `/vol1/1000/docker` | 各应用数据目录的父目录 |
| `MEDIA_DIR` | `/vol1/1000/video` | Emby 的媒体库目录 |

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
