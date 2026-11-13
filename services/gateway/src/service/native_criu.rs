//! 受信账号恢复器的私有客户端；命名空间pidfd覆盖物理生命周期。

use std::fs;
use std::io;
use std::mem::{size_of, zeroed};
use std::os::fd::{AsRawFd, FromRawFd, OwnedFd};
use std::os::unix::fs::MetadataExt;

use libc::{CMSG_DATA, CMSG_FIRSTHDR, CMSG_LEN, CMSG_NXTHDR};
use serde_json::{Value, json};
use tokio::io::unix::AsyncFd;
use tokio::io::{AsyncReadExt, AsyncWriteExt, Interest};
use tokio::net::UnixStream;
use tokio::process::{ChildStdin, ChildStdout};
use uuid::Uuid;

const SOCKET: &str = "/run/ccrb-criu/control.sock";
pub(super) const ENTROPY_PROFILE: &str = "bun143-wipeonfork-v1";
pub(super) const IMAGE_SHA256: &str =
    "564019c9560e960e96875c9663975491534b27c789ea3d23e5c13309ff293c79";

/// 查询部署入口显式启用的恢复能力。@return 是否允许尝试私有恢复器。
pub(super) fn enabled() -> bool {
    std::env::var("CCRB_CRIU").is_ok_and(|value| value == "1")
}

fn invalid() -> io::Error {
    io::Error::other("CRIU_CONTROL_INVALID")
}

async fn connect() -> io::Result<UnixStream> {
    let metadata = fs::symlink_metadata(SOCKET)?;
    if metadata.uid() != 0 || metadata.mode() & 0o007 != 0 {
        return Err(invalid());
    }
    let connection = UnixStream::connect(SOCKET).await?;
    if connection.peer_cred()?.uid() != 0 {
        return Err(invalid());
    }
    Ok(connection)
}

async fn send(connection: &mut UnixStream, value: &Value) -> io::Result<()> {
    let mut content = serde_json::to_vec(value).map_err(|_| invalid())?;
    content.push(b'\n');
    connection.write_all(&content).await
}

async fn receive(connection: &mut UnixStream) -> io::Result<Value> {
    let mut content = Vec::new();
    while content.len() < 4096 {
        let byte = connection.read_u8().await?;
        content.push(byte);
        if byte == b'\n' {
            return serde_json::from_slice(&content).map_err(|_| invalid());
        }
    }
    Err(invalid())
}

/// 从单标志字节取回精确数量的描述符；所有拒绝分支都关闭已安装的FD。
async fn receive_fds(connection: &UnixStream, count: usize) -> io::Result<Vec<OwnedFd>> {
    loop {
        connection.readable().await?;
        let attempt = connection.try_io(Interest::READABLE, || {
            let mut marker = [0u8; 1];
            let mut vector = libc::iovec {
                iov_base: marker.as_mut_ptr().cast(),
                iov_len: 1,
            };
            // usize数组保证cmsghdr对齐；容量大于协议上限，先接管全部FD再拒绝。
            let mut control = [0usize; 32];
            let mut message: libc::msghdr = unsafe { zeroed() };
            message.msg_iov = &mut vector;
            message.msg_iovlen = 1;
            message.msg_control = control.as_mut_ptr().cast();
            message.msg_controllen = size_of_val(&control);
            let received = unsafe {
                libc::recvmsg(connection.as_raw_fd(), &mut message, libc::MSG_CMSG_CLOEXEC)
            };
            if received < 0 {
                return Err(io::Error::last_os_error());
            }
            let mut descriptors = Vec::new();
            let mut valid = true;
            unsafe {
                let mut header = CMSG_FIRSTHDR(&message);
                while !header.is_null() {
                    if (*header).cmsg_level != libc::SOL_SOCKET
                        || (*header).cmsg_type != libc::SCM_RIGHTS
                        || (*header).cmsg_len < CMSG_LEN(0) as usize
                    {
                        valid = false;
                    } else {
                        let bytes = (*header).cmsg_len - CMSG_LEN(0) as usize;
                        if bytes % size_of::<i32>() != 0 {
                            valid = false;
                        }
                        for index in 0..bytes / size_of::<i32>() {
                            descriptors.push(OwnedFd::from_raw_fd(
                                *CMSG_DATA(header).cast::<i32>().add(index),
                            ));
                        }
                    }
                    header = CMSG_NXTHDR(&message, header);
                }
            }
            if received != 1
                || marker != [b'F']
                || !valid
                || message.msg_flags & (libc::MSG_CTRUNC | libc::MSG_TRUNC) != 0
                || descriptors.len() != count
            {
                return Err(invalid());
            }
            Ok(descriptors)
        });
        match attempt {
            Err(error) if error.kind() == io::ErrorKind::WouldBlock => continue,
            result => return result,
        }
    }
}

