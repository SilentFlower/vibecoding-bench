//! 账号发送器在首次提交时确定工作区，续轮从私有卷读取同一绑定。

use std::fs::{self, DirBuilder, File, OpenOptions};
use std::io::{self, BufReader, Write};
use std::os::unix::fs::{DirBuilderExt, OpenOptionsExt};
use std::path::Path;

use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use uuid::Uuid;

use super::{Identity, submission_log};
use crate::error::AppError;

/// 首次提交前的目录线索。取消预留时随连接释放。
pub(super) struct Candidate {
    client_path: Option<String>,
    new_turn: bool,
    branch: Option<String>,
}

/// 身份与目录保存在账号私有文件中，原生会话号由服务端创建。
#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Binding {
    session_key: String,
    client_path: Option<String>,
    native_session_id: String,
}

fn absolute_client_path(text: &str) -> bool {
    let b = text.as_bytes();
    let drive =
        b.len() >= 3 && b[0].is_ascii_alphabetic() && b[1] == b':' && matches!(b[2], b'/' | b'\\');
    let unc = text
        .strip_prefix(r"\\")
        .and_then(|tail| tail.split_once('\\'))
        .is_some_and(|(server, rest)| {
            !matches!(server, "" | "?" | ".")
                && rest
                    .split('\\')
                    .next()
                    .is_some_and(|share| !share.is_empty())
        });
    (text.starts_with('/') || drive || unc) && !text.chars().any(char::is_control)
}

// 只接受有边界的环境声明。路径说明工具执行地，绝不用于查找或挂载宿主目录。
fn declared(text: &str, in_user: bool) -> Option<&str> {
    let text = text.trim();
    let reminder = text
        .strip_prefix("<system-reminder>")
        .and_then(|v| v.strip_suffix("</system-reminder>"));
    let context = text
        .strip_prefix("<environment_context>")
        .and_then(|v| v.strip_suffix("</environment_context>"));
    if let Some(context) = context.or_else(|| (!in_user).then_some(text)) {
        let mut declarations = context.match_indices("<cwd>");
        if let Some((i, tag)) = declarations.next() {
            let (dir, tail) = context[i + tag.len()..].split_once("</cwd>")?;
            if !context[..i].rsplit('\n').next()?.trim().is_empty()
                || !tail.split('\n').next()?.trim().is_empty()
            {
                return None;
            }
            let dir = dir.trim();
            return (declarations.next().is_none() && absolute_client_path(dir)).then_some(dir);
        }
    }
    let mut lines = reminder
        .or_else(|| (!in_user).then_some(text))?
        .trim()
        .lines();
    if lines.next()?.trim() != "# Environment" {
        return None;
    }
    let mut paths = lines.filter_map(|line| {
        line.trim()
            .strip_prefix("- ")
            .unwrap_or(line.trim())
            .strip_prefix("Primary working directory:")
            .map(str::trim)
    });
    let path = paths.next()?;
    (absolute_client_path(path) && paths.next().is_none()).then_some(path)
}

fn from_content(content: &Value, in_user: bool) -> Option<&str> {
    if let Some(text) = content.as_str() {
        return declared(text, in_user);
    }
    content.as_array()?.iter().find_map(|block| {
        (block["type"] == "text")
            .then(|| block["text"].as_str())
            .flatten()
            .and_then(|s| declared(s, in_user))
    })
}

fn initial_path(body: &Value) -> Option<&str> {
    if let Some(dir) = from_content(&body["system"], false) {
        return Some(dir);
    }
    let mut first_user_seen = false;
    for msg in body["messages"].as_array()? {
        match msg["role"].as_str() {
            Some("system") => {
                if let Some(dir) = from_content(&msg["content"], false) {
                    return Some(dir);
                }
            }
            Some("user") if !first_user_seen => {
                first_user_seen = true;
                if let Some(dir) = from_content(&msg["content"], true) {
                    return Some(dir);
                }
            }
            _ => break,
        }
    }
    None
}

fn scoped_key(fields: impl Serialize) -> String {
    hex::encode(Sha256::digest(
        serde_json::to_vec(&fields).expect("仅编码身份元组"),
    ))
}

fn create_private(path: &Path) -> io::Result<File> {
    match DirBuilder::new().mode(0o700).create(path) {
        Ok(()) => File::open(path.parent().expect("账号卷子目录"))?.sync_all()?,
        Err(e) if e.kind() == io::ErrorKind::AlreadyExists => (),
        Err(e) => return Err(e),
    }
    submission_log::directory(path)
}

