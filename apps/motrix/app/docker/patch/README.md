# 界面默认中文补丁

## 为什么需要

Motrix 2.0 的 Web 前端把「初始语言」写死成了 `en-US`，位置在
`/app/dist/renderer-web/assets/app-settings-<hash>.js`：

```js
var y = _.map(({code:e}) => e),   // 支持的语言列表（含 zh-CN）
    b = `en-US`,                  // ← 默认语言常量
    x = b;
```

这个常量同时被用作 i18next 的 `lng`（初始语言）和 `fallbackLng`（兜底语言）。
后果有两个：

1. **解锁页永远是英文**。设置里的 `app.language` 要等登录后才能读到，
   登录前走 `catch { qc(le) }`，`le` 就是这个 `en-US` 常量。
2. 设置里选「跟随系统」（`app.language = "system"`）时，前端解析
   `system` → 规范化失败 → 落到 `b`，也就是英文。

镜像里没有任何环境变量能改这个常量（`MOTRIX_HOST_LANGUAGE` 只影响服务端，
不影响前端首屏）。

## 补丁做了什么

只替换一个常量：

```
- b=`en-US`
+ b=`zh-CN`
```

`en-US` 与 `zh-CN` 等长，所以打补丁后**文件字节数不变**（13398 字节），
其余内容逐字节一致。zh-CN 的翻译本身就内联在这个文件里（`zc` 常量），
不需要额外加载语言包。

## 怎么复现（镜像升级后需要重做）

```bash
docker cp motrix:/app/dist/renderer-web/assets/app-settings-XXXX.js ./app-settings.js
# 确认 b=`en-US` 只出现 1 次
grep -c 'b=`en-US`' app-settings.js
# 替换并改名成镜像里的真实文件名
sed 's/b=`en-US`/b=`zh-CN`/' app-settings.js > app-settings-XXXX.js
```

改完把文件名写进 `docker-compose.yaml` 的挂载行（目标路径必须与
`/app/dist/renderer-web/assets/` 下的真实文件名完全一致）。

## 升级镜像时的风险

**低，且是失败安全的。** 上游重新打包后 chunk 的 hash 会变（`app-settings-XXXX.js`），
这时挂载会在容器里创建一个没人引用的旧文件名，页面照旧加载新 chunk ——
**表现为界面退回英文，但功能完全正常，不会白屏、不会报错**。

唯一的注意事项：补丁文件必须存在于包内。如果源文件缺失，Docker 会把
挂载点建成**目录**，`assets/app-settings-*.js` 变成目录后前端会直接崩。
`cmd/install_callback` 会在安装日志里检查并记录这个文件是否就位。

## 验证方法

```bash
# 未登录时抓 DOM，html 的 lang 属性与解锁页文案应为中文
chrome --headless=new --virtual-time-budget=15000 --dump-dom http://<nas>:8088/ \
  | grep -o '解锁[^<]*'
```
