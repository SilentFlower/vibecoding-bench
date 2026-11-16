#define _GNU_SOURCE
#include <fcntl.h>
#include <grp.h>
#include <linux/filter.h>
#include <linux/seccomp.h>
#include <stdlib.h>
#include <sys/prctl.h>
#include <sys/stat.h>
#include <unistd.h>

/** 以生产UID和固定过滤器启动研究进程。@param argc 参数数量。@param argv BPF文件及固定程序参数。@return 失败111。 */
int main(int argc, char **argv) {
    if (argc < 3) return 111;
    int fd = open(argv[1], O_RDONLY);
    struct stat info;
    if (fd < 0 || fstat(fd, &info) || info.st_size <= 0 || info.st_size > 32768
            || info.st_size % sizeof(struct sock_filter)) return 111;
    struct sock_filter *filter = malloc(info.st_size);
    if (!filter) return 111;
    size_t used = 0;
    while (used < (size_t)info.st_size) {
        ssize_t count = read(fd, (char *)filter + used, info.st_size - used);
        if (count <= 0) return 111;
        used += count;
    }
    close(fd);
    struct sock_fprog program = {(unsigned short)(used / sizeof(struct sock_filter)), filter};
    if (prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) || setgroups(0, NULL)
            || setgid(1001) || setuid(1001)
            || prctl(PR_SET_SECCOMP, SECCOMP_MODE_FILTER, &program)) return 111;
    execv(argv[2], argv + 2);
    return 111;
}