impl Candidate {
    /// 仅解析投递到支持工作区的事件源的 Messages 正文。
    /// @param body 已冻结的入站正文。@param new_turn 是否允许首次创建。
    /// @param branch 由已绑定源生成的子会话 UUID。@return 准备阶段的目录线索。
    pub(super) fn from_request(
        body: &[u8],
        new_turn: bool,
        branch: Option<String>,
    ) -> Result<Self, AppError> {
        if !new_turn || branch.is_some() {
            // 恢复只接受已有绑定。忽略本轮正文里的目录更新，也免去解析整段工具历史。
            return Ok(Self {
                client_path: None,
                new_turn,
                branch,
            });
        }
        let parsed: Value = serde_json::from_slice(body).map_err(|_| super::invalid_identity())?;
        Ok(Self {
            client_path: initial_path(&parsed).map(str::to_owned),
            new_turn,
            branch,
        })
    }

    /// 原子绑定或读取已有会话。跨进程争用时采用已落盘的首轮目录。
    /// @param root 账号私有卷。@param identity 已校验的账号、主体与会话。@return 交给源的启动资料位置及原生会话号。
    pub(super) fn bind(self, root: &Path, identity: &Identity) -> Result<Value, AppError> {
        let unavailable = |_| AppError::ServiceUnavailable("V2 工作区绑定存储不可用".into());
        submission_log::directory(root).map_err(unavailable)?;
        let _lock = submission_log::lock(root).map_err(unavailable)?;
        let scope = (
            identity.account_id,
            &identity.environment_id,
            identity.principal_id,
        );
        // 分支目录由已核验的源 UUID 决定，保持与父会话及兄弟的 HOME、工作区隔离。
        let session = self.branch.as_deref().unwrap_or(&identity.session_id);
        let session_key = scoped_key((scope, session));
        let base = root.join("tui-workspaces");
        let directory = create_private(&base).map_err(unavailable)?;
        let path = base.join(format!("{session_key}.json"));
        let file = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_NOFOLLOW | libc::O_NONBLOCK)
            .open(&path);
        let (binding, create) = match file {
            Ok(f) => {
                submission_log::private_file(&f).map_err(unavailable)?;
                let b: Binding =
                    serde_json::from_reader(BufReader::new(f)).map_err(|_| super::unavailable())?;
                if b.session_key != session_key
                    || !Uuid::parse_str(&b.native_session_id).is_ok_and(|id| {
                        id.get_version_num() == 4 && id.to_string() == b.native_session_id
                    })
                {
                    return Err(super::unavailable());
                }
                (b, false)
            }
            Err(e) if e.kind() == io::ErrorKind::NotFound && self.new_turn => (
                Binding {
                    session_key,
                    native_session_id: Uuid::new_v4().to_string(),
                    client_path: self.client_path,
                },
                true,
            ),
            Err(e) if e.kind() == io::ErrorKind::NotFound => {
                return Err(AppError::BadRequest(
                    "V2 原会话缺少可核对的工作区绑定".into(),
                ));
            }
            Err(e) => return Err(unavailable(e)),
        };
        // 未声明项目时按会话分配。不同主体即使传入同一路径也只会获得各自的运行目录。
        let project = match &binding.client_path {
            Some(client) => scoped_key((scope, "project", client)),
            None => scoped_key((scope, "session", session)),
        };
        let cwd = base.join(project);
        if create {
            create_private(&cwd).map_err(unavailable)?;
            // 与提交账本共用账号文件锁。崩溃时下次持锁者可覆盖尚未发布的临时文件。
            let pending = base.join(".binding.pending");
            match fs::remove_file(&pending) {
                Ok(()) => (),
                Err(e) if e.kind() == io::ErrorKind::NotFound => (),
                Err(e) => return Err(unavailable(e)),
            }
            let mut f = OpenOptions::new()
                .write(true)
                .create_new(true)
                .mode(0o600)
                .open(&pending)
                .map_err(unavailable)?;
            let bytes = serde_json::to_vec(&binding).map_err(|_| super::unavailable())?;
            f.write_all(&bytes)
                .and_then(|_| f.sync_all())
                .map_err(unavailable)?;
            fs::rename(&pending, &path)
                .and_then(|_| directory.sync_all())
                .map_err(unavailable)?;
        } else {
            submission_log::directory(&cwd).map_err(unavailable)?;
        }
        // 原文可能超过控制帧预算。源可从私有绑定文件读取完整目录，控制通道只传固定长度字段。
        Ok(
            json!({"version":1, "work_dir":cwd, "binding_file":path, "native_session_id":binding.native_session_id}),
        )
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::{Arc, Barrier};

    fn turn(principal: i64, session: &str) -> Identity {
        Identity {
            account_id: 7,
            principal_id: principal,
            environment_id: "env".into(),
            generation: 1,
            session_id: session.into(),
            reservation_id: Uuid::new_v4().to_string(),
            deadline_unix_ms: 0,
            continuation_only: false,
            agent_hint: None,
            agent_summary: false,
        }
    }

    fn example(path: &str) -> Value {
        json!({"messages":[{"role":"user","content":[{"type":"text","text":format!("<system-reminder>\n# Environment\n - Primary working directory: {path}\n</system-reminder>")},{"type":"text","text":"你好"}]}]})
    }

