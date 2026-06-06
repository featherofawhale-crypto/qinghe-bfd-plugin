#!/usr/bin/env python3
"""
直接创建 UTM .utm 包来安装 Windows 11 ARM
无需通过 AppleScript，直接写 config.plist
"""

import os
import subprocess
import plistlib
import uuid
import shutil

ISO_PATH = os.path.expanduser("~/Documents/26100.4349.250607-1500.ge_release_svc_refresh_CLIENTCONSUMER_RET_A64FRE_zh-cn.iso")
VM_NAME = "Windows 11 ARM"
UTM_DIR = os.path.expanduser(f"~/Documents/{VM_NAME}.utm")
DATA_DIR = os.path.join(UTM_DIR, "Data")
CONFIG_PATH = os.path.join(UTM_DIR, "config.plist")

RAM_MB = 8192
CPU_CORES = 4
DISK_SIZE_MB = 65536  # 64GB

def create_config():
    """创建config.plist"""
    config = {
        "ConfigurationVersion": 2,
        "Debug": {},
        "Display": {
            "ConsoleFont": "Menlo",
            "ConsoleFontSize": 12,
            "ConsoleOnly": False,
            "ConsoleTheme": "Default",
            "DisplayCard": "virtio-ramfb",
            "DisplayDownscaler": "linear",
            "DisplayUpscaler": "nearest",
        },
        "Drives": [
            {
                "DriveName": "nvme0",
                "ImageType": "disk",
                "InterfaceType": "nvme",
                "ImagePath": "Windows11.qcow2",
                "ImageSize": DISK_SIZE_MB,  # MB
                "Removable": False,
            },
            {
                "DriveName": "cdrom0",
                "ImagePath": ISO_PATH,
                "ImageType": "cd",
                "InterfaceType": "usb",
                "Removable": True,
            },
        ],
        "Info": {
            "Icon": "windows",
        },
        "Input": {},
        "Networking": {
            "NetworkCard": "virtio-net-pci",
            "NetworkCardMAC": generate_mac(),
            "NetworkMode": "shared",
        },
        "Printing": {},
        "Sharing": {
            "ClipboardSharing": True,
            "DirectoryReadOnly": False,
            "DirectorySharing": True,
            "Usb3Support": False,
            "UsbRedirectMax": 3,
        },
        "Sound": {
            "SoundCard": "intel-hda",
            "SoundEnabled": True,
        },
        "System": {
            "Architecture": "aarch64",
            "BootDevice": "",
            "BootUefi": True,
            "CPU": "default",
            "CPUCount": CPU_CORES,
            "MachineProperties": "highmem=off",
            "Memory": RAM_MB,
            "RngEnabled": True,
            "SystemUUID": str(uuid.uuid4()).upper(),
            "Target": "virt",
            "UseHypervisor": True,
        },
    }
    return config

def generate_mac():
    """生成随机MAC地址 (QEMU格式)"""
    mac = [
        0x52, 0x54, 0x00,  # QEMU默认前缀
        uuid.uuid4().bytes[0] & 0xFE,  # 确保unicast
        uuid.uuid4().bytes[1],
        uuid.uuid4().bytes[2],
    ]
    return ":".join(f"{b:02X}" for b in mac)

