# R1 Tools / 斐讯 R1 工具箱

斐讯 R1 智慧音箱的折腾工具集。

## 前置要求

- Python 3.7+
- [ADB (Android Debug Bridge)](https://developer.android.com/studio/command-line/adb)
  - macOS: `brew install android-platform-tools`
  - Linux: `sudo apt install adb`
  - Windows: 安装 [Android SDK Platform Tools](https://developer.android.com/studio/releases/platform-tools)
- 音箱需与电脑在同一局域网
- 首次连接: `adb connect <音箱IP>`

---

## 工具

### 1. `bind_r1.py` — 绑定工具

通过修改音箱本地配置，绕过云端绑定流程。

**原理：**

App 的绑定状态保存在 SharedPreferences (`defaultSp.xml`) 中。将 `isBinded` 设为 `true` 后，App 会认为已经绑定过账号，从而跳过云端绑定流程。

**使用：**

```bash
adb connect <音箱IP>    # 连接音箱
python3 bind_r1.py      # 执行绑定
```

脚本会自动：
1. 杀掉小讯进程
2. 从设备拉取 `defaultSp.xml`
3. 将 `isBinded` 修改为 `true`
4. 将修改后的文件推回设备
5. 重启音箱

### 2. `upgrade_r1.py` — 固件升级工具

在本机启动 HTTP 服务器，让音箱通过局域网直接下载升级包。

**使用：**

```bash
adb connect <音箱IP>    # 连接音箱
python3 upgrade_r1.py   # 执行升级
```

需要将固件文件放在对应目录：

```
firmware/incremental-ota-<版本号>.zip
ota/ota-<版本号>.txt
```

脚本会自动：
1. 检测当前固件版本
2. 启动本地 HTTP 服务器
3. 推送 OTA 配置到 `/sdcard/otaprop.txt`
4. 重启音箱触发升级
5. 等待升级完成

**支持升级的固件版本：**

| 当前版本 | 升级文件 |
|---------|---------|
| 3119 → 3166 | `incremental-ota-3119.zip` |
| 3166 → 3174 | `incremental-ota-3166.zip` |
| 3174 → 3318 | `incremental-ota-3174.zip` |
| 3318 → 3331 | `incremental-ota-3318.zip` |
| 3331 → 3415 | `incremental-ota-3331.zip` |
| 3415 → 3448 | `incremental-ota-3415.zip` |

> 注意：只有 `incremental-ota-3415.zip`（3415→3448）是最终版本升级包。如果版本较旧，需要逐步升级。

### 3. `setup-wifi.sh` — WiFi 配置脚本

在音箱处于热点模式时配置 WiFi 网络。

**使用：**

```bash
# 按音箱顶部按钮 6 秒进入配网模式
# 连接小讯的 WiFi 热点
chmod +x setup-wifi.sh
./setup-wifi.sh
```

---

## 目录结构

```
r1-tools/
├── bind_r1.py              # 绑定工具
├── upgrade_r1.py           # 固件升级工具
├── setup-wifi.sh           # WiFi 配置脚本
├── firmware/               # 固件升级包
│   ├── incremental-ota-3119.zip
│   ├── incremental-ota-3166.zip
│   ├── incremental-ota-3174.zip
│   ├── incremental-ota-3318.zip
│   ├── incremental-ota-3331.zip
│   └── incremental-ota-3415.zip
├── ota/                    # OTA 配置文件
│   ├── ota-3119.txt
│   ├── ota-3166.txt
│   ├── ota-3174.txt
│   ├── ota-3318.txt
│   ├── ota-3331.txt
│   └── ota-3415.txt
├── README.md
└── .gitignore
```

## 常见问题

**ADB 找不到？**

```bash
# macOS
brew install android-platform-tools

# Linux (Debian/Ubuntu)
sudo apt install adb
```

**设备离线？**

尝试重新连接：先 `adb disconnect`，再 `adb connect <IP>`。

**防火墙拦截？**

使用 `upgrade_r1.py` 时，确保防火墙允许端口 `8088` 的入站连接。

**run-as 权限被拒？**

部分固件限制了 `run-as`，此时需要使用基于 `busybox` 的原始方案。

## 许可

MIT
