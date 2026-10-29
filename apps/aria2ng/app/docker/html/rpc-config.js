/* aria2ng 服务端配置 —— 唯一来源
 *
 * 这里填的值会在「每次打开页面」时写进浏览器，所以不管你是用电脑还是手机、
 * 用内网 IP 还是外网域名打开，看到的都是同一份设置、同一个连接状态。
 * 想改设置就改这个文件，保存后刷新页面即可，不用每台设备各填一遍。
 *
 * 文件位置（fnOS 上）：
 *     /vol1/@appcenter/aria2ng/docker/html/rpc-config.js
 * 重装/升级应用时，这个文件会被自动备份到 /vol1/@appconf/aria2ng/ 再还原回来。
 *
 * host 留空 = 不启用服务端配置，退回「在界面里手动填」的老方式。
 * secret 写明文，页面会自己转成 AriaNg 需要的格式。
 */
window.ARIA2NG_RPC = {
    host: "",           // aria2 的地址，例如 nas.example.com（不要带 http:// 和端口）
    port: "6800",       // aria2 的 RPC 端口，默认 6800
    interface: "jsonrpc",
    protocol: "http",   // http 或 https
    secret: ""          // aria2 配置里的 rpc-secret，没改过通常是 123456
};
