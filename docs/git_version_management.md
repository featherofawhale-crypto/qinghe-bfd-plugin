# Git Version Management

## Current Local Version

- Latest local plugin build: `2.0.1-beta.26`
- Latest public macOS plugin release: `2.0.1-beta.25`
- Latest public Windows plugin release: `2.0.1-beta.26`
- Release channel: `beta`
- Public macOS package filename: `qinghe-toolbox-v2.0.1-beta.25-macos.dmg`
- Public Windows package filename: `QingheBFD_v2.0.1-beta.26_Windows_Setup.exe`
- Local beta25 package folder: `dist/protected_release/QingheEditingToolbox_v2.0.1-beta.25_mac`
- Canonical update manifests:
  - `latest.json`
  - `release/latest.json`

## Repository Boundaries

The repository should track source, tests, release metadata, website/docs, and update manifests.

Generated release folders, bundled runtime output, temporary Codex publishing work, legacy local install scripts, UI review screenshots, local videos, safety snapshots, and platform cache files should stay out of git. Release binaries are distributed through GitHub/CNB releases and referenced by the tracked manifests.

## Release Rule

When publishing a new beta, update both manifest files and the README download filename in the same commit, then tag the release commit with `v<version>` after verification.
