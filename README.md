# 清何剪辑工具箱（DaVinci Resolve 黑帧/夹帧检测）

这是给 DaVinci Resolve 用户使用的剪辑检查插件。当前公开版本为 macOS 测试版，打开安装包后运行一键安装脚本即可使用。

官网页面：

https://featherofawhale-crypto.github.io/qinghe-bfd-plugin/

## 它能做什么

- 快速检查时间线里的黑帧、夹帧、重复帧、异常空隙等问题
- 给检测结果自动打标记，方便回到时间线逐个修正
- 支持复杂时间线、字幕/Text+、字体管理和剪辑节拍辅助
- macOS 包内置 Python 3.9、PySide6/Qt、FFmpeg 和 Resolve API Bridge，不要求普通用户自己配置命令行环境
- 带有插件内“更新”按钮，后续可以直接检查新版本

## 下载 macOS 安装包

请到右侧或下方的 GitHub Release 下载：

- `qinghe-toolbox-v2.0.1-beta.23-macos.dmg`

Release 地址：

https://github.com/featherofawhale-crypto/qinghe-bfd-plugin/releases/latest

当前公开包是 Apple Silicon / arm64 macOS 测试版。Windows 版本会等在 Windows 电脑上单独打包测试后再发布。

## 一键安装方法

1. 下载并双击打开 `qinghe-toolbox-v2.0.1-beta.23-macos.dmg`。
2. 在打开的窗口里，右键点击 `① 一键安装.command`。
3. 选择“打开”，按提示完成安装。
4. 重启 DaVinci Resolve。
5. 在 DaVinci Resolve 里打开：`工作区 -> 脚本 -> Edit -> 清何黑帧夹帧检测`。

如果 macOS 提示“无法打开”或“来自未认证开发者”，请不要直接双击脚本，改用右键“打开”。当前公开包没有做 Apple Developer 公证，所以第一次打开时 macOS 会拦一下。DMG 内也附带了“macOS无法验证处理说明.txt”和修复脚本。

## 插件内更新

插件右上角有“更新”按钮。它会先尝试国内更新源，失败后再走 GitHub 备用源。

当前 macOS 更新清单已经放在：

- `release/latest.json`
- GitHub Release 附件里的 `latest.json`

macOS 这版更新包使用 DMG。插件会下载 DMG，并提示用户打开安装包后运行一键安装。Windows 更新包暂时不放，等 Windows 端打包测试通过后再同步。

## 卸载

重新打开 DMG，运行：

- `一键卸载.command`

也可以手动删除 DaVinci Resolve 脚本目录里的 `清何黑帧夹帧检测.lua` 和 `Modules/black_frame_detector` 文件夹。

## 关于源码

这个公开仓库只放用户安装说明、更新清单和发布包入口。插件源码、内部开发文档、验收文档不会在这里展开发布。
