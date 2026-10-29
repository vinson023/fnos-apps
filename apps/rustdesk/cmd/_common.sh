#!/bin/bash
# RustDesk 应用公共函数库
#
# 重要背景（都是在本机实测出来的，改之前先看）：
# 1. fnOS 的生命周期脚本以「应用用户」身份运行，不是 root。
#    /var/run/docker.sock 是 root:docker 660，应用用户连不上 Docker，
#    所以脚本里不能直接 docker compose up —— 容器必须交给 fnOS 自己管理，
#    也就是在 config/resource 里声明 docker-project。
# 2. fnOS 会在 install_callback 之前就把容器建好，所以在回调里改 compose 无效。
#    用户的安装选项能生效，靠的是 fnOS 对 compose 文件里的 ${wizard_xxx} 做变量替换。
# 3. 生命周期脚本执行时不带 PATH，必须自己补，否则 date/ss 这些命令都找不到。

export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:${PATH}"

CONTAINER_HBBS="rustdesk-hbbs"
INFO_PORT=21120

# 读取向导值。
# 官方文档：字段名即环境变量名（wizard_data_dir → $wizard_data_dir）。
# 同时兼容部分应用使用的 TRIM_WIZARD_ 前缀写法。
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

log() {
    mkdir -p "${TRIM_PKGVAR}" 2>/dev/null
    echo "$(date '+%F %T') [rustdesk] $*" >> "${TRIM_PKGVAR}/rustdesk.log" 2>/dev/null
}
