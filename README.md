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
- `python3 scripts/replay_latest_release.py --release-tag <latest-rust-tag>` launches `codex exec` for the replay itself
- pushing `codex-patch-rust-v*` tags triggers `.github/workflows/release-matrix.yml`

Agentic replay notes:

- The replay plan and bookkeeping stay in Python scripts, but the actual replay and conflict resolution are executed by `codex exec`.
- `codex exec` only handles the patch replay itself. The launcher injects the private version, syncs this repository's replay metadata and release workflows onto the replay branch, runs the minimal validation commands, records replay state, and then moves `patch/main`.
- The launcher points `HOME` at `.codex-runtime/home`, `CODEX_HOME` at `.codex-runtime/codex-home`, and `CODEX_SQLITE_HOME` at `.codex-runtime/sqlite-home`.
- The launcher copies repo-local `.codex/config.toml`, `.codex/prompts/`, and `.codex/skills/` into `.codex-runtime/codex-home` before each replay run, so tracked replay inputs stay authoritative and tracked files stay clean.
- Official replay auth comes from the OpenAI provider. When `~/.codex/auth.json` exists, the launcher copies it into the runtime `CODEX_HOME`.
- The launcher also reads optional local overrides from `.codex-runtime/codex-exec.env`, so you can keep values such as `OPENAI_API_KEY=...` on disk without committing them.
- Active replay tracking uses lock files under `state/replays/` so the launcher does not dirty the main worktree before the agent starts.

Release matrix notes:

- The GitHub repository is public so the release workflow is intentionally kept on standard GitHub-hosted runners.
- Private release artifacts only publish the `codex` CLI binary for each target platform.
- The current matrix is pinned to `ubuntu-24.04`, `ubuntu-24.04-arm`, `macos-15-intel`, `macos-15`, `windows-2022`, and `windows-11-arm`.
- Linux release runners install `libcap-dev` before building so `codex-linux-sandbox` can compile for the CLI package.
- Non-Windows release builds force `CARGO_PROFILE_RELEASE_LTO=thin` to stay closer to upstream release behavior and reduce ARM runner pressure.
- The Windows ARM CLI build adds `/arm64hazardfree` to the MSVC linker flags to avoid the known `LNK1322` Cortex-A53 hazard check failure.
- Avoid larger runners and custom runner groups unless the release requirements change and the workflow is revalidated first.
