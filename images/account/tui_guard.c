/* 在 sender 的原有 Docker 限制内，仅向本轮官方进程开放其工作区和配置。 */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <linux/landlock.h>
#include <seccomp.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/prctl.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <unistd.h>

/* ABI 3 才限制既有文件截断。旧发行版头文件可能尚未命名此位。 */
#ifndef LANDLOCK_ACCESS_FS_TRUNCATE
#define LANDLOCK_ACCESS_FS_TRUNCATE (1ULL << 14)
#endif
#if defined(__x86_64__) && !defined(__NR_fchmodat2)
/* 固定 CLI 的 x86_64 内核 ABI；Bookworm 的头文件可能早于 fchmodat2。 */
#define __NR_fchmodat2 452
#endif
#define READ (LANDLOCK_ACCESS_FS_READ_FILE | LANDLOCK_ACCESS_FS_READ_DIR)
#define RUN  (READ | LANDLOCK_ACCESS_FS_EXECUTE)
#define EDIT (READ | LANDLOCK_ACCESS_FS_WRITE_FILE | LANDLOCK_ACCESS_FS_REMOVE_DIR | \
              LANDLOCK_ACCESS_FS_REMOVE_FILE | LANDLOCK_ACCESS_FS_MAKE_DIR | \
              LANDLOCK_ACCESS_FS_MAKE_REG | LANDLOCK_ACCESS_FS_MAKE_SYM | \
              LANDLOCK_ACCESS_FS_REFER | LANDLOCK_ACCESS_FS_TRUNCATE)

static void fail(const char *operation) {
    perror(operation);
    _exit(125);
}

static void permit(int rules, const char *path, uint64_t access, int optional) {
    struct stat st;
    struct landlock_path_beneath_attr rule = {0};
    rule.parent_fd = open(path, O_PATH | O_CLOEXEC);
    if (rule.parent_fd < 0) {
        if (optional && errno == ENOENT) return;
        fail("打开 TUI 隔离路径");
    }
    if (fstat(rule.parent_fd, &st) < 0) fail("检查 TUI 隔离路径");
    if (!S_ISDIR(st.st_mode))
        access &= LANDLOCK_ACCESS_FS_EXECUTE | LANDLOCK_ACCESS_FS_READ_FILE |
                  LANDLOCK_ACCESS_FS_WRITE_FILE | LANDLOCK_ACCESS_FS_TRUNCATE;
    rule.allowed_access = access;
    if (syscall(SYS_landlock_add_rule, rules, LANDLOCK_RULE_PATH_BENEATH, &rule, 0))
        fail("登记 TUI 隔离路径");
    close(rule.parent_fd);
}

static void check(int result) {
    if (result < 0) {
        errno = -result;
        fail("限制 TUI 同账号进程访问");
    }
}

static void abi2_file_policy(scmp_filter_ctx filter, uint32_t denied) {
    /* 路径截短必须先取得 Landlock 授权的可写描述符。内核在处理写式打开的截短前检查写权限。 */
    check(seccomp_rule_add(filter, denied, SCMP_SYS(truncate), 0));
#ifdef __NR_truncate64
    check(seccomp_rule_add(filter, denied, SCMP_SYS(truncate64), 0));
#endif
    /* seccomp 只能读取直接参数。通过 ENOSYS 保留运行库的常规打开回退。 */
    check(seccomp_rule_add(filter, SCMP_ACT_ERRNO(ENOSYS), SCMP_SYS(openat2), 0));
    const uint64_t mask = O_TRUNC | O_ACCMODE;
    const uint64_t non_writable[] = {O_RDONLY, O_ACCMODE};
    for (size_t i = 0; i < sizeof(non_writable) / sizeof(non_writable[0]); ++i) {
        const uint64_t flags = O_TRUNC | non_writable[i];
#ifdef __NR_open
        check(seccomp_rule_add(filter, denied, SCMP_SYS(open), 1, SCMP_A1(SCMP_CMP_MASKED_EQ, mask, flags)));
#endif
        check(seccomp_rule_add(filter, denied, SCMP_SYS(openat), 1, SCMP_A2(SCMP_CMP_MASKED_EQ, mask, flags)));
    }
}

