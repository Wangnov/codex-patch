# codex-patch

Public mirror of `openai/codex` plus private patch automation.

- `mirror/main` tracks upstream without private changes.
- `patch/main` is the current releasable private line.
- `replay/<tag>` branches are temporary replay branches for upstream releases.

This repository preserves three private patch groups:

1. `what` / `why` plus the related `shnote` behavior
2. default cross-provider thread listing behavior
3. private version injection for release builds

Core automation entrypoints:

- `python3 scripts/check_latest_release.py --dry-run`
- `python3 scripts/replay_latest_release.py --release-tag <latest-rust-tag> --dry-run`
- pushing `codex-patch-rust-v*` tags triggers `.github/workflows/release-matrix.yml`

Release matrix notes:

- The GitHub repository is public so the release workflow is intentionally kept on standard GitHub-hosted runners.
- The current matrix is pinned to `ubuntu-24.04`, `ubuntu-24.04-arm`, `macos-15-intel`, `macos-15`, `windows-2022`, and `windows-11-arm`.
- Avoid larger runners and custom runner groups unless the release requirements change and the workflow is revalidated first.
