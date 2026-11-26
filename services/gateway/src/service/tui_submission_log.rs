//! 持久记录已认领发送或已确认取消的预留 ID。

use std::collections::BTreeMap;
use std::fs::{self, File, Metadata, OpenOptions};
use std::io::{self, Read, Write};
use std::os::fd::AsRawFd;
use std::os::unix::fs::{MetadataExt, OpenOptionsExt};
use std::path::Path;
use std::thread;
use std::time::{Duration, Instant};

use serde::{Deserialize, Serialize};
use uuid::Uuid;

use crate::service::diagnostics::tui_startup_event;
use crate::service::runtime_transport::{TransportBinding, now_ms};

use super::MAX_RECORDS;

const FILE: &str = "tui-v2-submissions.json";
const LOCK: &str = "tui-v2-submissions.lock";
const PENDING: &str = ".tui-v2-submissions.json.pending";
const MAX_BYTES: usize = MAX_RECORDS * 64 + 4096;

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Ledger {
    account_id: i64,
    environment_id: String,
    committed: BTreeMap<String, u64>,
    #[serde(default)]
    cancelled: BTreeMap<String, u64>,
}

/// 第一个持久化的操作决定预留的终态。
pub(super) enum Terminal {
    Submitted,
    Cancelled,
}

impl Ledger {
    fn len(&self) -> usize {
        self.committed.len() + self.cancelled.len()
    }

    fn deadline(&self, id: &str) -> Option<u64> {
        self.committed
            .get(id)
            .or_else(|| self.cancelled.get(id))
            .copied()
    }

    fn prune(&mut self, wall_now: u64) {
        self.committed.retain(|_, deadline| *deadline > wall_now);
        self.cancelled.retain(|_, deadline| *deadline > wall_now);
    }
}

fn invalid() -> io::Error {
    io::Error::new(
        io::ErrorKind::InvalidData,
        "V2 提交记录的存储或账号归属无效",
    )
}

pub(super) fn directory(path: &Path) -> io::Result<File> {
    let file = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW | libc::O_DIRECTORY)
        .open(path)?;
    let meta = file.metadata()?;
    if meta.uid() != unsafe { libc::geteuid() } || meta.mode() & 0o777 != 0o700 {
        return Err(invalid());
    }
    // 状态检查可核对挂载写权限，同时保持只读。
    let mut stats = std::mem::MaybeUninit::<libc::statvfs>::uninit();
    if unsafe { libc::fstatvfs(file.as_raw_fd(), stats.as_mut_ptr()) } != 0 {
        return Err(io::Error::last_os_error());
    }
    if unsafe { stats.assume_init() }.f_flag & libc::ST_RDONLY != 0 {
        return Err(invalid());
    }
    Ok(file)
}

fn private_metadata(file: &File) -> io::Result<Metadata> {
    let meta = file.metadata()?;
    if !meta.is_file() || meta.uid() != unsafe { libc::geteuid() } || meta.mode() & 0o777 != 0o600 {
        return Err(invalid());
    }
    Ok(meta)
}

/// 校验持久文件的属主、权限及唯一链接。@param file 已打开的私有文件。@return 核验结果。
pub(super) fn private_file(file: &File) -> io::Result<()> {
    if private_metadata(file)?.nlink() != 1 {
        return Err(invalid());
    }
    Ok(())
}

fn open_ledger(
    mut open: impl FnMut() -> io::Result<File>,
    read_deadline: Option<Instant>,
) -> io::Result<Option<File>> {
    let mut file = match open() {
        Ok(file) => file,
        Err(error) if error.kind() == io::ErrorKind::NotFound => return Ok(None),
        Err(error) => return Err(error),
    };
    loop {
        match (private_metadata(&file)?.nlink(), read_deadline) {
            (1, _) => return Ok(Some(file)),
            // 无锁读取可能先打开旧版本，随后写者完成原子替换。重开当前路径，依然只接纳单链接文件。
            (0, Some(deadline)) if Instant::now() < deadline => file = open()?,
            (0, Some(_)) => return Err(io::ErrorKind::TimedOut.into()),
            _ => return Err(invalid()),
        }
    }
}

