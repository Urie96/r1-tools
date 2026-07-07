#!/usr/bin/env python3
"""
R1 绑定工具
===========
不依赖 busybox，将音箱的绑定状态配置文件拉到本地修改再放回。

原理：
  SharedPreferences 里 isBinded=true → App 认为已绑定，跳过云端绑定流程

使用前请先 adb connect <音箱IP>
"""

import os, sys, tempfile, re, xml.sax.saxutils
from pathlib import Path
from subprocess import run, PIPE, DEVNULL

PACKAGE = "com.phicomm.speaker.device"
PREFS_FILE = "defaultSp.xml"


# ─── 颜色 ───────────────────────────────────────────────────

class C:
    GREEN = "\033[0;32m"; YELLOW = "\033[1;33m"
    RED = "\033[0;31m"; CYAN = "\033[0;36m"; BOLD = "\033[1m"; NC = "\033[0m"

def info(msg):  print(f"{C.GREEN}[✓]{C.NC} {msg}")
def warn(msg):  print(f"{C.YELLOW}[!]{C.NC} {msg}")
def error(msg): print(f"{C.RED}[✗]{C.NC} {msg}", file=sys.stderr)


# ─── adb 辅助 ───────────────────────────────────────────────

def adb(*args, **kwargs):
    capture = "stdout" not in kwargs and "stderr" not in kwargs
    return run(["adb", *args], capture_output=capture, text=True, **kwargs)


def adb_shell(cmd, **kwargs):
    r = adb("shell", cmd, **kwargs)
    return r.stdout.strip("\r\n ")


# ─── 修改 XML ───────────────────────────────────────────────

def set_binded(xml: str) -> str:
    """在 SharedPreferences XML 中插入 isBinded=true"""
    # 如果已经存在 isBinded，确保值为 true
    if 'name="isBinded"' in xml or "name='isBinded'" in xml:
        xml = re.sub(
            r'<boolean\s+name=["\']isBinded["\']\s+value=["\']([^"\']*)["\']\s*/>',
            '<boolean name="isBinded" value="true"/>',
            xml,
        )
        return xml

    # 不存在则插入：在包含 <set> 的行后添加
    # SharedPreferences 格式：<string name="set">...</string> 或 <set> 标签
    line = '<boolean name="isBinded" value="true"/>'
    # 找 <string name="set"> 开头的行，在其后插入
    inserted = False
    out = []
    for line_text in xml.splitlines(keepends=True):
        out.append(line_text)
        if not inserted and ("<string name=\"set\"" in line_text or "<string name='set'" in line_text):
            out.append(f"  {line}\n")
            inserted = True
    if not inserted:
        # fallback：在 </map> 前插入
        xml = xml.replace("</map>", f"  {line}\n</map>")
        return xml
    return "".join(out)


# ─── 主流程 ─────────────────────────────────────────────────

def main():
    print()
    print("  R1 绑定工具（无需 busybox）")
    print()

    # 检查 adb
    if not (shutil_which := __import__("shutil", fromlist=["which"]).which("adb")):
        error("adb 未安装")
        sys.exit(1)

    # 检查连接
    r = adb("get-state")
    if r.returncode != 0 or r.stdout.strip() != "device":
        error("请先执行 adb connect <音箱IP>")
        sys.exit(1)
    info("设备已连接")

    # 检查 run-as 是否可用
    r_test = adb("shell", f"run-as {PACKAGE} ls ./shared_prefs/", stderr=PIPE)
    if r_test.returncode != 0:
        error(f"run-as 不可用，无法访问 {PACKAGE} 的数据目录")
        error("某些固件可能限制了 run-as，原版方案需要 busybox 也是因为这个")
        sys.exit(1)
    info("run-as 可用")

    # ── 1. 杀掉小讯进程 ──
    info("结束小讯进程...")
    adb("shell", "am", "force-stop", PACKAGE, stdout=DEVNULL, stderr=DEVNULL)

    # ── 2. 把配置文件拉到本地 ──
    info("拉取配置文件...")
    r = adb("exec-out", "run-as", PACKAGE, "cat", f"./shared_prefs/{PREFS_FILE}")
    if r.returncode != 0 or not r.stdout.strip():
        # fallback: 先 cp 到 /sdcard 再 pull
        warn("exec-out 方式失败，尝试先复制到 /sdcard ...")
        adb("shell", "run-as", PACKAGE, "cp", f"./shared_prefs/{PREFS_FILE}", f"/sdcard/{PREFS_FILE}",
            stdout=DEVNULL, stderr=DEVNULL)
        r = adb("pull", f"/sdcard/{PREFS_FILE}", stderr=DEVNULL)
        if r.returncode != 0:
            error("无法获取配置文件")
            sys.exit(1)
        xml_content = r.stdout
        adb("shell", "rm", f"/sdcard/{PREFS_FILE}", stdout=DEVNULL, stderr=DEVNULL)
    else:
        xml_content = r.stdout

    if not xml_content.strip():
        error("配置文件为空")
        sys.exit(1)

    # ── 3. 修改 ──
    info("修改绑定状态...")
    new_xml = set_binded(xml_content)

    if new_xml == xml_content:
        warn("isBinded 已经是 true，无需修改")
    else:
        # 打印差异
        for i, (old_l, new_l) in enumerate(zip(xml_content.splitlines(), new_xml.splitlines())):
            if old_l != new_l:
                print(f"  {C.YELLOW}~{C.NC} {new_l.strip()}")

    # ── 4. 推回设备 ──
    info("写回设备...")
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False)
    tmp.write(new_xml)
    tmp.close()

    # 推到 /sdcard/
    r = adb("push", tmp.name, f"/sdcard/{PREFS_FILE}", stdout=DEVNULL, stderr=DEVNULL)
    os.unlink(tmp.name)
    if r.returncode != 0:
        error("推送失败")
        sys.exit(1)

    # 用 run-as cp 从 /sdcard 拷回应用目录
    r = adb("shell", "run-as", PACKAGE, "cp", f"/sdcard/{PREFS_FILE}", f"./shared_prefs/{PREFS_FILE}",
            stderr=PIPE)
    adb("shell", "rm", f"/sdcard/{PREFS_FILE}", stdout=DEVNULL, stderr=DEVNULL)
    if r.returncode != 0:
        error("复制回应用目录失败")
        error(f"错误: {r.stderr.strip()}")
        sys.exit(1)

    info("绑定配置已写入")

    # ── 5. 重启 ──
    print()
    warn("即将重启音箱使绑定生效")
    try:
        input(f"{C.CYAN}按回车重启，Ctrl+C 取消 > {C.NC}")
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(0)

    info("重启设备...")
    adb("reboot")
    print()
    info("已重启，等待开机完成后唤醒小讯测试是否绑定成功")


if __name__ == "__main__":
    main()