fn pidfd_matches(descriptor: &OwnedFd, pid: u32) -> io::Result<()> {
    let information = fs::read_to_string(format!("/proc/self/fdinfo/{}", descriptor.as_raw_fd()))?;
    if information.lines().any(|line| {
        line.strip_prefix("Pid:")
            .and_then(|value| value.trim().parse::<u32>().ok())
            == Some(pid)
    }) {
        Ok(())
    } else {
        Err(invalid())
    }
}

/// 保持模板登记连接；丢弃时控制器撤销新恢复准入。
pub(super) struct Template {
    pub id: String,
    pub seed_worker: String,
    pub image: String,
    _connection: UnixStream,
}

impl Template {
    /// 只检查登记通道存活，不发送控制命令。@return 登记连接尚无EOF或错误。
    pub fn alive(&self) -> bool {
        let mut descriptor = libc::pollfd {
            fd: self._connection.as_raw_fd(),
            events: libc::POLLIN,
            revents: 0,
        };
        unsafe { libc::poll(&mut descriptor, 1, 0) == 0 }
    }

    /// 立即撤销登记通道；在途实例保留各自的物理退出句柄。@return 无。
    pub fn invalidate(&self) {
        // shutdown不依赖Arc引用计数，让并发持有旧模板的创建者也失去后续准入。
        unsafe {
            libc::shutdown(self._connection.as_raw_fd(), libc::SHUT_RDWR);
        }
    }

    /// 登记尚未执行业务的受限种子。@param key 完整池身份。@param id 模板UUID。@param worker 种子UUID。@param pid 实际PID。@param image 预期映像。@return 保持存活的登记租约。
    pub async fn register(
        key: &str,
        id: &str,
        worker: &str,
        pid: u32,
        image: &str,
    ) -> io::Result<Self> {
        let mut connection = connect().await?;
        send(
            &mut connection,
            &json!({"type":"template","key":key,"template":id,"worker":worker,"pid":pid}),
        )
        .await?;
        let ready = receive(&mut connection).await?;
        if ready != json!({"protocol":1,"type":"template_ready","template":id,"image":image}) {
            return Err(invalid());
        }
        Ok(Self {
            id: id.into(),
            seed_worker: worker.into(),
            image: image.into(),
            _connection: connection,
        })
    }
}

/// 恢复实例的控制连接与命名空间存活句柄；调用方负责等待后再释放物理许可。
pub(super) struct Process {
    connection: Option<UnixStream>,
    namespace: Option<AsyncFd<OwnedFd>>,
    worker: Option<OwnedFd>,
    pub pid: Option<u32>,
    pub inner_pid: Option<u32>,
}

impl Process {
    #[cfg(test)]
    /// 构造真实pidfd清理夹具。@param connection 测试控制连接。@param descriptor 实际子进程pidfd。@return 取消守卫使用的进程句柄。
    pub(super) fn test_namespace(connection: UnixStream, descriptor: OwnedFd) -> Self {
        Self {
            connection: Some(connection),
            namespace: Some(AsyncFd::new(descriptor).unwrap()),
            worker: None,
            pid: None,
            inner_pid: None,
        }
    }
    #[cfg(test)]
    /// 构造带真实worker存活证据的夹具。@param connection 测试控制连接。@param descriptor 实际worker的pidfd。@param pid 实际PID。@return 与清理句柄共同持有的worker状态。
    pub(super) fn test_worker(connection: UnixStream, descriptor: OwnedFd, pid: u32) -> Self {
        let worker = descriptor.try_clone().unwrap();
        let mut process = Self::test_namespace(connection, descriptor);
        process.worker = Some(worker);
        process.pid = Some(pid);
        process
    }
    /// 连接控制器，此时尚未创建物理worker。@return 可由取消守卫持有的空会话。
    pub async fn connect() -> io::Result<Self> {
        Ok(Self {
            connection: Some(connect().await?),
            namespace: None,
            worker: None,
            pid: None,
            inner_pid: None,
        })
    }

