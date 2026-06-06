#!/usr/bin/env python3
"""
修改 UTM 4.7.5 的 config.plist，配置 Windows 11 ARM 虚拟机
"""

import plistlib
import os
import subprocess

VM_PATH = os.path.expanduser("~/Library/Containers/com.utmapp.UTM/Data/Documents/Windows 11 ARM.utm")
CONFIG_PATH = os.path.join(VM_PATH, "config.plist")
DATA_DIR = os.path.join(VM_PATH, "Data")
ISO_PATH = os.path.expanduser("~/Documents/26100.4349.250607-1500.ge_release_svc_refresh_CLIENTCONSUMER_RET_A64FRE_zh-cn.iso")

def modify_config():
    # 读取现有配置
    with open(CONFIG_PATH, "rb") as f:
        config = plistlib.load(f)

    print("=" * 60)
    print("🔧 修改 UTM Windows 11 ARM 配置")
    print("=" * 60)

    # 1. 设置CPU核心数
    config["System"]["CPUCount"] = 4
    print("✅ CPU核心数: 4")

    # 2. 设置内存（已经8192）
    print(f"✅ 内存: {config['System']['MemorySize']}MB ({config['System']['MemorySize']//1024}GB)")

    # 3. 修改磁盘1（VirtIO → NVMe，更大的空间）
    # 找到Disk类型的驱动器
    for drive in config.get("Drive", []):
        if drive.get("ImageType") == "Disk":
            # 改为NVMe接口
            drive["Interface"] = "NVMe"
            print(f"✅ 磁盘接口: VirtIO → NVMe")

            # 检查是否需要重新创建更大的磁盘
            disk_name = drive.get("ImageName", "")
            disk_path = os.path.join(DATA_DIR, disk_name)
            if os.path.exists(disk_path):
                size_mb = os.path.getsize(disk_path) / (1024*1024)
                print(f"  现有磁盘: {disk_name} ({size_mb:.0f}MB)")
            else:
                print(f"  磁盘文件: {disk_name} (将由UTM创建)")
            break

    # 4. 修改CD驱动器，添加ISO路径
    for drive in config.get("Drive", []):
        if drive.get("ImageType") == "CD":
            # UTM 4.x 使用 ImagePath 指定外部ISO文件
            drive["ImagePath"] = ISO_PATH
            print(f"✅ ISO已挂载: {os.path.basename(ISO_PATH)}")
            break

    # 5. 添加第二个CD驱动器用于SPICE工具（如果存在）
    spice_tools = os.path.expanduser(
        "~/Library/Containers/com.utmapp.UTM/Data/Library/Application Support/GuestSupportTools/utm-guest-tools-latest.iso"
    )
    if os.path.exists(spice_tools):
        print(f"✅ SPICE Guest Tools 已就绪: utm-guest-tools-latest.iso")
        # 暂不添加为第二个CD，等Windows安装完再加

    # 6. 确保UEFI和Hypervisor设置正确
    if "QEMU" in config:
        config["QEMU"]["UEFIBoot"] = True
        config["QEMU"]["Hypervisor"] = True
        print("✅ UEFI启动: 已启用")
        print("✅ Hypervisor加速: 已启用")

    # 7. 添加TPM设备（Windows 11需要，但可绕过）
    # UTM 4.x QEMU配置中 TPMDevice
    if "QEMU" in config:
        config["QEMU"]["TPMDevice"] = True
        print("✅ TPM 2.0: 已启用")

    # 8. 设置显示
    if "Display" not in config or not config["Display"]:
        config["Display"] = [{
            "Hardware": "virtio-ramfb",
            "DynamicResolution": True,
        }]
        print("✅ 显示: virtio-ramfb (动态分辨率)")

    # 9. 修改Sound（可选）
    if "Sound" not in config or not config["Sound"]:
        config["Sound"] = [{
            "Hardware": "intel-hda",
        }]
        print("✅ 音频: intel-hda")

    # 写回配置
    with open(CONFIG_PATH, "wb") as f:
        plistlib.dump(config, f)

    print("\n✅ 配置已更新!")
    print(f"📁 配置文件: {CONFIG_PATH}")

    # 打印配置摘要
    print("\n📋 配置摘要:")
    print(f"   VM名称: {config['Information']['Name']}")
    print(f"   架构: {config['System']['Architecture']}")
    print(f"   内存: {config['System']['MemorySize']}MB")
    print(f"   CPU: {config['System']['CPUCount']}核")
    print(f"   UEFI: {config['QEMU']['UEFIBoot']}")
    print(f"   Hypervisor: {config['QEMU']['Hypervisor']}")
    print(f"   TPM: {config['QEMU']['TPMDevice']}")
    print(f"   驱动器数量: {len(config.get('Drive', []))}")
    for i, drive in enumerate(config.get("Drive", [])):
        img_type = drive.get("ImageType", "?")
        iface = drive.get("Interface", "?")
        img_path = drive.get("ImagePath", drive.get("ImageName", "auto"))
        print(f"   驱动器{i+1}: {img_type} ({iface}) - {img_path}")

    return True

def main():
    if not os.path.exists(CONFIG_PATH):
        print(f"❌ 配置文件不存在: {CONFIG_PATH}")
        print("请确保虚拟机已在UTM中创建")
        return

    modify_config()

    print("\n" + "=" * 60)
    print("🚀 准备启动虚拟机...")
    print("💡 提示：安装过程中按 Shift+Fn+F10 打开命令提示符")
    print("   输入 regedit 添加以下绕过TPM的注册表项：")
    print("   HKEY_LOCAL_MACHINE\\SYSTEM\\Setup\\LabConfig")
    print("     BypassTPMCheck = 1 (DWORD)")
    print("     BypassSecureBootCheck = 1 (DWORD)")
    print("     BypassRAMCheck = 1 (DWORD)")
    print("     BypassStorageCheck = 1 (DWORD)")
    print("=" * 60)

if __name__ == "__main__":
    main()