fn load(
    root: &Path,
    account_id: i64,
    environment_id: String,
    read_deadline: Option<Instant>,
) -> io::Result<Ledger> {
    let path = root.join(FILE);
    let open = || {
        OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_NOFOLLOW | libc::O_NONBLOCK)
            .open(&path)
    };
    let file = match open_ledger(open, read_deadline)? {
        Some(file) => file,
        None => {
            return Ok(Ledger {
                account_id,
                environment_id,
                committed: BTreeMap::new(),
                cancelled: BTreeMap::new(),
            });
        }
    };
    let mut raw = Vec::new();
    file.take(MAX_BYTES as u64 + 1).read_to_end(&mut raw)?;
    if raw.len() > MAX_BYTES {
        return Err(invalid());
    }
    let ledger: Ledger = serde_json::from_slice(&raw).map_err(|_| invalid())?;
    if ledger.account_id != account_id
        || ledger.environment_id != environment_id
        || ledger.len() > MAX_RECORDS
        || ledger
            .committed
            .keys()
            .chain(ledger.cancelled.keys())
            .any(|id| !Uuid::parse_str(id).is_ok_and(|uuid| uuid.to_string() == *id))
        || ledger
            .cancelled
            .keys()
            .any(|id| ledger.committed.contains_key(id))
    {
        return Err(invalid());
    }
    Ok(ledger)
}

/// 取得用于工作区发布的文件锁。@param root 私有目录。@return 关闭时释放锁的文件。
pub(super) fn lock(root: &Path) -> io::Result<File> {
    lock_until(root, Instant::now() + Duration::from_secs(1))
}

fn lock_until(root: &Path, deadline: Instant) -> io::Result<File> {
    let file = OpenOptions::new()
        .read(true)
        .write(true)
        .create(true)
        .mode(0o600)
        .custom_flags(libc::O_NOFOLLOW | libc::O_NONBLOCK)
        .open(root.join(LOCK))?;
    private_file(&file)?;
    loop {
        let remaining = deadline
            .checked_duration_since(Instant::now())
            .filter(|remaining| !remaining.is_zero())
            .ok_or(io::ErrorKind::TimedOut)?;
        if unsafe { libc::flock(file.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) } == 0 {
            return Ok(file);
        }
        let error = io::Error::last_os_error();
        if !matches!(
            error.kind(),
            io::ErrorKind::WouldBlock | io::ErrorKind::Interrupted
        ) {
            return Err(error);
        }
        thread::sleep(remaining.min(Duration::from_millis(5)));
    }
}

fn save(root: &Path, directory: &File, ledger: &Ledger) -> io::Result<()> {
    let encoded = serde_json::to_vec(ledger).map_err(|_| invalid())?;
    // 文件锁内复用固定暂存名。进程中断最多留下一个待清理的暂存文件。
    let temp = root.join(PENDING);
    if let Err(error) = fs::remove_file(&temp)
        && error.kind() != io::ErrorKind::NotFound
    {
        return Err(error);
    }
    let mut file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .mode(0o600)
        .open(&temp)?;
    let result = file
        .write_all(&encoded)
        .and_then(|()| file.sync_all())
        .and_then(|()| fs::rename(&temp, root.join(FILE)))
        .and_then(|()| directory.sync_all());
    if result.is_err() {
        let _ = fs::remove_file(temp);
    }
    result
}

/// 只读核对账号存储及可选终态。@param root 私有持久目录。@param binding 当前账号绑定。
/// @param id 预留 ID，状态探测时为空。@param deadline 原调用单调截止。
/// @return 截止尚未通过的 ID 是否已被消费。
pub(super) async fn was_consumed(
    root: &Path,
    binding: &TransportBinding,
    id: Option<&str>,
    deadline: Instant,
) -> io::Result<bool> {
    let root = root.to_owned();
    let account_id = binding.account_id;
    let environment_id = binding.environment_id.clone();
    let id = id.map(str::to_owned);
    tokio::task::spawn_blocking(move || {
        directory(&root)?;
        let ledger = load(&root, account_id, environment_id, Some(deadline))?;
        Ok(id
            .and_then(|id| ledger.deadline(&id))
            .is_some_and(|deadline| deadline > now_ms()))
    })
    .await?
}

