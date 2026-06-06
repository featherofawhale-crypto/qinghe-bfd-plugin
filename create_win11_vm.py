#!/usr/bin/env python3
"""
通过 UTM AppleScript 接口自动化创建 Windows 11 ARM 虚拟机
用法: python3 create_win11_vm.py
"""

import subprocess
import os

ISO_PATH = os.path.expanduser("~/Documents/26100.4349.250607-1500.ge_release_svc_refresh_CLIENTCONSUMER_RET_A64FRE_zh-cn.iso")
VM_NAME = "Windows 11 ARM"
RAM_MB = 8192
CPU_CORES = 4
DISK_SIZE_MB = 65536  # 64GB

def run_applescript(script):
    """执行AppleScript并返回结果"""
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True, text=True, timeout=60
    )
    if result.returncode != 0:
        print(f"❌ AppleScript错误: {result.stderr.strip()}")
        return None
    return result.stdout.strip()

def create_vm():
    """步骤1: 创建虚拟机"""
    print("🔧 步骤1: 创建虚拟机...")

    script = f'''
    tell application "UTM"
        make new virtual machine with properties {{
            backend:qemu,
            configuration:{{
                name:"{VM_NAME}",
                architecture:"aarch64",
                memory:{RAM_MB},
                cpu cores:{CPU_CORES},
                uefi:true,
                hypervisor:true
            }}
        }}
    end tell
    '''

    result = run_applescript(script)
    if result:
        print(f"  ✅ 虚拟机创建成功: {result}")
    else:
        print("  ❌ 虚拟机创建失败")
    return result

def configure_drives():
    """步骤2: 配置驱动器 (NVMe硬盘 + ISO CD/DVD)"""
    print("🔧 步骤2: 配置驱动器...")

    # 添加NVMe硬盘
    script_nvme = f'''
    tell application "UTM"
        set vmList to every virtual machine
        repeat with vm in vmList
            if name of vm is "{VM_NAME}" then
                update configuration of vm with {{
                    |drives|:{{
                        {{
                            |interface|:NVMe,
                            |guest size|:{DISK_SIZE_MB},
                            raw:false
                        }}
                    }}
                }}
            end if
        end repeat
    end tell
    '''
    result = run_applescript(script_nvme)
    if result is not None:
        print(f"  ✅ NVMe硬盘配置成功 ({DISK_SIZE_MB//1024}GB)")
    else:
        print("  ⚠️ NVMe硬盘配置失败，继续...")

    # 添加ISO作为CD/DVD
    script_iso = f'''
    tell application "UTM"
        set vmList to every virtual machine
        repeat with vm in vmList
            if name of vm is "{VM_NAME}" then
                update configuration of vm with {{
                    |drives|:{{
                        {{
                            |interface|:USB,
                            removable:true,
                            source:"{ISO_PATH}"
                        }}
                    }}
                }}
            end if
        end repeat
    end tell
    '''
    result = run_applescript(script_iso)
    if result is not None:
        print(f"  ✅ ISO挂载成功")
    else:
        print("  ⚠️ ISO挂载失败")

    return True

def configure_network():
    """步骤3: 配置网络"""
    print("🔧 步骤3: 配置网络...")

    script = f'''
    tell application "UTM"
        set vmList to every virtual machine
        repeat with vm in vmList
            if name of vm is "{VM_NAME}" then
                update configuration of vm with {{
                    |network interfaces|:{{
                        {{
                            |hardware|:"virtio-net-pci",
                            |mode|:shared
                        }}
                    }}
                }}
            end if
        end repeat
    end tell
    '''
    result = run_applescript(script)
    if result is not None:
        print("  ✅ 网络配置成功 (shared模式, virtio-net-pci)")
    else:
        print("  ⚠️ 网络配置失败")
    return True

def configure_display():
    """步骤4: 配置显示"""
    print("🔧 步骤4: 配置显示...")

    script = f'''
    tell application "UTM"
        set vmList to every virtual machine
        repeat with vm in vmList
            if name of vm is "{VM_NAME}" then
                update configuration of vm with {{
                    |displays|:{{
                        {{
                            |hardware|:"virtio-gpu-pci",
                            |dynamic resolution|:true
                        }}
                    }}
                }}
            end if
        end repeat
    end tell
    '''
    result = run_applescript(script)
    if result is not None:
        print("  ✅ 显示配置成功 (virtio-gpu, 动态分辨率)")
    else:
        print("  ⚠️ 显示配置失败")
    return True

def start_vm():
    """步骤5: 启动虚拟机"""
    print("🔧 步骤5: 启动虚拟机...")

    script = f'''
    tell application "UTM"
        set vmList to every virtual machine
        repeat with vm in vmList
            if name of vm is "{VM_NAME}" then
                start vm
                return "started"
            end if
        end repeat
    end tell
    '''
    result = run_applescript(script)
    if result == "started":
        print("  ✅ 虚拟机已启动！")
        print("\n📌 请在UTM窗口中按任意键启动Windows安装程序")
        print("💡 提示：如果看到EFI Shell，请输入以下命令：")
        print("   map -r")
        print("   FS0:")
        print("   cd EFI")
        print("   cd BOOT")
        print("   BOOTAA64.EFI")
    else:
        print("  ❌ 虚拟机启动失败")
    return result == "started"

def verify_vm():
    """验证虚拟机配置"""
    print("🔍 验证虚拟机状态...")

    script = f'''
    tell application "UTM"
        set vmList to every virtual machine
        set output to ""
        repeat with vm in vmList
            if name of vm is "{VM_NAME}" then
                set output to "名称: " & name of vm & "\\n"
                set output to output & "ID: " & id of vm & "\\n"
                set output to output & "后端: " & (backend of vm as text) & "\\n"
                set output to output & "状态: " & (status of vm as text) & "\\n"
            end if
        end repeat
        return output
    end tell
    '''
    result = run_applescript(script)
    if result:
        print(f"  {result}")
    else:
        print("  ⚠️ 未找到虚拟机")
    return True

def main():
    print("=" * 60)
    print("🚀 UTM Windows 11 ARM 虚拟机自动创建工具")
    print("=" * 60)
    print(f"  ISO: {ISO_PATH}")
    print(f"  VM名称: {VM_NAME}")
    print(f"  内存: {RAM_MB // 1024}GB")
    print(f"  CPU: {CPU_CORES}核")
    print(f"  硬盘: {DISK_SIZE_MB // 1024}GB")
    print(f"  架构: ARM64 (aarch64)")
    print()

    # 验证ISO存在
    if not os.path.exists(ISO_PATH):
        print(f"❌ ISO文件不存在: {ISO_PATH}")
        return

    # 步骤1: 创建VM
    if not create_vm():
        print("❌ 无法创建虚拟机，请检查UTM是否运行")
        return

    # 步骤2: 配置驱动器
    configure_drives()

    # 步骤3: 配置网络
    configure_network()

    # 步骤4: 配置显示
    configure_display()

    # 验证
    verify_vm()

    # 步骤5: 启动
    print()
    response = input("是否启动虚拟机？(1=是/Enter=是): ").strip()
    if response in ("", "1", "y", "Y", "yes"):
        start_vm()
    else:
        print("已跳过启动，请在UTM中手动启动")

if __name__ == "__main__":
    main()
