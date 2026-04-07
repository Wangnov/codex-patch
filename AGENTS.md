# codex-patch

You are maintaining a public patch repository that carries a private patch line on top of `openai/codex`.

Private requirements:
1. Preserve `what` / `why` plus the related `shnote` behavior.
2. Preserve default cross-provider thread listing behavior.
3. Preserve private version injection for patch releases.

Rules:
- Trigger replay only when the upstream GitHub `Latest release` changes.
- Resolve conflicts as the private patch author would.
- Preserve private intent even if upstream refactors files.
- Run only minimal validation. Never default to full-workspace tests.
- Write replay results to machine-readable state files.
- Escalate only if upstream changes make private requirements ambiguous or incompatible.
- Do not rely on full tag fetches for routine checks; detect the latest release first and fetch the specific release tag when needed.
- This repository is public. Prefer standard GitHub-hosted runner labels that are currently valid for public repositories.
- For the release matrix, stay on explicitly pinned standard runners: `ubuntu-24.04`, `ubuntu-24.04-arm`, `macos-15-intel`, `macos-15`, `windows-2022`, and `windows-11-arm`.
- Do not switch the release matrix to larger runners such as `macos-15-xlarge`, or to custom/self-hosted runner groups, unless the workflow is revalidated against the current GitHub documentation and the repo requirements change.
