#!/bin/bash
# 批量构建 apps/ 下所有 fnOS 应用包，产物统一输出到 dist/
# 用法: ./scripts/build.sh [appname ...]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST="$ROOT/dist"

if ! command -v fnpack >/dev/null 2>&1; then
    echo "错误: 未找到 fnpack，请先安装 fnOS 官方打包工具" >&2
    exit 1
fi

mkdir -p "$DIST"

if [ "$#" -gt 0 ]; then
    APPS=("$@")
else
    APPS=()
    for d in "$ROOT"/apps/*/; do
        APPS+=("$(basename "$d")")
    done
fi

for app in "${APPS[@]}"; do
    src="$ROOT/apps/$app"
    if [ ! -f "$src/manifest" ]; then
        echo "跳过 $app: 缺少 manifest"
        continue
    fi

    version="$(grep -m1 '^version=' "$src/manifest" | cut -d= -f2)"
    echo "==> 构建 $app (v$version)"

    # fnpack 把产物写到当前工作目录，所以先切到 dist
    ( cd "$DIST" && fnpack build -d "$src" )

    produced="$DIST/$app.fpk"
    if [ -f "$produced" ]; then
        mv -f "$produced" "$DIST/$app-$version.fpk"
        echo "    -> dist/$app-$version.fpk"
    else
        echo "    警告: 未生成预期的 $app.fpk" >&2
    fi
done

echo "完成，产物位于 $DIST"
