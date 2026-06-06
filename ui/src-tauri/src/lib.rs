use serde::Deserialize;
use serde::Serialize;
use serde_json::Value;
use std::fs::{self, File};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use uuid::Uuid;

#[derive(Debug, Clone, Serialize, Deserialize)]
struct ProgressEvent {
    timestamp: String,
    thread_id: String,
    step_key: String,
    label: String,
    agent: String,
    status: String,
    artifact_path: Option<String>,
    detail: Option<String>,
    current_stage: Option<String>,
}

#[derive(Debug, Serialize, Deserialize)]
struct WorkflowSnapshot {
    thread_id: Option<String>,
    workflow_status: Option<String>,
    current_stage: Option<String>,
    active_agent: Option<String>,
    waiting_for_agent: Option<String>,
    final_summary: Option<String>,
    manuscript_path: Option<String>,
    experiment_plan_path: Option<String>,
    experiment_result_path: Option<String>,
    advisor_review_path: Option<String>,
    reviewer_review_path: Option<String>,
    artifacts: Vec<Value>,
    messages_log: Vec<Value>,
    interrupt: Option<Value>,
    progress_events: Vec<ProgressEvent>,
}

fn project_root() -> Result<PathBuf, String> {
    if let Ok(value) = std::env::var("AI_SCIENTIST_PROJECT_ROOT") {
        return Ok(PathBuf::from(value));
    }
    let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    manifest_dir
        .parent()
        .and_then(Path::parent)
        .map(Path::to_path_buf)
        .ok_or_else(|| "无法解析项目根目录。".to_string())
}

fn workspace_root() -> Result<PathBuf, String> {
    Ok(project_root()?.join("workspace"))
}

fn resolve_python() -> String {
    if let Ok(value) = std::env::var("AI_SCIENTIST_PYTHON") {
        if !value.trim().is_empty() {
            return value;
        }
    }

    if let Ok(value) = std::env::var("VIRTUAL_ENV") {
        let candidate = PathBuf::from(value).join("Scripts").join("python.exe");
        if candidate.exists() {
            return candidate.to_string_lossy().to_string();
        }
    }

    if let Ok(value) = std::env::var("CONDA_PREFIX") {
        let candidate = PathBuf::from(value).join("python.exe");
        if candidate.exists() {
            return candidate.to_string_lossy().to_string();
        }
    }

    if let Ok(root) = project_root() {
        let venv_candidate = root.join(".venv").join("Scripts").join("python.exe");
        if venv_candidate.exists() {
            return venv_candidate.to_string_lossy().to_string();
        }
    }

    if let Ok(user_profile) = std::env::var("USERPROFILE") {
        let conda_candidate = PathBuf::from(user_profile)
            .join(".conda")
            .join("envs")
            .join("AI-Scientist")
            .join("python.exe");
        if conda_candidate.exists() {
            return conda_candidate.to_string_lossy().to_string();
        }
    }

    "python".to_string()
}

fn ensure_ui_log_dir() -> Result<PathBuf, String> {
    let path = workspace_root()?.join("logs");
    fs::create_dir_all(&path).map_err(|error| format!("创建日志目录失败：{error}"))?;
    Ok(path)
}

fn create_spawn_log(thread_id: &str, phase: &str) -> Result<(Stdio, Stdio), String> {
    let log_dir = ensure_ui_log_dir()?;
    let log_path = log_dir.join(format!("ui_{thread_id}_{phase}.log"));
    let stdout_file = File::create(&log_path).map_err(|error| format!("创建日志文件失败：{error}"))?;
    let stderr_file = stdout_file
        .try_clone()
        .map_err(|error| format!("克隆日志句柄失败：{error}"))?;
    Ok((Stdio::from(stdout_file), Stdio::from(stderr_file)))
}

fn read_jsonl_lines(path: &Path) -> Vec<Value> {
    let Ok(content) = fs::read_to_string(path) else {
        return Vec::new();
    };
    content
        .lines()
        .filter_map(|line| {
            let trimmed = line.trim();
            if trimmed.is_empty() {
                return None;
            }
            serde_json::from_str::<Value>(trimmed).ok()
        })
        .collect()
}

fn load_progress_events(thread_id: &str) -> Result<Vec<ProgressEvent>, String> {
    let path = workspace_root()?.join("logs").join("progress.jsonl");
    let events = read_jsonl_lines(&path)
        .into_iter()
        .filter_map(|value| serde_json::from_value::<ProgressEvent>(value).ok())
        .filter(|event| event.thread_id == thread_id)
        .collect();
    Ok(events)
}

fn workflow_completed(thread_id: &str) -> Result<bool, String> {
    let path = workspace_root()?.join("logs").join("workflow.jsonl");
    let completed = read_jsonl_lines(&path).into_iter().any(|value| {
        value.get("thread_id").and_then(Value::as_str) == Some(thread_id)
            && value.get("event").and_then(Value::as_str) == Some("completed")
    });
    Ok(completed)
}

fn last_artifact_path(events: &[ProgressEvent], step_keys: &[&str], agent: Option<&str>) -> Option<String> {
    events
        .iter()
        .rev()
        .find(|event| {
            event.artifact_path.is_some()
                && step_keys.iter().any(|step_key| event.step_key == *step_key)
                && agent.map(|expected| event.agent == expected).unwrap_or(true)
        })
        .and_then(|event| event.artifact_path.clone())
}