    /// 完成两阶段FD交接；ACK前先保存命名空间pidfd。@param template 有效模板。@param key 池身份。@param worker 新实例ID。@param nonce 新挑战。@return 私有输入输出管道。
    pub async fn start(
        &mut self,
        template: &Template,
        key: &str,
        worker: &str,
        nonce: &str,
    ) -> io::Result<(ChildStdin, ChildStdout)> {
        let connection = self.connection.as_mut().ok_or_else(invalid)?;
        send(connection, &json!({"type":"restore","key":key,"template":template.id,"worker":worker,"nonce":nonce})).await?;
        let mut namespace = receive_fds(connection, 1).await?;
        // 保存FD与ACK之间没有await；取消守卫从此持有完整物理退出证据。
        self.namespace = Some(AsyncFd::new(namespace.pop().ok_or_else(invalid)?)?);
        let ready = receive(connection).await?;
        let namespace_pid = ready["pid"]
            .as_u64()
            .and_then(|pid| u32::try_from(pid).ok())
            .ok_or_else(invalid)?;
        pidfd_matches(
            self.namespace.as_ref().ok_or_else(invalid)?.get_ref(),
            namespace_pid,
        )?;
        if ready["protocol"] != 1 || ready["type"] != "namespace_ready" {
            return Err(invalid());
        }
        send(connection, &json!({"type":"start"})).await?;
        let mut descriptors = receive_fds(connection, 3).await?;
        let worker_fd = descriptors.pop().ok_or_else(invalid)?;
        let output = descriptors.pop().ok_or_else(invalid)?;
        let input = descriptors.pop().ok_or_else(invalid)?;
        let ready = receive(connection).await?;
        let pid = ready["pid"]
            .as_u64()
            .and_then(|pid| u32::try_from(pid).ok())
            .ok_or_else(invalid)?;
        let inner = ready["inner_pid"]
            .as_u64()
            .and_then(|pid| u32::try_from(pid).ok())
            .ok_or_else(invalid)?;
        pidfd_matches(&worker_fd, pid)?;
        if ready["protocol"] != 1
            || ready["type"] != "restore_ready"
            || ready["parent"] != namespace_pid
            || ready["template"] != template.id
            || ready["seed_worker"] != template.seed_worker
            || ready["worker"] != worker
            || ready["nonce"] != nonce
            || ready["image"] != template.image
            || ready["entropy_profile"] != ENTROPY_PROFILE
        {
            return Err(invalid());
        }
        let status = fs::read_to_string(format!("/proc/{pid}/status"))?;
        if !status
            .lines()
            .any(|line| line == format!("PPid:\t{namespace_pid}"))
            || !status.lines().any(|line| {
                line.strip_prefix("NSpid:")
                    .and_then(|values| values.split_whitespace().last())
                    == Some(inner.to_string().as_str())
            })
        {
            return Err(invalid());
        }
        self.pid = Some(pid);
        self.inner_pid = Some(inner);
        self.worker = Some(worker_fd);
        Ok((
            ChildStdin::from_std(input.into())?,
            ChildStdout::from_std(output.into())?,
        ))
    }

    /// 判断实际worker是否仍存活。@return pidfd尚未可读为真。
    pub fn alive(&self) -> bool {
        self.worker.as_ref().is_some_and(|fd| {
            let mut poll = libc::pollfd {
                fd: fd.as_raw_fd(),
                events: libc::POLLIN,
                revents: 0,
            };
            unsafe { libc::poll(&mut poll, 1, 0) == 0 }
        })
    }

    /// 关闭控制连接并等命名空间实际退出。@return 无。
    pub async fn retire(mut self) {
        self.connection.take();
        if let Some(namespace) = self.namespace.take() {
            let _ = namespace.readable().await;
        }
    }
}

