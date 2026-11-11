#!/bin/bash
# 把已安装的 fnOS 应用图标地址从「跟随桌面协议」改成固定 http，
# 解决开启 HTTPS 后点图标打不开（https://host:端口 打到只讲 HTTP 的容器上）。
#
# 用法（NAS 上以 root 执行）：
#   sh fix-https.sh              # 处理全部应用
#   sh fix-https.sh omnibox      # 只处理一个
#
# 做三件事：
#   1. app_service.url / default_url 前面补 http（原本是 ://${host}:端口/）
#   2. /vol1/@appcenter/<app>/ui/config 的 protocol 改成 http（重装后不再退回）
#   3. 重启 trim_app_center（服务端缓存了服务列表，不重启不生效）
set -euo pipefail

APPS_ROOT="/vol1/@appcenter"
PSQL="su -s /bin/sh postgres -c"

say() { printf '%s\n' "$*"; }

q() { $PSQL "psql -w -d appcenter -A -t -c \"$1\"" 2>/dev/null; }

run_sql() {
  printf '%s\n' "$1" > /tmp/fix_https.sql
  $PSQL "psql -w -d appcenter -A -F ' | ' -f /tmp/fix_https.sql" 2>/dev/null
}

if [ "$#" -gt 0 ]; then
  APP="$1"
  SEL="service_name like '${APP}.%'"
else
  SEL="service_name like '%.main' or service_name like '%.Application'"
fi

say "== 1. 数据库里补 http =="
run_sql "select service_name, url, default_url from app_service where ($SEL) order by service_name;"

run_sql "update app_service set
           url = case when url like '://%' then 'http' || url else url end,
           default_url = case when default_url like '://%' then 'http' || default_url else default_url end
         where ($SEL);"

say ""
say "== 2. 已装 ui/config 的 protocol 改成 http =="
for cfg in "$APPS_ROOT"/*/ui/config; do
  [ -f "$cfg" ] || continue
  app="$(basename "$(dirname "$(dirname "$cfg")")")"
  if [ "$#" -gt 0 ] && [ "$app" != "$APP" ]; then continue; fi
  if grep -q '"protocol": *"[^"]*"' "$cfg"; then
    before="$(grep -o '"protocol"[^,]*' "$cfg" | head -1)"
    sed -i 's/"protocol": *"[^"]*"/"protocol": "http"/' "$cfg"
    after="$(grep -o '"protocol"[^,]*' "$cfg" | head -1)"
    say "  $app: $before -> $after"
  fi
done

say ""
say "== 3. 重启应用中心（让服务列表缓存失效）=="
systemctl restart trim_app_center.service
sleep 5
say "  trim_app_center: $(systemctl is-active trim_app_center.service)"

say ""
say "== 结果 =="
run_sql "select service_name, url, default_url from app_service where ($SEL) order by service_name;"
say ""
say "完成。刷新桌面（或退出重登）后图标就正常了。"
