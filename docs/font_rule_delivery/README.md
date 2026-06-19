# 清何字体探针规则交付包

本目录是 DaVinci Resolve Text+ 字体切换的两层规则交付包。

## 两层规则

1. `basic_font_rules.json`
   - 基础字体映射规则。
   - 每条都是“原字体名直接失败”后，找到 Resolve/Text+ 真正接受的字体名。
   - 只有同时通过 Text+ 读回和 PNG 中文可视化验证，才会进入这里。

2. `fallback_probe_rules.json`
   - 兜底探测规则。
   - 当基础映射库没有命中时，用这些泛化规则继续生成候选名。
   - 这些规则来自已验证样本的归纳：PostScript 名、ASCII family、family/style 打包、FontManager 注册等。

## 当前验证结果

- 基础映射条数：`1000`
- 去重映射键：`1000`
- 失败规则：`0`

## 规则成立标准

一条基础映射规则必须全部满足：

- `direct_before=false`
- `accepted != source`，不能把原本可直接切换的字体算作规则
- Resolve Text+ 接受修正候选名，并且读回匹配
- 渲染 PNG 可见真实中文
- `tofu_suspect=false`
- `glyph_segments>=4`

## 文件说明

- `basic_font_rules.json`：基础映射规则。
- `fallback_probe_rules.json`：兜底探测规则。
- `validate_font_rule_delivery.py`：验证本目录规则是否满足标准。
- `run_strict_font_probe.ps1`：继续采集严格视觉规则的脚本。
- `font_probe_rules.py`：完整测试脚本副本。
- `source_manifest.json`：生成来源和统计信息。
