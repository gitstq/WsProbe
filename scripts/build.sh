#!/usr/bin/env bash
#
# WsProbe 跨平台打包脚本(可选)
#
# WsProbe 本身是纯 Python 工具库,pip 安装即可使用;
# 本脚本用于需要"无依赖单文件可执行程序"的场景,基于 PyInstaller。
#
# 用法:
#   ./scripts/build.sh              # 打包当前平台
#   ./scripts/build.sh clean        # 清理构建产物
#
# 注意:PyInstaller 无法交叉编译,生成 Windows/macOS 产物需在对应系统上执行
# (或使用对应系统的 CI runner,见 .github/workflows/release.yml)。
#
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

APP_NAME="wsprobe"
DIST_DIR="dist"

clean() {
    echo "==> 清理构建产物"
    rm -rf "$DIST_DIR" build ./*.spec
    echo "完成"
}

build() {
    echo "==> 检查 PyInstaller"
    if ! command -v pyinstaller >/dev/null 2>&1; then
        echo "未找到 pyinstaller,请先安装: pip install pyinstaller"
        exit 1
    fi

    echo "==> 开始打包(当前平台: $(uname -s) / $(uname -m))"
    pyinstaller \
        --onefile \
        --name "$APP_NAME" \
        --clean \
        --noconfirm \
        --distpath "$DIST_DIR" \
        --specpath "$DIST_DIR" \
        wsprobe/__main__.py

    echo "==> 产物:"
    ls -lh "$DIST_DIR/$APP_NAME"* 2>/dev/null || true

    if command -v sha256sum >/dev/null 2>&1 && [ -f "$DIST_DIR/$APP_NAME" ]; then
        echo "==> SHA256:"
        sha256sum "$DIST_DIR/$APP_NAME" | tee "$DIST_DIR/$APP_NAME.sha256"
    fi
}

case "${1:-build}" in
    clean) clean ;;
    build) build ;;
    *) echo "用法: $0 [build|clean]" ; exit 1 ;;
esac
