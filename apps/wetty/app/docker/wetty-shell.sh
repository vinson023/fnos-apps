#!/bin/sh
# WeTTY 的入口脚本。
#
# WeTTY 自带的 ssh 只服务于默认的 login 流程：它先 ssh 上去、再在远端跑一次 login，
# 而飞牛上的 login 会把所有账号都判成 Login incorrect，那条路走不通。
# WeTTY 的 --command 又是在容器内本地执行的，不经过它的 ssh。
# 所以这里自己 exec ssh：认证交给 ssh 自己，密码在浏览器终端里输入。
#
# 容器用 host 网络，127.0.0.1 就是飞牛本身；要连别的机器改 WETTY_SSH_TARGET 即可。

TARGET="${WETTY_SSH_TARGET:-root@127.0.0.1}"

exec ssh \
    -o StrictHostKeyChecking=no \
    -o UserKnownHostsFile=/dev/null \
    -o LogLevel=ERROR \
    -o PreferredAuthentications=password \
    -o PubkeyAuthentication=no \
    -o ServerAliveInterval=30 \
    -o ServerAliveCountMax=3 \
    "$TARGET"
