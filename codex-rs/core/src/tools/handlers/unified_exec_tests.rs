use super::*;
use crate::shell::default_user_shell;
use crate::tools::handlers::parse_arguments_with_base_path;
use crate::tools::handlers::resolve_workdir_base_path;
use codex_protocol::models::FileSystemPermissions;
use codex_protocol::models::PermissionProfile;
use codex_tools::UnifiedExecShellMode;
use codex_tools::ZshForkConfig;
use codex_utils_absolute_path::AbsolutePathBuf;
use core_test_support::PathExt;
use pretty_assertions::assert_eq;
use std::fs;
use std::sync::Arc;
use tempfile::tempdir;

use crate::codex::make_session_and_context;
use crate::tools::context::ExecCommandToolOutput;
use crate::tools::context::ToolInvocation;
use crate::tools::context::ToolPayload;
use crate::tools::registry::ToolHandler;
use crate::turn_diff_tracker::TurnDiffTracker;
use tokio::sync::Mutex;

#[test]
fn test_get_command_uses_default_shell_when_unspecified() -> anyhow::Result<()> {
    let json =
        r#"{"cmd":"echo hello","what":"print greeting text","why":"verify default shell behavior"}"#;

    let args: ExecCommandArgs = parse_arguments(json)?;

    assert!(args.shell.is_none());

    let command = get_command(
        &args,
        Arc::new(default_user_shell()),
        &UnifiedExecShellMode::Direct,
        /*allow_login_shell*/ true,
    )
    .map_err(anyhow::Error::msg)?;

    assert_eq!(command.len(), 3);
    assert_eq!(command[2], "echo hello");
    Ok(())
}

#[test]
fn test_get_command_respects_explicit_bash_shell() -> anyhow::Result<()> {
    let json = r#"{"cmd":"echo hello","what":"print greeting text","why":"verify explicit bash shell behavior","shell":"/bin/bash"}"#;

    let args: ExecCommandArgs = parse_arguments(json)?;

    assert_eq!(args.shell.as_deref(), Some("/bin/bash"));

    let command = get_command(
        &args,
        Arc::new(default_user_shell()),
        &UnifiedExecShellMode::Direct,
        /*allow_login_shell*/ true,
    )
    .map_err(anyhow::Error::msg)?;

    assert_eq!(command.last(), Some(&"echo hello".to_string()));
    if command
        .iter()
        .any(|arg| arg.eq_ignore_ascii_case("-Command"))
    {
        assert!(command.contains(&"-NoProfile".to_string()));
    }
    Ok(())
}

#[test]
fn test_get_command_respects_explicit_powershell_shell() -> anyhow::Result<()> {
    let json = r#"{"cmd":"echo hello","what":"print greeting text","why":"verify explicit powershell shell behavior","shell":"powershell"}"#;

    let args: ExecCommandArgs = parse_arguments(json)?;

    assert_eq!(args.shell.as_deref(), Some("powershell"));

    let command = get_command(
        &args,
        Arc::new(default_user_shell()),
        &UnifiedExecShellMode::Direct,
        /*allow_login_shell*/ true,
    )
    .map_err(anyhow::Error::msg)?;

    assert_eq!(command[2], "echo hello");
    Ok(())
}

#[test]
fn test_get_command_respects_explicit_cmd_shell() -> anyhow::Result<()> {
    let json = r#"{"cmd":"echo hello","what":"print greeting text","why":"verify explicit cmd shell behavior","shell":"cmd"}"#;

    let args: ExecCommandArgs = parse_arguments(json)?;

    assert_eq!(args.shell.as_deref(), Some("cmd"));

    let command = get_command(
        &args,
        Arc::new(default_user_shell()),
        &UnifiedExecShellMode::Direct,
        /*allow_login_shell*/ true,
    )
    .map_err(anyhow::Error::msg)?;

    assert_eq!(command[2], "echo hello");
    Ok(())
}

#[test]
fn test_get_command_rejects_explicit_login_when_disallowed() -> anyhow::Result<()> {
    let json = r#"{"cmd":"echo hello","what":"print greeting text","why":"verify disallowed login shell behavior","login":true}"#;

    let args: ExecCommandArgs = parse_arguments(json)?;
    let err = get_command(
        &args,
        Arc::new(default_user_shell()),
        &UnifiedExecShellMode::Direct,
        /*allow_login_shell*/ false,
    )
    .expect_err("explicit login should be rejected");

    assert!(
        err.contains("login shell is disabled by config"),
        "unexpected error: {err}"
    );
    Ok(())
}

