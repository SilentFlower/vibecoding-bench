#define _GNU_SOURCE
#include <fcntl.h>
#include <linux/filter.h>
#include <linux/seccomp.h>
#include <sched.h>
#include <signal.h>
#include <stdlib.h>
#include <string.h>
#include <sys/prctl.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <sys/syscall.h>
#include <poll.h>
#include <stdio.h>
#include <limits.h>
#include <unistd.h>

/** 安装构建时冻结的业务过滤器。@return 成功0，失败111。 */
static int business_filter(void) {
    int descriptor = open("/opt/ccrb-criu/business-seccomp.bpf", O_RDONLY | O_NOFOLLOW | O_CLOEXEC);
    struct stat info;
    if (descriptor < 0 || fstat(descriptor, &info) || info.st_uid || (info.st_mode & 022)
            || info.st_size <= 0 || info.st_size > 32768 || info.st_size % sizeof(struct sock_filter)) return 111;
    struct sock_filter instructions[4096];
    size_t used = 0;
    while (used < (size_t)info.st_size) {
        ssize_t count = read(descriptor, (char *)instructions + used, info.st_size - used);
        if (count <= 0) return 111;
        used += count;
    }
    close(descriptor);
    struct sock_fprog filter = {(unsigned short)(used / sizeof(struct sock_filter)), instructions};
    if (prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0)
            || prctl(PR_SET_SECCOMP, SECCOMP_MODE_FILTER, &filter)) return 111;
    return 0;
}

/** 启动固定sender或独立恢复命名空间。@param argc 固定参数数量。@param argv 可信控制器生成的角色及内部FD。@return 角色退出码。 */
int main(int argc, char **argv) {
    if (getuid() || geteuid() || argc < 2) return 111;
    pid_t parent = getppid();
    if (prctl(PR_SET_PDEATHSIG, SIGKILL) || getppid() != parent) return 111;
    if (argc == 2 && !strcmp(argv[1], "sender")) {
        if (business_filter()) return 111;
        execl("/opt/ccrb-tls-observer/launch", "launch", "sender", NULL);
        return 111;
    }
    if (argc != 9 || strcmp(argv[1], "namespace") || strlen(argv[2]) != 36
            || strspn(argv[2], "0123456789abcdef-") != 36) return 111;
    int descriptors[6];
    for (int index = 3; index < argc; index++) {
        const char *token = argv[index];
        int descriptor = 0;
        if (!*token) return 111;
        /* 启动前核对全部句柄，避免格式错误发生在创建命名空间之后。 */
        while (*token) {
            if (*token < '0' || *token > '9' || descriptor > (INT_MAX - (*token - '0')) / 10) return 111;
            descriptor = descriptor * 10 + (*token++ - '0');
        }
        if (descriptor < 3 || fcntl(descriptor, F_GETFD) < 0) return 111;
        for (int previous = 3; previous < index; previous++) {
            if (descriptors[previous - 3] == descriptor) return 111;
        }
        descriptors[index - 3] = descriptor;
    }
    int parent_fd = syscall(SYS_pidfd_open, getpid(), 0);
    if (parent_fd < 0 || unshare(CLONE_NEWNS | CLONE_NEWPID)) return 111;
    pid_t child = fork();
    if (child < 0) return 111;
    if (!child) {
        struct pollfd alive = {parent_fd, POLLIN, 0};
        if (prctl(PR_SET_PDEATHSIG, SIGKILL) || poll(&alive, 1, 0) != 0) return 111;
        close(parent_fd);
        char *arguments[] = {"python3", "-E", "-s", "/opt/ccrb-criu/supervisor.py",
            argv[2], argv[3], argv[4], argv[5], argv[6], argv[7], argv[8], NULL};
        execv("/usr/local/bin/python3", arguments);
        return 111;
    }
    close(parent_fd);
    printf("%d\n", child);
    fflush(stdout);
    close(STDOUT_FILENO);
    for (int index = 3; index < argc; index++) {
        close(descriptors[index - 3]);
    }
    int status;
    if (waitpid(child, &status, 0) != child) return 111;
    return WIFEXITED(status) ? WEXITSTATUS(status) : 111;
}