    /// 由可信源分配的子分支不能继承父目录，续轮仍可读自己的唯一布局。
    #[test]
    fn agent_workspace_keeps_a_private_stable_branch() {
        let root = std::env::temp_dir().join(format!("workspace-{}", Uuid::new_v4()));
        DirBuilder::new().mode(0o700).create(&root).unwrap();
        let request = serde_json::to_vec(&example("/outer/project")).unwrap();
        let identity = turn(1, "shared");
        let parent = Candidate::from_request(&request, true, None)
            .unwrap()
            .bind(&root, &identity)
            .unwrap();
        let branch = Uuid::new_v4().to_string();
        let child = Candidate::from_request(&request, true, Some(branch.clone()))
            .unwrap()
            .bind(&root, &identity)
            .unwrap();
        let resume = Candidate::from_request(&request, false, Some(branch))
            .unwrap()
            .bind(&root, &identity)
            .unwrap();
        assert_eq!(child, resume);
        for field in ["native_session_id", "work_dir", "binding_file"] {
            assert_ne!(child[field], parent[field]);
        }
        fs::remove_dir_all(&root).unwrap();
    }

    #[test]
    fn first_environment_keeps_the_callers_path() {
        for path in [
            r"C:\Work\团队 A",
            r"\\host\share\团队 A",
            "D:/Work/Team A",
            "/Users/李/项目",
            "/home/me/project",
            "/mnt/c/Work/团队 A",
        ] {
            assert_eq!(initial_path(&example(path)), Some(path));
        }
        for p in [
            "relative",
            r"C:project",
            r"\project",
            r"\\server",
            r"\\?\C:\test",
        ] {
            assert_eq!(initial_path(&example(p)), None);
        }
        let mut body = example("/a");
        body["messages"].as_array_mut().unwrap().extend([
            json!({"role":"assistant","content":"好"}),
            example("/b")["messages"][0].clone(),
        ]);
        assert_eq!(initial_path(&body), Some("/a"));
        body["messages"][0]["content"][0]["text"] =
            json!("举例：Primary working directory: /quoted");
        assert_eq!(initial_path(&body), None);
        body["system"] = json!([{"type":"text","text":"普通文本引用 <cwd>/example</cwd>"}]);
        assert_eq!(initial_path(&body), None);
        body["system"] = json!([{"type":"text","text":"<cwd>\nC:\\外层\\项目\n</cwd>"}]);
        assert_eq!(initial_path(&body), Some(r"C:\外层\项目"));
    }

    #[test]
    fn first_commit_survives_concurrent_claims_restart_and_same_path_other_principal() {
        let root = std::env::temp_dir().join(format!("workspace-{}", Uuid::new_v4()));
        DirBuilder::new().mode(0o700).create(&root).unwrap();
        let barrier = Arc::new(Barrier::new(2));
        let mut threads = Vec::new();
        for p in [r"C:\Work\同时", r"\\host\share\并发"] {
            let barrier = barrier.clone();
            let root = root.clone();
            threads.push(std::thread::spawn(move || {
                barrier.wait();
                Candidate {
                    client_path: Some(p.into()),
                    new_turn: true,
                    branch: None,
                }
                .bind(&root, &turn(1, "same"))
                .unwrap()
            }));
        }
        let winners: Vec<_> = threads.into_iter().map(|t| t.join().unwrap()).collect();
        assert_eq!(winners[0], winners[1]);
        let first = &winners[0];
        let saved: Binding =
            serde_json::from_slice(&fs::read(first["binding_file"].as_str().unwrap()).unwrap())
                .unwrap();
        let bind = |who, session, p, new_turn| {
            Candidate {
                client_path: p,
                new_turn,
                branch: None,
            }
            .bind(&root, &turn(who, session))
        };
        assert_eq!(
            *first,
            bind(1, "same", Some("/after-cd".into()), false).unwrap()
        );
        let second = bind(2, "same", saved.client_path.clone(), true).unwrap();
        assert_ne!(first["native_session_id"], second["native_session_id"]);
        assert_ne!(first["work_dir"], second["work_dir"]);
        let independent = bind(1, "separate", saved.client_path, true).unwrap();
        assert_eq!(first["work_dir"], independent["work_dir"]);
        assert_ne!(first["native_session_id"], independent["native_session_id"]);
        assert!(bind(3, "same", None, false).is_err());
        let unspecified = bind(3, "same", None, true).unwrap();
        assert_eq!(
            unspecified,
            bind(3, "same", Some("/later".into()), false).unwrap()
        );
        assert_ne!(
            unspecified["work_dir"],
            bind(3, "separate", None, true).unwrap()["work_dir"]
        );
        fs::remove_dir_all(&root).unwrap();
    }
}