/// 生成恢复绑定的系统随机挑战。@return 64位十六进制字符串。
pub(super) fn nonce() -> String {
    format!("{}{}", Uuid::new_v4().simple(), Uuid::new_v4().simple())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Read;
    use std::os::unix::net::UnixStream as StdStream;

    /// 登记通道关闭后立刻撤销模板就绪状态。@return 无。
    #[tokio::test]
    async fn native_criu_template_status_tracks_registration_disconnect() {
        let (connection, controller) = UnixStream::pair().unwrap();
        let template = Template {
            id: String::new(),
            seed_worker: String::new(),
            image: String::new(),
            _connection: connection,
        };
        assert!(template.alive());
        drop(controller);
        assert!(!template.alive());
    }

    fn handoff(connection: &StdStream, descriptors: &[i32]) {
        let mut marker = b'F';
        let mut vector = libc::iovec {
            iov_base: (&mut marker as *mut u8).cast(),
            iov_len: 1,
        };
        let mut control = [0usize; 16];
        let mut message: libc::msghdr = unsafe { zeroed() };
        message.msg_iov = &mut vector;
        message.msg_iovlen = 1;
        message.msg_control = control.as_mut_ptr().cast();
        message.msg_controllen =
            unsafe { libc::CMSG_SPACE(std::mem::size_of_val(descriptors) as u32) as usize };
        unsafe {
            let header = CMSG_FIRSTHDR(&message);
            (*header).cmsg_level = libc::SOL_SOCKET;
            (*header).cmsg_type = libc::SCM_RIGHTS;
            (*header).cmsg_len = CMSG_LEN(std::mem::size_of_val(descriptors) as u32) as usize;
            std::ptr::copy_nonoverlapping(
                descriptors.as_ptr(),
                CMSG_DATA(header).cast::<i32>(),
                descriptors.len(),
            );
            assert_eq!(
                libc::sendmsg(connection.as_raw_fd(), &message, libc::MSG_NOSIGNAL),
                1
            );
        }
    }

    #[tokio::test]
    async fn native_criu_rejects_extra_descriptors_and_closes_every_received_copy() {
        let (sender, receiver) = StdStream::pair().unwrap();
        receiver.set_nonblocking(true).unwrap();
        let receiver = UnixStream::from_std(receiver).unwrap();
        let mut pipe = [0; 2];
        assert_eq!(
            unsafe { libc::pipe2(pipe.as_mut_ptr(), libc::O_CLOEXEC) },
            0
        );
        let mut read = unsafe { fs::File::from_raw_fd(pipe[0]) };
        let write = unsafe { OwnedFd::from_raw_fd(pipe[1]) };
        handoff(&sender, &[write.as_raw_fd(), write.as_raw_fd()]);
        assert!(receive_fds(&receiver, 1).await.is_err());
        drop(write);
        // 任何被拒绝的写FD副本泄漏都会使此读取阻塞。
        let mut poll = libc::pollfd {
            fd: read.as_raw_fd(),
            events: libc::POLLIN,
            revents: 0,
        };
        assert_eq!(unsafe { libc::poll(&mut poll, 1, 100) }, 1);
        assert_eq!(read.read(&mut [0u8; 1]).unwrap(), 0);
    }

    #[tokio::test]
    async fn native_criu_handoff_keeps_cloexec_and_exact_pidfd_identity() {
        let (sender, receiver) = StdStream::pair().unwrap();
        receiver.set_nonblocking(true).unwrap();
        let receiver = UnixStream::from_std(receiver).unwrap();
        let raw = unsafe { libc::syscall(libc::SYS_pidfd_open, std::process::id(), 0) } as i32;
        assert!(raw >= 0);
        let original = unsafe { OwnedFd::from_raw_fd(raw) };
        handoff(&sender, &[original.as_raw_fd()]);
        let mut received = receive_fds(&receiver, 1).await.unwrap();
        let descriptor = received.pop().unwrap();
        assert_ne!(
            unsafe { libc::fcntl(descriptor.as_raw_fd(), libc::F_GETFD) } & libc::FD_CLOEXEC,
            0
        );
        assert!(pidfd_matches(&descriptor, std::process::id()).is_ok());
        assert!(pidfd_matches(&descriptor, std::process::id() + 1).is_err());
        assert!(
            pidfd_matches(
                &fs::File::open("/dev/null").unwrap().into(),
                std::process::id()
            )
            .is_err()
        );
    }
}
