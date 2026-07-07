#!/usr/bin/env python3
"""
R1 一键升级固件
===============
在本机启动 HTTP 服务器，音箱通过局域网直接下载升级包。

使用前请先执行 adb connect <音箱IP>

依赖：Python 3.7+（http.server 模块内置，无需额外安装）
"""

import os, sys, signal, tempfile, re, threading, http.server, socket
from pathlib import Path
from subprocess import run, PIPE, DEVNULL

SCRIPT_DIR = Path(__file__).resolve().parent
FIRMWARE_DIR = SCRIPT_DIR / "firmware"
OTA_DIR = SCRIPT_DIR / "ota"
HTTP_PORT = 8088


# ─── 工具函数 ────────────────────────────────────────────────

def adb(*args, check=False, text=True, **kwargs):
    """执行 adb 命令，返回 CompletedProcess"""
    # 如果调用方传了 stdout/stderr，就不自动 capture_output
    capture = "stdout" not in kwargs and "stderr" not in kwargs
    return run(["adb", *args], capture_output=capture, text=text, check=check, **kwargs)


def adb_shell(cmd, check=False):
    """执行 adb shell <cmd>，返回 stdout（去尾随换行和 \\r）"""
    r = adb("shell", cmd, check=check)
    return r.stdout.strip("\r\n ")


# ─── 颜色输出 ───────────────────────────────────────────────

class Color:
    GREEN = "\033[0;32m"
    YELLOW = "\033[1;33m"
    RED = "\033[0;31m"
    CYAN = "\033[0;36m"
    BOLD = "\033[1m"
    NC = "\033[0m"


def info(msg):   print(f"{Color.GREEN}[✓]{Color.NC} {msg}")
def warn(msg):   print(f"{Color.YELLOW}[!]{Color.NC} {msg}")
def error(msg):  print(f"{Color.RED}[✗]{Color.NC} {msg}", file=sys.stderr)


# ─── HTTP 服务器（后台线程） ─────────────────────────────────

httpd: http.server.HTTPServer | None = None