fn build_snapshot_from_logs(thread_id: &str) -> Result<WorkflowSnapshot, String> {
    let progress_events = load_progress_events(thread_id)?;
    let latest_event = progress_events.last().cloned();
    let completed = workflow_completed(thread_id)?;
    let waiting_for_experiment = progress_events
        .iter()
        .rev()
        .find(|event| event.step_key == "human_experiment")
        .map(|event| event.status == "waiting")
        .unwrap_or(false);

    let workflow_status = if completed {
        "completed"
    } else if waiting_for_experiment {
        "suspended"
    } else {
        "running"
    };

    let current_stage = if completed {
        Some("done".to_string())
    } else {
        latest_event
            .as_ref()
            .and_then(|event| event.current_stage.clone())
            .or_else(|| Some("bootstrap".to_string()))
    };

    let active_agent = if completed || waiting_for_experiment {
        None
    } else {
        latest_event.as_ref().map(|event| event.agent.clone())
    };

    let waiting_for_agent = if waiting_for_experiment {
        Some("human".to_string())
    } else {
        None
    };

    let manuscript_path = last_artifact_path(
        &progress_events,
        &["finalize", "final_polish", "manuscript_drafting"],
        None,
    );
    let experiment_plan_path = last_artifact_path(&progress_events, &["experiment_design"], Some("student"));
    let experiment_result_path = last_artifact_path(&progress_events, &["result_analysis"], Some("student"));
    let advisor_review_path = last_artifact_path(
        &progress_events,
        &["innovation_review", "advisor_result_gate", "advisor_paper_review"],
        Some("advisor"),
    );
    let reviewer_review_path =
        last_artifact_path(&progress_events, &["reviewer_blind_review"], Some("reviewer"));

    let final_summary = if completed {
        Some(
            [
                format!("线程 ID：{thread_id}"),
                format!("最终论文：{}", manuscript_path.clone().unwrap_or_default()),
                format!("导师意见：{}", advisor_review_path.clone().unwrap_or_default()),
                format!("盲审意见：{}", reviewer_review_path.clone().unwrap_or_default()),
            ]
            .join("\n"),
        )
    } else {
        None
    };

    Ok(WorkflowSnapshot {
        thread_id: Some(thread_id.to_string()),
        workflow_status: Some(workflow_status.to_string()),
        current_stage,
        active_agent,
        waiting_for_agent,
        final_summary,
        manuscript_path,
        experiment_plan_path,
        experiment_result_path,
        advisor_review_path,
        reviewer_review_path,
        artifacts: Vec::new(),
        messages_log: Vec::new(),
        interrupt: None,
        progress_events,
    })
}

fn resolve_workspace_artifact(path: &str) -> Result<PathBuf, String> {
    let candidate = PathBuf::from(path);
    if candidate.is_absolute() {
        return Ok(candidate);
    }
    Ok(workspace_root()?.join(candidate))
}

#[tauri::command]
fn start_workflow(paper_dir: String) -> Result<String, String> {
    let root = project_root()?;
    let thread_id = Uuid::new_v4().simple().to_string();
    let topic = Path::new(&paper_dir)
        .file_name()
        .and_then(|name| name.to_str())
        .filter(|value| !value.is_empty())
        .unwrap_or("自动生成论文")
        .to_string();
    let domain = "人工智能".to_string();
    let (stdout, stderr) = create_spawn_log(&thread_id, "start")?;

    Command::new(resolve_python())
        .args(["-m", "app.gui_cli"])
        .args([
            "--project-root".to_string(),
            root.to_string_lossy().to_string(),
            "start".to_string(),
            "--topic".to_string(),
            topic,
            "--domain".to_string(),
            domain,
            "--paper-dir".to_string(),
            paper_dir,
            "--thread-id".to_string(),
            thread_id.clone(),
        ])
        .current_dir(&root)
        .stdout(stdout)
        .stderr(stderr)
        .spawn()
        .map_err(|error| format!("启动工作流失败：{error}"))?;

    Ok(thread_id)
}

#[tauri::command]
fn resume_workflow(thread_id: String, resume_file: String) -> Result<(), String> {
    let root = project_root()?;
    let (stdout, stderr) = create_spawn_log(&thread_id, "resume")?;

    Command::new(resolve_python())
        .args(["-m", "app.gui_cli"])
        .args([
            "--project-root".to_string(),
            root.to_string_lossy().to_string(),
            "resume".to_string(),
            "--thread-id".to_string(),
            thread_id,
            "--resume-file".to_string(),
            resume_file,
        ])
        .current_dir(&root)
        .stdout(stdout)
        .stderr(stderr)
        .spawn()
        .map_err(|error| format!("恢复工作流失败：{error}"))?;

    Ok(())
}

#[tauri::command]
fn inspect_workflow(thread_id: String) -> Result<WorkflowSnapshot, String> {
    build_snapshot_from_logs(&thread_id)
}

#[tauri::command]
fn open_artifact(path: String) -> Result<(), String> {
    let resolved = resolve_workspace_artifact(&path)?;
    if !resolved.exists() {
        return Err(format!("文件不存在：{}", resolved.display()));
    }

    #[cfg(target_os = "windows")]
    {
        Command::new("cmd")
            .args(["/C", "start", "", &resolved.to_string_lossy()])
            .spawn()
            .map_err(|error| format!("打开文件失败：{error}"))?;
        return Ok(());
    }

    #[cfg(target_os = "macos")]
    {
        Command::new("open")
            .arg(&resolved)
            .spawn()
            .map_err(|error| format!("打开文件失败：{error}"))?;
        return Ok(());
    }

    #[cfg(all(unix, not(target_os = "macos")))]
    {
        Command::new("xdg-open")
            .arg(&resolved)
            .spawn()
            .map_err(|error| format!("打开文件失败：{error}"))?;
        return Ok(());
    }
}

pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![
            start_workflow,
            resume_workflow,
            inspect_workflow,
            open_artifact
        ])
        .run(tauri::generate_context!())
        .expect("failed to run tauri application");
}
