# codex-patch

Mirror of `openai/codex` plus private patch automation.

- `mirror/main` tracks upstream without private changes.
- `patch/main` is the current releasable private line.
- `replay/<tag>` branches are temporary replay branches for upstream releases.

This repository preserves three private patch groups:

1. `what` / `why` plus the related `shnote` behavior
2. default cross-provider thread listing behavior
3. private version injection for release builds