def create_utm_package():
    """创建.utm包"""
    # 创建目录结构
    os.makedirs(DATA_DIR, exist_ok=True)

    # 写config.plist
    config = create_config()
    with open(CONFIG_PATH, "wb") as f:
        plistlib.dump(config, f)
    print(f"✅ config.plist 已创建: {CONFIG_PATH}")

    # 预创建磁盘镜像 (如果需要)
    # qcow2路径
    qcow2_path = os.path.join(DATA_DIR, "Windows11.qcow2")
    if not os.path.exists(qcow2_path):
        print(f"🔧 创建虚拟磁盘镜像 ({DISK_SIZE_MB//1024}GB)...")
        result = subprocess.run(
            ["qemu-img", "create", "-f", "qcow2", qcow2_path, f"{DISK_SIZE_MB}M"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            print(f"  ✅ 虚拟磁盘已创建: {qcow2_path}")
        else:
            print(f"  ⚠️ qemu-img创建失败: {result.stderr}")
            print(f"  💡 UTM会在VM启动时自动创建磁盘镜像")
    else:
        print(f"  ℹ️ 虚拟磁盘已存在: {qcow2_path}")

    print(f"\n✅ UTM包创建完成: {UTM_DIR}")
    return True

def open_in_utm():
    """在UTM中打开.utm包"""
    print(f"\n🚀 正在UTM中打开虚拟机...")
    result = subprocess.run(
        ["open", "-a", "UTM", UTM_DIR],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        print("  ✅ 已发送到UTM")
        return True
    else:
        print(f"  ❌ 打开失败: {result.stderr}")
        return False

def print_instructions():
    """打印安装说明"""
    print("""
╔══════════════════════════════════════════════════════════╗
║     🪟 Windows 11 ARM 安装指南                          ║
╠══════════════════════════════════════════════════════════╣
║                                                        ║
║  1. 在UTM中点击 ▶️ 启动虚拟机                            ║
║  2. 看到 "Press any key to boot from CD/DVD" 时按键     ║
║  3. 选择语言，点击"下一步"                               ║
║  4. 点击"现在安装"                                       ║
║  5. 提示输入产品密钥 → 选择 **"我没有产品密钥"**          ║
║  6. 选择 Windows 11 Pro/Home                            ║
║  7. 选择 **"自定义: 仅安装Windows"**                     ║
║  8. 选择"驱动器0未分配的空间"，点击"下一步"               ║
║                                                        ║
║  ⚠️ 重要：绕过TPM/网络限制                               ║
║  安装过程中按 Shift+Fn+F10 (或 Shift+F10) 打开CMD:      ║
║    > regedit                                          ║
║    (在HKEY_LOCAL_MACHINE\SYSTEM\Setup下)               ║
║    新建 LabConfig 项，添加以下 DWORD (32位) 值:          ║
║      BypassTPMCheck = 1                                ║
║      BypassSecureBootCheck = 1                          ║
║      BypassRAMCheck = 1                                 ║
║      BypassStorageCheck = 1                             ║
║    关闭regedit，关闭CMD，继续安装                        ║
║                                                        ║
║  或者直接跳过网络要求:                                    ║
║    Shift+F10 → OOBE\\BYPASSNRO → 回车 → 自动重启       ║
║                                                        ║
║  ⚠️ 如果进入EFI Shell (启动失败):                        ║
║    在Shell中输入:                                        ║
║      map -r                                             ║
║      FS0:                                               ║
║      cd EFI                                             ║
║      cd BOOT                                            ║
║      BOOTAA64.EFI                                       ║
║                                                        ║
╚══════════════════════════════════════════════════════════╝
""")

def main():
    print("=" * 60)
    print("🪟 UTM Windows 11 ARM .utm 包创建工具")
    print("=" * 60)

    # 检查ISO
    if not os.path.exists(ISO_PATH):
        print(f"❌ ISO文件不存在: {ISO_PATH}")
        return

    # 检查qemu-img
    qemu_img = shutil.which("qemu-img")
    if not qemu_img:
        # 尝试UTM自带的
        qemu_img = "/Applications/UTM.app/Contents/Resources/qemu/bin/qemu-img"
    print(f"  qemu-img: {qemu_img}")

    # 创建.utm包
    if os.path.exists(UTM_DIR):
        print(f"⚠️ 目标目录已存在: {UTM_DIR}")
        resp = input("是否覆盖？(1=是): ").strip()
        if resp == "1":
            shutil.rmtree(UTM_DIR)
            print("  已删除旧目录")
        else:
            print("  已取消")
            return

    create_utm_package()

    # 创建qcow2磁盘
    qcow2_path = os.path.join(DATA_DIR, "Windows11.qcow2")
    if not os.path.exists(qcow2_path):
        print(f"\n🔧 创建虚拟磁盘...")
        result = subprocess.run(
            [qemu_img, "create", "-f", "qcow2", qcow2_path, f"{DISK_SIZE_MB}M"],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode == 0:
            print(f"  ✅ 虚拟磁盘已创建: {qcow2_path}")
        else:
            print(f"  ⚠️ qemu-img失败: {result.stderr}")
            print(f"  💡 手动创建: qemu-img create -f qcow2 {qcow2_path} {DISK_SIZE_MB}M")

    print_instructions()

    # 在UTM中打开
    open_in_utm()

    print("\n✅ 完成！UTM中应该能看到 'Windows 11 ARM' 虚拟机了")
    print("📌 按照上面的说明启动并安装Windows 11")

if __name__ == "__main__":
    main()