#[test]
fn test_get_command_ignores_explicit_shell_in_zsh_fork_mode() -> anyhow::Result<()> {
    let json = r#"{"cmd": "echo hello", "shell": "/bin/bash"}"#;
    let args: ExecCommandArgs = parse_arguments(json)?;
    let shell_zsh_path = AbsolutePathBuf::from_absolute_path(if cfg!(windows) {
        r"C:\opt\codex\zsh"
    } else {
        "/opt/codex/zsh"
    })?;
    let shell_mode = UnifiedExecShellMode::ZshFork(ZshForkConfig {
        shell_zsh_path: shell_zsh_path.clone(),
        main_execve_wrapper_exe: AbsolutePathBuf::from_absolute_path(if cfg!(windows) {
            r"C:\opt\codex\codex-execve-wrapper"
        } else {
            "/opt/codex/codex-execve-wrapper"
        })?,
    });

    let command = get_command(
        &args,
        Arc::new(default_user_shell()),
        &shell_mode,
        /*allow_login_shell*/ true,
    )
    .map_err(anyhow::Error::msg)?;

    assert_eq!(
        command,
        vec![
            shell_zsh_path.to_string_lossy().to_string(),
            "-lc".to_string(),
            "echo hello".to_string()
        ]
    );
    Ok(())
}

#[test]
fn exec_command_args_resolve_relative_additional_permissions_against_workdir() -> anyhow::Result<()>
{
    let cwd = tempdir()?;
    let workdir = cwd.path().join("nested");
    fs::create_dir_all(&workdir)?;
    let expected_write = workdir.join("relative-write.txt");
    let json = r#"{
            "cmd": "echo hello",
            "what": "print greeting text",
            "why": "verify permission path resolution",
            "workdir": "nested",
            "additional_permissions": {
                "file_system": {
                    "write": ["./relative-write.txt"]
                }
            }
        }"#;

    let base_path = resolve_workdir_base_path(json, &cwd.path().abs())?;
    let args: ExecCommandArgs = parse_arguments_with_base_path(json, &base_path)?;

    assert_eq!(
        args.additional_permissions,
        Some(PermissionProfile {
            file_system: Some(FileSystemPermissions {
                read: None,
                write: Some(vec![expected_write.abs()]),
            }),
            ..Default::default()
        })
    );
    Ok(())
}

#[tokio::test]
async fn exec_command_pre_tool_use_payload_uses_raw_command() {
    let payload = ToolPayload::Function {
        arguments: serde_json::json!({ "cmd": "printf exec command" }).to_string(),
    };
    let (session, turn) = make_session_and_context().await;
    let handler = UnifiedExecHandler;

    assert_eq!(
        handler.pre_tool_use_payload(&ToolInvocation {
            session: session.into(),
            turn: turn.into(),
            tracker: Arc::new(Mutex::new(TurnDiffTracker::new())),
            call_id: "call-43".to_string(),
            tool_name: "exec_command".to_string(),
            tool_namespace: None,
            payload,
        }),
        Some(crate::tools::registry::PreToolUsePayload {
            command: "printf exec command".to_string(),
        })
    );
}

#[tokio::test]
async fn exec_command_pre_tool_use_payload_skips_write_stdin() {
    let payload = ToolPayload::Function {
        arguments: serde_json::json!({ "chars": "echo hi" }).to_string(),
    };
    let (session, turn) = make_session_and_context().await;
    let handler = UnifiedExecHandler;

    assert_eq!(
        handler.pre_tool_use_payload(&ToolInvocation {
            session: session.into(),
            turn: turn.into(),
            tracker: Arc::new(Mutex::new(TurnDiffTracker::new())),
            call_id: "call-44".to_string(),
            tool_name: "write_stdin".to_string(),
            tool_namespace: None,
            payload,
        }),
        None
    );
}