static void private_process(int abi2) {
    scmp_filter_ctx filter = seccomp_init(SCMP_ACT_ALLOW);
    if (!filter) fail("创建 TUI 进程限制");
    const uint32_t denied = SCMP_ACT_ERRNO(EPERM);
    const int blocked[] = {
        SCMP_SYS(ptrace), SCMP_SYS(process_vm_readv), SCMP_SYS(process_vm_writev),
        SCMP_SYS(pidfd_open), SCMP_SYS(pidfd_getfd), SCMP_SYS(pidfd_send_signal),
        SCMP_SYS(rt_sigqueueinfo), SCMP_SYS(rt_tgsigqueueinfo), SCMP_SYS(tkill),
        SCMP_SYS(io_uring_setup), SCMP_SYS(io_uring_register), SCMP_SYS(io_uring_enter),
        /* Landlock 不管理路径元数据。保留 fchmod 给已获准打开的本会话输出文件。 */
        SCMP_SYS(chmod), SCMP_SYS(fchmodat), SCMP_SYS(chown), SCMP_SYS(lchown),
        SCMP_SYS(fchownat), SCMP_SYS(setxattr), SCMP_SYS(lsetxattr),
        SCMP_SYS(removexattr), SCMP_SYS(lremovexattr), SCMP_SYS(utime),
        SCMP_SYS(utimes), SCMP_SYS(utimensat), SCMP_SYS(futimesat)
    };
    for (size_t i = 0; i < sizeof(blocked) / sizeof(blocked[0]); ++i)
        check(seccomp_rule_add(filter, denied, blocked[i], 0));
#ifdef __NR_fchmodat2
    check(seccomp_rule_add(filter, denied, __NR_fchmodat2, 0));
#endif
    const unsigned int pid = getpid();
    check(seccomp_rule_add(filter, denied, SCMP_SYS(kill), 1, SCMP_A0(SCMP_CMP_NE, pid, 0)));
    check(seccomp_rule_add(filter, denied, SCMP_SYS(tgkill), 1, SCMP_A0(SCMP_CMP_NE, pid, 0)));
    /* 会话 Mod 用带随机令牌的 TCP 回环。Linux ABI 3 不限制连接其他同 UID 的 Unix socket。 */
    check(seccomp_rule_add(filter, denied, SCMP_SYS(socket), 1, SCMP_A0(SCMP_CMP_MASKED_EQ, UINT32_MAX, AF_UNIX)));
    check(seccomp_rule_add(filter, denied, SCMP_SYS(socketpair), 1, SCMP_A0(SCMP_CMP_MASKED_EQ, UINT32_MAX, AF_UNIX)));
    if (abi2) abi2_file_policy(filter, denied);
    check(seccomp_load(filter));
    seccomp_release(filter);
}

/** 限定子进程的文件和进程访问范围，然后执行受信程序。
 * @param argc 参数个数。@param argv 私有 HOME、Mod 目录、固定程序及其参数。
 * @return 成功交付给原版进程；系统不支持隔离时返回 125。
 */
int main(int argc, char **argv) {
    const long abi = syscall(SYS_landlock_create_ruleset, (struct landlock_ruleset_attr *)NULL,
                             (size_t)0, LANDLOCK_CREATE_RULESET_VERSION);
    if (abi < 2) return 125;
    const int abi2 = abi == 2;
    int probe = argc == 2 && !strcmp(argv[1], "--check");
    if (!probe && (argc < 4 || argv[1][0] != '/' || argv[2][0] != '/' || argv[3][0] != '/'))
        return 125;
    if (abi2 && !probe) {
        /* ABI 2 保留已授权描述符的 ftruncate。继承的三个标准描述符必须是发送器分配的终端。 */
        for (int fd = STDIN_FILENO; fd <= STDERR_FILENO; ++fd)
            if (!isatty(fd)) fail("核验 TUI 终端描述符");
    }
    struct landlock_ruleset_attr configuration = {.handled_access_fs = (1ULL << 15) - 1};
    if (abi2) configuration.handled_access_fs &= ~LANDLOCK_ACCESS_FS_TRUNCATE;
    const uint64_t edit = EDIT & configuration.handled_access_fs;
    int rules = syscall(SYS_landlock_create_ruleset, &configuration, sizeof(configuration), 0);
    if (rules < 0) fail("创建 TUI 文件隔离");
    if (prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0)) fail("锁定 TUI 权限");
    permit(rules, ".", edit, 0);
    if (probe) {
        if (syscall(SYS_landlock_restrict_self, rules, 0)) fail("核验 TUI 文件隔离");
        private_process(abi2);
        return 0;
    }
    permit(rules, argv[1], edit, 0);
    permit(rules, argv[2], READ, 0);
    permit(rules, argv[3], RUN, 0);
    /* 受信 PreToolUse 拒绝钩子通过 shell 内建 printf 返回决定。 */
    permit(rules, "/bin/sh", RUN, 0);
    permit(rules, "/bin/bash", RUN, 0);
    const char *libraries[] = {"/lib", "/lib64", "/usr/lib", "/usr/share/locale", "/usr/share/zoneinfo"};
    for (size_t i = 0; i < sizeof(libraries) / sizeof(libraries[0]); ++i)
        permit(rules, libraries[i], RUN, 1);
    const char *system[] = {"/etc/ld.so.cache", "/etc/hosts", "/etc/nsswitch.conf", "/etc/resolv.conf",
        "/etc/ssl/certs", "/etc/passwd", "/etc/group", "/etc/localtime", "/etc/os-release",
        "/proc/meminfo", "/proc/cpuinfo", "/proc/self/status", "/proc/self/stat", "/proc/self/maps",
        "/sys/devices/system/cpu", "/sys/fs/cgroup", "/dev/urandom", "/dev/random"};
    for (size_t i = 0; i < sizeof(system) / sizeof(system[0]); ++i)
        permit(rules, system[i], READ, 1);
    permit(rules, "/dev/null", LANDLOCK_ACCESS_FS_READ_FILE | LANDLOCK_ACCESS_FS_WRITE_FILE, 0);
    permit(rules, "/dev/tty", LANDLOCK_ACCESS_FS_READ_FILE | LANDLOCK_ACCESS_FS_WRITE_FILE, 0);
    if (syscall(SYS_landlock_restrict_self, rules, 0)) fail("启用 TUI 文件隔离");
    /* 原版程序用已核验的 FD 执行，exec 成功时一并关闭它和工作目录描述符。 */
    if (close_range(3, ~0U, CLOSE_RANGE_CLOEXEC)) fail("关闭 TUI 继承描述符");
    private_process(abi2);
    execv(argv[3], argv + 3);
    fail("启动官方交互 CLI");
}
