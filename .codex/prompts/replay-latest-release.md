You are maintaining the `codex-patch` private patch line on top of `openai/codex`.

Replay the private patch intent onto upstream release `{release_tag}`.

Repository: `{repo_root}`
Replay branch: `{replay_branch}`
Expected private display version: `{display_version}`
Expected private git tag: `{private_git_tag}`
Patch generation: `{private_patch_generation}`

Private requirements to preserve:
1. Preserve `what` / `why` plus the related `shnote` behavior.
2. Preserve default cross-provider thread listing behavior.
3. Preserve private version injection for patch releases.

Working rules:
- Resolve conflicts from the patch author's perspective.
- Preserve private intent even if upstream refactors files.
- Minimize human intervention.
- Work in `{repo_root}` directly. The launcher keeps that worktree clean enough for the replay branch checkout.
- Do not create a linked worktree unless git itself forces you to.
- Do not inject the private version yourself. The launcher will do that after your replay commits are in place.
- Do not sync repository metadata or release workflow files yourself. The launcher will do that before final bookkeeping.
- Do not run the minimal validation commands yourself. The launcher will do that after version injection.
- Do not run full-workspace tests.
- Do not rely on global Codex config or global skills; this run is intentionally isolated to this repository setup.
- Do not update `patch/main`, do not write replay state files, and do not create the private release tag. Leave the completed result on `{replay_branch}` only. The launcher will handle bookkeeping and final branch/tag updates.

Required git flow:
1. Ensure upstream tag `{release_tag}` exists locally. If it is missing, fetch only that tag from `upstream`.
2. Check out `{replay_branch}` from `{release_tag}`.
3. Replay the patch groups below in order.
4. Leave `{replay_branch}` checked out with the finished replay commits only.

Patch manifest:
- `{patch_manifest_path}`

Release manifest:
- `{release_manifest_path}`

Patch groups to replay in order:
{patch_groups}

Launcher-owned minimal validation commands:
{validation_commands}

Success criteria:
- The replay branch contains the required private behavior on top of `{release_tag}`.
- Leave `{replay_branch}` checked out so the launcher can inject `{display_version}`, sync repository metadata, and run the minimal validation.
- Your final message briefly summarizes conflicts resolved and commits created.
