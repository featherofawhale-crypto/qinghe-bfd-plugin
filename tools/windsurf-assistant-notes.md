# windsurf-assistant

Source: https://github.com/zhouyoukang1234-spec/windsurf-assistant

Installed as a git submodule at:

```text
tools/windsurf-assistant
```

Current use in this project:

- Keep the external Windsurf/WAM assistant toolkit available for reference.
- Do not import it into the DaVinci Resolve plugin runtime.
- Do not auto-run its proxy, account, PAT, GitHub Actions, or VSIX install scripts from this project.

Useful local paths:

- `tools/windsurf-assistant/packages/wam`
- `tools/windsurf-assistant/packages/dao-proxy-min`
- `tools/windsurf-assistant/wam-bundle`

Update command:

```powershell
git submodule update --remote -- tools/windsurf-assistant
```
