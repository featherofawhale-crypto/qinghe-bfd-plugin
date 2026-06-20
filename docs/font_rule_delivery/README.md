# 清何字体探针规则交付包

本目录是 DaVinci Resolve Text+ 字体切换规则交付包。规则分为两层：精确映射规则和兜底探测规则。

## 两层规则

1. `basic_font_rules.json`
   - 基础字体映射规则。
   - 每条都是“原字体名直接失败”后，找到 Resolve/Text+ 真正接受的字体名。
   - 只有同时通过 Text+ 读回和 PNG 可视化验证，才会进入这里。

2. `fallback_probe_rules.json`
   - 兜底探测规则。
   - 当基础映射库没有命中时，用这些泛化规则继续生成候选名。
   - 这些规则来自已验证样本的归纳：PostScript 名、ASCII family、family/style 打包、FontManager 注册等。

## 当前验证结果

- 基础映射条数：`2808`
- 去重映射键：`2808`
- 离线验证失败规则：`0`

注意：离线验证只能证明规则字段满足交付格式和历史证据门槛；最终可用性必须以 Resolve Text+ 现场切换并渲染成功为准。

## 规则成立标准

一条基础映射规则必须全部满足：

- `direct_before=false`
- `accepted != source`，不能把原本可直接切换的字体算作规则
- Resolve Text+ 接受修正候选名，并且读回匹配
- 渲染帧不是 `Font Not Found` 等 Resolve 错误提示画面
- 渲染帧有可见字形
- 中文字体使用中英文混合样本：`清何黑帧检测 QH123`
- 中文字体要求中文部分不是方框字形
- 英文字体允许中文方框，但英文部分必须能正常显示，用于证明字体已切换
- 画面必须保持白底字形：`near_white_pct>=50`，`non_white_pct<=15`，`very_dark_pct<=10`

## 关键命令

诊断 Resolve 外部脚本接口：

```powershell
python docs\font_rule_delivery\font_probe_rules.py --diagnose-resolve-scripting --resolve-preflight-timeout 30
```

逐条重检旧规则：

```powershell
python docs\font_rule_delivery\font_probe_rules.py --recheck-results artifacts\font_probe_reports\visual_6000.jsonl --visual --rules-require-visual --output artifacts\font_probe_reports\visual_6000_recheck.jsonl --rules-output artifacts\font_probe_reports\visual_6000_recheck_rules.json --timeline-index 7 --track-index 1 --item-index 5 --timecode 01:00:19:07 --keep-visual-png
```

验证交付包：

```powershell
python docs\font_rule_delivery\validate_font_rule_delivery.py
```

## 文件说明

- `basic_font_rules.json`：基础映射规则。
- `fallback_probe_rules.json`：兜底探测规则。
- `validate_font_rule_delivery.py`：验证本目录规则是否满足标准。
- `run_strict_font_probe.ps1`：继续采集严格视觉规则的脚本。
- `font_probe_rules.py`：完整测试脚本副本。
- `source_manifest.json`：生成来源和统计信息。

## 当前已知阻断

`source_manifest.json` 的 `blocked_rules` 记录现场确认会触发 Resolve `Font Not Found` 的规则。这类规则不会进入 `basic_font_rules.json`。