/// 以互斥方式原子保存并同步预留终态。@param root 私有持久目录。
/// @param binding 当前账号绑定。@param id 原预留 ID。@param deadline_ms 原信封截止。
/// @param deadline 当前 sender 对本次操作的单调截止。
/// @param terminal 发送认领或取消。@return 此次是否首次消费该 ID。
pub(super) async fn consume(
    root: &Path,
    binding: &TransportBinding,
    id: &str,
    deadline_ms: u64,
    deadline: Instant,
    terminal: Terminal,
) -> io::Result<bool> {
    let root = root.to_owned();
    let account_id = binding.account_id;
    let environment_id = binding.environment_id.clone();
    let id = id.to_owned();
    tokio::task::spawn_blocking(move || {
        let directory = directory(&root)?;
        let submitting = matches!(terminal, Terminal::Submitted);
        if submitting {
            tui_startup_event("sender_submission_ledger_lock", &id, None, Some("started"));
        }
        let lock = lock_until(&root, deadline);
        if submitting {
            let result = match &lock {
                Ok(_) => "acquired",
                Err(error) if error.kind() == io::ErrorKind::TimedOut => "deadline",
                Err(_) => "failed",
            };
            tui_startup_event("sender_submission_ledger_lock", &id, None, Some(result));
        }
        let _lock = lock?;
        let mut ledger = load(&root, account_id, environment_id, None)?;
        let wall_now = now_ms();
        if deadline_ms <= wall_now || Instant::now() >= deadline {
            return Err(io::ErrorKind::TimedOut.into());
        }
        ledger.prune(wall_now);
        if ledger.deadline(&id).is_some() {
            return Ok(false);
        }
        if ledger.len() >= MAX_RECORDS {
            return Err(io::ErrorKind::WouldBlock.into());
        }
        match terminal {
            Terminal::Submitted => ledger.committed.insert(id, deadline_ms),
            Terminal::Cancelled => ledger.cancelled.insert(id, deadline_ms),
        };
        save(&root, &directory, &ledger)?;
        Ok(true)
    })
    .await?
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::DirBuilderExt;

    /// 原子替换时，无锁读重新打开同一路径。多链接文件仍拒绝。@return 无。
    #[test]
    fn ledger_reader_reopens_replaced_inode_within_deadline() {
        let root = std::env::temp_dir().join(format!("ledger-read-{}", Uuid::new_v4()));
        fs::DirBuilder::new().mode(0o700).create(&root).unwrap();
        let path = root.join(FILE);
        let replacement = root.join(PENDING);
        for (file, data) in [(&path, b"old"), (&replacement, b"new")] {
            OpenOptions::new()
                .write(true)
                .create_new(true)
                .mode(0o600)
                .open(file)
                .unwrap()
                .write_all(data)
                .unwrap();
        }
        let deadline = Instant::now() + Duration::from_secs(1);
        let mut opened = 0;
        let mut file = open_ledger(
            || {
                let file = File::open(&path)?;
                opened += 1;
                if opened == 1 {
                    fs::rename(&replacement, &path)?;
                    assert_eq!(file.metadata()?.nlink(), 0);
                }
                Ok(file)
            },
            Some(deadline),
        )
        .unwrap()
        .unwrap();
        let mut value = String::new();
        file.read_to_string(&mut value).unwrap();
        assert_eq!(opened, 2);
        assert_eq!(value, "new");
        drop(file);
        fs::hard_link(&path, &replacement).unwrap();
        assert_eq!(
            open_ledger(|| File::open(&path), Some(deadline))
                .unwrap_err()
                .kind(),
            io::ErrorKind::InvalidData
        );
        fs::remove_dir_all(root).unwrap();
    }
}