#[test]
fn exec_command_post_tool_use_payload_uses_output_for_noninteractive_one_shot_commands() {
    let payload = ToolPayload::Function {
        arguments: serde_json::json!({ "cmd": "echo three", "tty": false }).to_string(),
    };
    let output = ExecCommandToolOutput {
        event_call_id: "event-43".to_string(),
        chunk_id: "chunk-1".to_string(),
        wall_time: std::time::Duration::from_millis(498),
        raw_output: b"three".to_vec(),
        max_output_tokens: None,
        process_id: None,
        exit_code: Some(0),
        original_token_count: None,
        session_command: Some(vec![
            "/bin/zsh".to_string(),
            "-lc".to_string(),
            "echo three".to_string(),
        ]),
    };

    assert_eq!(
        UnifiedExecHandler.post_tool_use_payload("call-43", &payload, &output),
        Some(crate::tools::registry::PostToolUsePayload {
            command: "echo three".to_string(),
            tool_response: serde_json::json!("three"),
        })
    );
}

#[test]
fn exec_command_post_tool_use_payload_skips_interactive_exec() {
    let payload = ToolPayload::Function {
        arguments: serde_json::json!({ "cmd": "echo three", "tty": true }).to_string(),
    };
    let output = ExecCommandToolOutput {
        event_call_id: "event-44".to_string(),
        chunk_id: "chunk-1".to_string(),
        wall_time: std::time::Duration::from_millis(498),
        raw_output: b"three".to_vec(),
        max_output_tokens: None,
        process_id: None,
        exit_code: Some(0),
        original_token_count: None,
        session_command: Some(vec![
            "/bin/zsh".to_string(),
            "-lc".to_string(),
            "echo three".to_string(),
        ]),
    };

    assert_eq!(
        UnifiedExecHandler.post_tool_use_payload("call-44", &payload, &output),
        None
    );
}

#[test]
fn exec_command_post_tool_use_payload_skips_running_sessions() {
    let payload = ToolPayload::Function {
        arguments: serde_json::json!({ "cmd": "echo three", "tty": false }).to_string(),
    };
    let output = ExecCommandToolOutput {
        event_call_id: "event-45".to_string(),
        chunk_id: "chunk-1".to_string(),
        wall_time: std::time::Duration::from_millis(498),
        raw_output: b"three".to_vec(),
        max_output_tokens: None,
        process_id: Some(45),
        exit_code: None,
        original_token_count: None,
        session_command: Some(vec![
            "/bin/zsh".to_string(),
            "-lc".to_string(),
            "echo three".to_string(),
        ]),
    };

    assert_eq!(
        UnifiedExecHandler.post_tool_use_payload("call-45", &payload, &output),
        None
    );
}

#[test]
fn test_exec_command_allows_missing_what_and_why_arguments() -> anyhow::Result<()> {
    let args_without_what: ExecCommandArgs =
        parse_arguments(r#"{"cmd":"echo hello","why":"verify shell behavior"}"#)?;
    assert_eq!(args_without_what.what, None);

    let args_without_why: ExecCommandArgs =
        parse_arguments(r#"{"cmd":"echo hello","what":"print greeting text"}"#)?;
    assert_eq!(args_without_why.why, None);

    let args_without_purpose: ExecCommandArgs = parse_arguments(r#"{"cmd":"echo hello"}"#)?;
    assert_eq!(args_without_purpose.what, None);
    assert_eq!(args_without_purpose.why, None);

    Ok(())
}

#[test]
fn test_exec_command_rejects_blank_what_and_why() {
    assert!(
        validate_command_purpose(
            "exec_command",
            true,
            Some("run test command"),
            Some("verify behavior"),
        )
        .is_ok()
    );

    let blank_what =
        validate_command_purpose("exec_command", true, Some("  "), Some("verify behavior"))
            .expect_err("blank what should be rejected");
    assert!(
        blank_what
            .to_string()
            .contains("requires non-empty `what` and `why`")
    );

    let blank_why = validate_command_purpose(
        "exec_command",
        true,
        Some("run test command"),
        Some("  "),
    )
    .expect_err("blank why should be rejected");
    assert!(
        blank_why
            .to_string()
            .contains("requires non-empty `what` and `why`")
    );

    assert!(validate_command_purpose("exec_command", false, None, None).is_ok());
}
