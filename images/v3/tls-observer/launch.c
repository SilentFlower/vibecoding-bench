#define _GNU_SOURCE
#include <linux/capability.h>
#include <sys/prctl.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <grp.h>
#include <poll.h>
#include <signal.h>
#include <limits.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

/** 将当前角色降到业务UID并约束父进程。@param observer 是否保留加载能力。@param parent 冻结父PID。@return 失败111。 */
static int enter_identity(int observer, pid_t parent) {
    if (prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) || prctl(PR_SET_KEEPCAPS, 1, 0, 0, 0)) return 111;
    if (setgroups(0, NULL) || setresgid(1001, 1001, 1001) || setresuid(1001, 1001, 1001)) return 111;
    struct __user_cap_header_struct header = {_LINUX_CAPABILITY_VERSION_3, 0};
    struct __user_cap_data_struct data[2] = {{0}};
    if (observer) data[0].effective = data[0].permitted = data[0].inheritable = 1U << CAP_SYS_ADMIN;
    if (syscall(SYS_capset, &header, data) || prctl(PR_CAP_AMBIENT, PR_CAP_AMBIENT_CLEAR_ALL, 0, 0, 0)) return 111;
    if (observer && prctl(PR_CAP_AMBIENT, PR_CAP_AMBIENT_RAISE, CAP_SYS_ADMIN, 0, 0)) return 111;
    if (prctl(PR_SET_PDEATHSIG, SIGKILL) || getppid() != parent) return 111;
    return 0;
}

/** 可信父进程派生固定角色并降权。@param argc 固定角色参数。@param argv 无任意程序路径。@return 失败111。 */
int main(int argc, char **argv) {
    if (getuid() != 0 || geteuid() != 0 || argc < 2) return 111;
    int observer = strcmp(argv[1], "observer") == 0;
    int stop = strcmp(argv[1], "stop") == 0;
    if ((observer && argc != 14) || (stop && argc != 3)
            || (!observer && !stop && (strcmp(argv[1], "sender") || argc != 2))) return 111;
    pid_t parent = getppid();
    if (observer) {
        pid_t supervisor = getpid();
        pid_t child = fork();
        if (child < 0) return 111;
        if (child > 0) {
            if (enter_identity(0, parent)) { kill(child, SIGKILL); return 111; }
            close(STDOUT_FILENO);
            struct pollfd input = {STDIN_FILENO, 0, 0};
            int status;
            /* 同UID监督进程只观察管道挂断，正文仍由Python独占读取；EOF无需新FD或额外权限。 */
            for (;;) {
                if (waitpid(child, &status, WNOHANG) == child)
                    return WIFEXITED(status) ? WEXITSTATUS(status) : 111;
                if (poll(&input, 1, 20) < 0 || input.revents) break;
            }
            kill(child, SIGKILL);
            for (int attempt = 0; attempt < 100; attempt++) {
                if (waitpid(child, &status, WNOHANG) == child) return 0;
                usleep(10000);
            }
            return 111;
        }
        parent = supervisor;
    }
    if (enter_identity(observer, parent)) return 111;
    if (stop) {
        char *end = NULL;
        long descriptor = strtol(argv[2], &end, 10);
        if (!end || *end || descriptor < 3 || descriptor > INT_MAX) return 111;
        return syscall(SYS_pidfd_send_signal, (int)descriptor, SIGKILL, NULL, 0) == 0 ? 0 : 111;
    } else if (!observer) {
        char *args[] = {"account-sender", NULL};
        execv("/usr/local/bin/account-sender", args);
    } else {
        /* 所有参数来自broker白名单；客户端没有传入程序、路径或权限集合的入口。 */
        char *args[] = {"python3", "-E", "-s", "/opt/ccrb-tls-observer/observer.py",
            argv[2], argv[3], argv[4], argv[5], argv[6], argv[7], argv[8], argv[9],
            argv[10], argv[11], argv[12], argv[13], NULL};
        execv("/usr/local/bin/python3", args);
    }
    return 111;
}
