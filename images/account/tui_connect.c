/* 固定 CLI 的 libc 连接入口。实际 TCP connect 只能由原会话的可信代理执行。 */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <netinet/in.h>
#include <poll.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/syscall.h>
#include <sys/time.h>
#include <unistd.h>

/* 与原事件源连接空闲预算一致。通常在一次本机 connect 中立即完成。 */
#define CONNECT_TIMEOUT_SECONDS 120
#define CONNECT_TIMEOUT_MS (CONNECT_TIMEOUT_SECONDS * 1000)

static int connect_loopback(int fd, const struct sockaddr_in *target) {
    int domain, type, protocol;
    socklen_t length = sizeof(int);
    if (getsockopt(fd, SOL_SOCKET, SO_DOMAIN, &domain, &length) < 0 || domain != AF_INET
        || getsockopt(fd, SOL_SOCKET, SO_TYPE, &type, &length) < 0 || type != SOCK_STREAM
        || getsockopt(fd, SOL_SOCKET, SO_PROTOCOL, &protocol, &length) < 0 || protocol != IPPROTO_TCP)
        return EPERM;
    int flags = fcntl(fd, F_GETFL);
    if (flags < 0) return errno;
    if (flags & O_NONBLOCK)
        return syscall(SYS_connect, fd, target, sizeof(*target)) < 0 ? errno : 0;
    if (fcntl(fd, F_SETFL, flags | O_NONBLOCK) < 0) return errno;
    int result = syscall(SYS_connect, fd, target, sizeof(*target)) < 0 ? errno : 0;
    if (result == EINPROGRESS) {
        struct pollfd pending = {.fd = fd, .events = POLLOUT};
        int ready = poll(&pending, 1, CONNECT_TIMEOUT_MS);
        if (ready < 0) result = errno;
        else if (!ready) result = ETIMEDOUT;
        else if (getsockopt(fd, SOL_SOCKET, SO_ERROR, &result, &length) < 0) result = errno;
    }
    if (fcntl(fd, F_SETFL, flags) < 0 && !result) result = errno;
    return result;
}

/** 在可信事件源线程内运行会话连接代理。@param channel 当前会话的可信 socket。
 * @param port 当前会话模型与 Mod 回调端口。@return 对端退出返回 0，通道出错返回 errno。
 */
int tui_run_loopback_broker(int channel, unsigned short port) {
    const struct sockaddr_in target = {
        .sin_family = AF_INET, .sin_addr.s_addr = htonl(INADDR_LOOPBACK), .sin_port = htons(port),
    };
    for (;;) {
        char request;
        int descriptors[2];
        union {
            struct cmsghdr alignment;
            char bytes[CMSG_SPACE(sizeof(descriptors))];
        } control = {0};
        struct iovec data = {&request, sizeof(request)};
        struct msghdr message = {
            .msg_iov = &data, .msg_iovlen = 1,
            .msg_control = control.bytes, .msg_controllen = sizeof(control.bytes),
        };
        ssize_t size = recvmsg(channel, &message, MSG_CMSG_CLOEXEC);
        if (size < 0 && errno == EINTR) continue;
        if (size < 0) return errno;
        const struct cmsghdr *header = CMSG_FIRSTHDR(&message);
        if (!header && size == 0) return 0;
        if (!header || header->cmsg_level != SOL_SOCKET || header->cmsg_type != SCM_RIGHTS) continue;
        size_t count = (header->cmsg_len - CMSG_LEN(0)) / sizeof(int);
        if (count > 2) return EPROTO;
        memcpy(descriptors, CMSG_DATA(header), count * sizeof(int));
        if (size == 1 && count == 2 && !(message.msg_flags & (MSG_TRUNC | MSG_CTRUNC))) {
            // 目标取自可信启动参数。CLI 传入的只有已创建的 socket 和独立应答通道。
            int result = connect_loopback(descriptors[0], &target);
            send(descriptors[1], &result, sizeof(result), MSG_NOSIGNAL | MSG_DONTWAIT);
        }
        for (size_t i = 0; i < count; ++i) close(descriptors[i]);
    }
}

/** 把当前回环连接交给可信代理。@param fd 原 TCP 描述符。@param addr 目标地址。
 * @param len 地址长度。@return 保留 connect 的返回值和 errno 约定。
 */
int connect(int fd, const struct sockaddr *addr, socklen_t len) {
    const char *channel = getenv("FLOWER_TUI_CONNECT_FD");
    const char *port = getenv("FLOWER_TUI_LOOPBACK_PORT");
    struct sockaddr_in target;
    if (!channel || !port || !addr || len != sizeof(target)) {
        errno = EPERM;
        return -1;
    }
    memcpy(&target, addr, sizeof(target));
    if (target.sin_family != AF_INET || target.sin_addr.s_addr != htonl(INADDR_LOOPBACK)
        || target.sin_port != htons((unsigned short)atoi(port))) {
        errno = EPERM;
        return -1;
    }
    int reply[2];
    if (socketpair(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC, 0, reply) < 0) return -1;
    const struct timeval timeout = {.tv_sec = CONNECT_TIMEOUT_SECONDS};
    if (setsockopt(reply[0], SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout)) < 0) {
        int error = errno;
        close(reply[0]);
        close(reply[1]);
        errno = error;
        return -1;
    }
    int descriptors[] = {fd, reply[1]};
    char request = 0;
    union {
        struct cmsghdr alignment;
        char bytes[CMSG_SPACE(sizeof(descriptors))];
    } control = {0};
    struct iovec data = {&request, sizeof(request)};
    struct msghdr message = {
        .msg_iov = &data, .msg_iovlen = 1,
        .msg_control = control.bytes, .msg_controllen = sizeof(control.bytes),
    };
    struct cmsghdr *header = CMSG_FIRSTHDR(&message);
    header->cmsg_level = SOL_SOCKET;
    header->cmsg_type = SCM_RIGHTS;
    header->cmsg_len = CMSG_LEN(sizeof(descriptors));
    memcpy(CMSG_DATA(header), descriptors, sizeof(descriptors));
    ssize_t sent = sendmsg(atoi(channel), &message, MSG_NOSIGNAL | MSG_DONTWAIT);
    int result = errno;
    close(reply[1]);
    if (sent == sizeof(request)) {
        // 每条连接独立应答，避免 CLI 的并发线程消费到其他连接的 errno。
        ssize_t received;
        do {
            received = recv(reply[0], &result, sizeof(result), MSG_WAITALL);
        } while (received < 0 && errno == EINTR);
        if (received != sizeof(result))
            result = received < 0 && (errno == EAGAIN || errno == EWOULDBLOCK) ? ETIMEDOUT : ECONNREFUSED;
    }
    close(reply[0]);
    if (!result) return 0;
    errno = result;
    return -1;
}
