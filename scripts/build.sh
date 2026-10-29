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

    # 从 Windows/压缩包同步过来的源码常丢失可执行位，缺了会导致安装后脚本无法执行
    chmod +x "$src"/cmd/* 2>/dev/null || true

    # wetty 的入口脚本会被 :ro 挂进容器并由 env 执行，包里必须是 755，
    # 否则终端里只剩一行 "env: can't execute ..."。fnpack 保留源文件权限，所以这里先修好
    if [ -f "$src/app/docker/wetty-shell.sh" ]; then
        chmod 755 "$src/app/docker/wetty-shell.sh"
    fi

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