def start_http_server():
    """在后台线程启动 HTTP 服务器，提供 firmware/ 目录的文件"""
    global httpd
    os.chdir(str(FIRMWARE_DIR))

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(FIRMWARE_DIR), **kwargs)

        def log_message(self, fmt, *args):
            # 输出到 stderr 以便在主线程看到
            print(f"  {Color.CYAN}[HTTP]{Color.NC} {fmt % args}", file=sys.stderr)

    httpd = http.server.HTTPServer(("0.0.0.0", HTTP_PORT), Handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    info(f"HTTP 服务器已启动，端口 {HTTP_PORT}")


def stop_http_server():
    if httpd:
        httpd.shutdown()


# ─── 获取本机局域网 IP ──────────────────────────────────────

def get_local_ip() -> str:
    """通过 UDP 连接（不实际发送数据）获取本机局域网 IP"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.1)
        # 连接到一个外部地址（不会真的发数据）
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return ""


# ─── 主流程 ──────────────────────────────────────────────────

def main():
    print()
    print("  R1 一键升级固件")
    print("  （本机 HTTP 服务器 → 局域网升级）")
    print()

    # ── 前置检查 ──
    if not (FIRMWARE_DIR.is_dir() and OTA_DIR.is_dir()):
        error("firmware/ 和 ota/ 目录必须存在")
        sys.exit(1)

    # 检查 adb
    if not (shutil_which := __import__("shutil", fromlist=["which"]).which("adb")):
        error("adb 未安装，请先安装：")
        error("  macOS: brew install android-platform-tools")
        error("  Linux: sudo apt install adb")
        sys.exit(1)
    info(f"adb: {shutil_which}")

    # 检查设备连接
    r = adb("get-state")
    if r.returncode != 0 or r.stdout.strip() != "device":
        error("adb 未连接到设备，请先执行: adb connect <音箱IP>")
        sys.exit(1)
    serial = adb_shell("getprop ro.serialno")
    info(f"设备已连接: {serial}")

    # ── 获取设备信息 ──
    print()
    ver = adb_shell("getprop ro.build.version.incremental")
    build_host = adb_shell("getprop ro.build.host")
    build_model = adb_shell("getprop ro.product.model")

    print(f"  固件版本: {ver}")
    if build_host == "phicomm" and build_model == "rk322x-box":
        print("  设备识别: 斐讯 R1 ✅")
    else:
        warn(f"非标准 R1 设备（{build_host} / {build_model}）")

    if ver and ver.isdigit() and int(ver) > 2999 and int(ver) != 3448:
        warn(f"固件版本 {ver} 不是最新版 (3448)，可升级")

    if not ver:
        error("无法获取固件版本号")
        sys.exit(1)

    # ── 查找升级文件 ──
    ota_cfg = OTA_DIR / f"ota-{ver}.txt"
    fw_zip = FIRMWARE_DIR / f"incremental-ota-{ver}.zip"

    if not ota_cfg.exists():
        error(f"未找到升级配置: ota/ota-{ver}.txt")
        print("  支持的版本：")
        for f in sorted(OTA_DIR.glob("ota-*.txt")):
            print(f"    - {f.stem.removeprefix('ota-')}")
        sys.exit(1)

    if not fw_zip.exists():
        error(f"未找到升级包: firmware/incremental-ota-{ver}.zip")
        sys.exit(1)

    # 解析目标版本
    cur_fw_ver = ""
    for line in ota_cfg.read_text().splitlines():
        if line.startswith("ota_cur_fw_ver="):
            cur_fw_ver = line.split("=", 1)[1].strip()
            break

    fw_size = fw_zip.stat().st_size
    human_size = fw_size
    for unit in ("B", "K", "M", "G"):
        if human_size < 1024:
            human_size = f"{human_size:.0f}{unit}" if unit == "B" else f"{human_size:.1f}{unit}"
            break
        human_size /= 1024

    print()
    print(f"  当前版本: {ver}")
    print(f"  目标版本: {cur_fw_ver or '未知'}")
    print(f"  升级包:   {fw_zip.name}（{human_size}）")

    # ── 1. 清除 OTA 缓存 ──
    print()
    info("清除 OTA 服务缓存...")
    adb("shell", "/system/bin/pm", "clear", "com.phicomm.speaker.otaservice",
        stdout=DEVNULL, stderr=DEVNULL)

    # ── 2. 启动 HTTP 服务器 ──
    local_ip = get_local_ip()
    if not local_ip:
        error("无法获取本机局域网 IP")
        sys.exit(1)
    info(f"本机 IP: {local_ip}")

    start_http_server()
    print(f"  {Color.CYAN}地址:{Color.NC} http://{local_ip}:{HTTP_PORT}/{fw_zip.name}")

    # ── 3. 生成 otaprop.txt ──
    tmp = tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt")
    with ota_cfg.open() as f:
        for line in f:
            if line.startswith("ota_debug_url="):
                tmp.write(f"ota_debug_url=http://{local_ip}:{HTTP_PORT}/{fw_zip.name}\n")
            else:
                tmp.write(line)
    tmp.close()
    otaprop_path = tmp.name

    # ── 4. 推送 ──
    info("推送升级配置到 /sdcard/otaprop.txt ...")
    r = adb("push", otaprop_path, "/sdcard/otaprop.txt", stdout=DEVNULL, stderr=DEVNULL)
    if r.returncode != 0:
        error("推送失败")
        stop_http_server()
        os.unlink(otaprop_path)
        sys.exit(1)
    info("推送成功")
    os.unlink(otaprop_path)

    # ── 5. 重启 ──
    print()
    warn("即将重启音箱触发 OTA 升级！")
    print(f"  {Color.YELLOW}确保防火墙允许端口 {HTTP_PORT} 的入站连接{Color.NC}")
    print()
    try:
        input(f"{Color.CYAN}按回车执行重启，Ctrl+C 取消 > {Color.NC}")
    except (EOFError, KeyboardInterrupt):
        print()
        stop_http_server()
        sys.exit(0)

    info("重启设备...")
    adb("reboot")

    # ── 6. 等待 ──
    print()
    print("  设备已重启，升级流程：")
    print("  1. 音箱重新启动")
    print("  2. OTA 服务从本机下载升级包")
    print("  3. 自动安装并再次重启")
    print()
    print(f"  {Color.YELLOW}HTTP 服务器运行中，日志见上方{Color.NC}")
    print(f"  {Color.BOLD}升级完成后按回车结束{Color.NC}")
    try:
        input()
    except (EOFError, KeyboardInterrupt):
        pass

    stop_http_server()
    print()
    info("升级流程结束")
    warn("建议：升级后执行 adb shell rm /sdcard/otaprop.txt 清理残留")


if __name__ == "__main__":
    # 优雅退出
    signal.signal(signal.SIGINT, lambda s, f: sys.exit(0))
    main()
