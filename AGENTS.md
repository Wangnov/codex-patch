# codex-patch

You are maintaining a private patch line on top of `openai/codex`.

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
