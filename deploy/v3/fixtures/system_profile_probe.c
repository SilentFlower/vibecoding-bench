#define _GNU_SOURCE
#include <cpuid.h>
#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/syscall.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <sys/utsname.h>
#include <unistd.h>

static int check_fd(int descriptor, const char *expected) {
    if (descriptor < 0) return 1;
    char value[1024] = {0};
    ssize_t count = read(descriptor, value, sizeof(value) - 1);
    close(descriptor);
    return count < 0 || strcmp(value, expected);
}

/* 验证透传不读取不存在的可变参数，并保留六参数调用及 errno。 */
static int check_syscalls(void) {
    if (syscall(SYS_getpid) != getpid() || syscall(SYS_getuid) != getuid()) return 1;
    void *memory = (void *)syscall(SYS_mmap, NULL, 4096, PROT_READ | PROT_WRITE,
        MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (memory == MAP_FAILED) return 2;
    ((volatile char *)memory)[4095] = 42;
    if (((volatile char *)memory)[4095] != 42 || syscall(SYS_munmap, memory, 4096)) return 3;
    errno = 0;
    if (syscall(-1) != -1 || errno != ENOSYS) return 4;
    return 0;
}

static int check_dmi(void) {
    const char *directories[] = {"/sys/class/dmi/id", "/sys/devices/virtual/dmi/id"};
    const char *fields[] = {"sys_vendor", "product_name", "product_version", "product_family", "product_serial", "product_uuid"};
    for (size_t index = 0; index < sizeof(directories) / sizeof(directories[0]); index++) {
        for (size_t field = 0; field < sizeof(fields) / sizeof(fields[0]); field++) {
            char path[256], source[256], expected[256] = {0};
            snprintf(path, sizeof(path), "%s/%s", directories[index], fields[field]);
            snprintf(source, sizeof(source), "/etc/v3-system-profile/dmi/%s", fields[field]);
            FILE *input = fopen(source, "r");
            if (!input || !fgets(expected, sizeof(expected), input)) return 30;
            fclose(input);
            if (check_fd(open(path, O_RDONLY), expected)) return 31;
            struct stat value;
            struct stat64 large;
            struct statx extended;
            if (stat(path, &value) || lstat(path, &value) || !S_ISREG(value.st_mode)
                    || value.st_size != (off_t)strlen(expected)) return 32;
            if (stat64(path, &large) || lstat64(path, &large) || large.st_size != value.st_size) return 33;
            if (fstatat(AT_FDCWD, path, &value, 0)
                    || fstatat64(AT_FDCWD, path, &large, AT_SYMLINK_NOFOLLOW)) return 34;
            if (statx(AT_FDCWD, path, 0, STATX_BASIC_STATS, &extended)
                    || extended.stx_size != (unsigned long long)value.st_size) return 35;
            if (syscall(SYS_statx, AT_FDCWD, path, 0, STATX_BASIC_STATS, &extended)
                    || extended.stx_size != (unsigned long long)value.st_size) return 36;
            if (access(path, F_OK) || access(path, R_OK) || faccessat(AT_FDCWD, path, R_OK, AT_EACCESS)) return 37;
            if (access(path, W_OK) != -1 || open(path, O_WRONLY) != -1) return 38;
            int directory = open(directories[index], O_RDONLY | O_DIRECTORY);
            if (directory < 0 || check_fd(openat(directory, fields[field], O_RDONLY), expected)) return 39;
            if (fstatat(directory, fields[field], &value, 0)
                    || faccessat(directory, fields[field], R_OK, 0)) return 40;
            if (fstatat(directory, "", &value, AT_EMPTY_PATH) || !S_ISDIR(value.st_mode)) return 41;
            close(directory);
        }
        int previous = open(".", O_RDONLY | O_DIRECTORY);
        if (previous < 0 || chdir(directories[index]) || access("product_name", R_OK) || fchdir(previous)) return 42;
        close(previous);
    }
    struct stat missing;
    if (stat("/sys/class/dmi/id/unknown-field", &missing) != -1 || errno != ENOENT) return 43;
    return 0;
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
    if (check_syscalls()) return 20;
    for (unsigned int index = 0; index < 3; index++) {
        __cpuid(0x80000002 + index, words[0], words[1], words[2], words[3]);
        memcpy(brand + 16 * index, words, 16);
    }
    if (argc > 1 && !strcmp(argv[1], "--files")) {
        int dmi = check_dmi();
        if (dmi) return dmi;
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
