/* 隔离容器中，仅暂停或拒绝账号发送器的快照目录 chmod。 */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

static void record_event(const char *directory, const char *event)
{
    char path[4096];
    snprintf(path, sizeof(path), "%s/events", directory);
    int fd = open(path, O_WRONLY | O_CREAT | O_APPEND | O_CLOEXEC, 0644);
    if (fd >= 0) {
        struct timespec now;
        if (clock_gettime(CLOCK_MONOTONIC, &now) == 0)
            dprintf(fd, "%s %lld\n", event, now.tv_sec * 1000000000LL + now.tv_nsec);
        close(fd);
    }
}

/* 在快照锁已经持有时暂停写入。@param path 路径。@param mode 权限。@return libc 结果或注入错误。 */
int chmod(const char *path, mode_t mode)
{
    int (*real_chmod)(const char *, mode_t) = dlsym(RTLD_NEXT, "chmod");
    const char *directory = getenv("FLOWER_CAPTURE_PROBE_DIR");
    const char *test = getenv("FLOWER_CAPTURE_PROBE_CASE");
    if (!directory || !test || strcmp(path, "/flows/api/cc-prepared") != 0)
        return real_chmod(path, mode);

    record_event(directory, "entered");
    if (strcmp(test, "failed") == 0) {
        record_event(directory, "failed");
        errno = EACCES;
        return -1;
    }

    char release[4096];
    snprintf(release, sizeof(release), "%s/release", directory);
    const struct timespec step = {0, 20 * 1000 * 1000};
    for (int i = 0; i < 3000; ++i) {
        if (access(release, F_OK) == 0) {
            record_event(directory, "released");
            return real_chmod(path, mode);
        }
        nanosleep(&step, NULL);
    }
    record_event(directory, "expired");
    errno = ETIMEDOUT;
    return -1;
}
