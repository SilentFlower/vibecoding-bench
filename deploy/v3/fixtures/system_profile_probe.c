#define _GNU_SOURCE
#include <cpuid.h>
#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/syscall.h>
#include <sys/utsname.h>
#include <unistd.h>

static int check_fd(int descriptor, const char *expected) {
    if (descriptor < 0) return 1;
    char value[1024] = {0};
    ssize_t count = read(descriptor, value, sizeof(value) - 1);
    close(descriptor);
    return count < 0 || strcmp(value, expected);
}

static void *check_thread(void *unused) {
    (void)unused;
    for (int index = 0; index < 100; index++) {
        struct utsname value;
        errno = ENOTTY;
        if (uname(&value) || errno != ENOTTY) return (void *)1;
        char expected[128];
        snprintf(expected, sizeof(expected), "%s\n", value.release);
        if (check_fd(open("/proc/sys/kernel/osrelease", O_RDONLY), expected)) return (void *)1;
    }
    return NULL;
}

/** 比较动态接口、原始系统调用与 CPU 指令，并可验证常规文件接口。
 * @param argc 参数数量。
 * @param argv 传入 --files 时同时验证文件读取与线程初始化。
 * @return 成功为 0；任何不一致为非零。
 */
int main(int argc, char **argv) {
    struct utsname value, raw;
    char brand[49] = {0};
    unsigned int words[4];
    if (uname(&value) || syscall(SYS_uname, &raw)) return 2;
    for (unsigned int index = 0; index < 3; index++) {
        __cpuid(0x80000002 + index, words[0], words[1], words[2], words[3]);
        memcpy(brand + 16 * index, words, 16);
    }
    if (argc > 1 && !strcmp(argv[1], "--files")) {
        char expected[128];
        snprintf(expected, sizeof(expected), "%s\n", value.release);
        if (check_fd(open("/proc/sys/kernel/osrelease", O_RDONLY), expected)) return 3;
        if (check_fd(open64("/proc/sys/kernel/../kernel/osrelease", O_RDONLY), expected)) return 4;
        volatile int flags = O_RDONLY;
        if (check_fd(open("/proc/sys/kernel/osrelease", flags), expected)) return 14;
        if (check_fd(open64("/proc/sys/kernel/osrelease", flags), expected)) return 15;
        int directory = open("/proc/sys/kernel", O_RDONLY | O_DIRECTORY);
        if (directory < 0 || check_fd(openat(directory, "./osrelease", O_RDONLY), expected)) return 5;
        if (check_fd(openat64(directory, "../kernel/osrelease", O_RDONLY), expected)) return 6;
        if (check_fd(openat(directory, "osrelease", flags), expected)) return 16;
        if (check_fd(openat64(directory, "osrelease", flags), expected)) return 17;
        if (openat(directory, "", O_RDONLY) != -1 || errno != ENOENT) return 7;
        char *volatile missing = NULL;
        if (open(missing, O_RDONLY) != -1 || errno != EFAULT) return 18;
        close(directory);
        if (chdir("/proc/sys/kernel") || check_fd(open("./osrelease", O_RDONLY), expected)) return 8;
        for (int large = 0; large < 2; large++) {
            FILE *input = large ? fopen64("version", "re") : fopen("version", "r");
            char buffer[128] = {0};
            if (!input || !fgets(buffer, sizeof(buffer), input)) return 9;
            fclose(input);
            snprintf(expected, sizeof(expected), "%s\n", value.version);
            if (strcmp(buffer, expected)) return 10;
        }
        if (open("/proc/sys/kernel/osrelease", O_WRONLY) != -1) return 11;
        pthread_t threads[4];
        for (int index = 0; index < 4; index++) if (pthread_create(&threads[index], NULL, check_thread, NULL)) return 12;
        for (int index = 0; index < 4; index++) {
            void *result;
            if (pthread_join(threads[index], &result) || result) return 13;
        }
    }
    printf("{\"uname_release\":\"%s\",\"syscall_release\":\"%s\",\"cpuid_brand\":\"%s\"}\n",
        value.release, raw.release, brand);
    return 0;
}
