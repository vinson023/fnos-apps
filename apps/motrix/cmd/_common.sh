#!/bin/bash
# 公共定义与工具函数，被各生命周期脚本 source。
# fnOS 执行钩子时的 PATH 可能不含 /usr/sbin（ss 在 /usr/sbin 下），这里补齐
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:${PATH}"

WEB_PORT=8080
MDXP_PORT=16801
BT_PORT=6881
CONTAINER_NAME="motrix"

log() {
    echo "[motrix] $*"
}

# 读取安装向导里填的值。
# fnOS 把向导字段注入为环境变量，字段名就是变量名（不带 TRIM_ 前缀）；
# 个别版本会加 TRIM_WIZARD_ 前缀，这里两种都兼容，都没有则用默认值。
wiz() {
    local name="$1" def="$2" val tmp
    val="${!name}"
    if [ -z "$val" ]; then
        tmp="TRIM_WIZARD_${name}"
        val="${!tmp}"
    fi
    if [ -z "$val" ]; then
        val="$def"
    fi
    printf '%s' "$val"
}

# 已监听的端口列表（TCP + UDP），每行一个
listening_ports() {
    ss -tuln 2>/dev/null | awk 'NR>1 {print $5}' | sed 's/.*://' | sort -u
}
