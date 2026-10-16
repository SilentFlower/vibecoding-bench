#define _GNU_SOURCE
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <pthread.h>
#include <stdarg.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/utsname.h>
#include <unistd.h>

#define PROFILE_ROOT "/etc/v3-system-profile/"

static pthread_once_t profile_once = PTHREAD_ONCE_INIT;
static pthread_once_t symbols_once = PTHREAD_ONCE_INIT;
static char kernel_release[65];
static char kernel_version[65];
static bool profile_valid;
static int (*next_open)(const char *, int, ...);
static int (*next_openat)(int, const char *, int, ...);
static FILE *(*next_fopen)(const char *, const char *);
static FILE *(*next_fopen64)(const char *, const char *);
static int (*next_open_2)(const char *, int);
static int (*next_open64_2)(const char *, int);
static int (*next_openat_2)(int, const char *, int);
static int (*next_openat64_2)(int, const char *, int);

/* 直接读取固定只读文件，避免覆盖库初始化递归进入自己的 open hook。 */
static bool load_field(const char *path, char *output, size_t size) {
    int descriptor = (int)syscall(SYS_openat, AT_FDCWD, path, O_RDONLY | O_NOFOLLOW | O_CLOEXEC);
    if (descriptor < 0) return false;
    struct stat metadata;
    bool valid = syscall(SYS_fstat, descriptor, &metadata) == 0 && S_ISREG(metadata.st_mode)
        && metadata.st_uid == 0 && !(metadata.st_mode & 0222) && metadata.st_nlink == 1
        && metadata.st_size > 1 && metadata.st_size <= (off_t)size;
    ssize_t count = valid ? syscall(SYS_read, descriptor, output, size) : -1;
    syscall(SYS_close, descriptor);
    if (count < 2 || count > (ssize_t)size || output[count - 1] != '\n') return false;
    output[count - 1] = '\0';
    return !memchr(output, '\n', (size_t)count - 1) && !memchr(output, '\0', (size_t)count - 1);
}

static void initialize_profile(void) {
    profile_valid = load_field(PROFILE_ROOT "kernel-release", kernel_release, sizeof(kernel_release))
        && load_field(PROFILE_ROOT "kernel-version", kernel_version, sizeof(kernel_version));
}

static void initialize_symbols(void) {
    *(void **)(&next_open) = dlsym(RTLD_NEXT, "open");
    *(void **)(&next_openat) = dlsym(RTLD_NEXT, "openat");
    *(void **)(&next_fopen) = dlsym(RTLD_NEXT, "fopen");
    *(void **)(&next_fopen64) = dlsym(RTLD_NEXT, "fopen64");
    *(void **)(&next_open_2) = dlsym(RTLD_NEXT, "__open_2");
    *(void **)(&next_open64_2) = dlsym(RTLD_NEXT, "__open64_2");
    *(void **)(&next_openat_2) = dlsym(RTLD_NEXT, "__openat_2");
    *(void **)(&next_openat64_2) = dlsym(RTLD_NEXT, "__openat64_2");
}

/* 只做词法路径归一化；符号链接和显式 raw syscall 不属于该覆盖边界。 */
static bool absolute_path(int directory, const char *path, char *output) {
    char input[PATH_MAX];
    if (path[0] == '/') {
        if (strlen(path) >= sizeof(input)) return false;
        memcpy(input, path, strlen(path) + 1);
    } else {
        char base[PATH_MAX];
        if (directory == AT_FDCWD) {
            if (syscall(SYS_getcwd, base, sizeof(base)) < 0) return false;
        } else {
            char descriptor_path[64];
            snprintf(descriptor_path, sizeof(descriptor_path), "/proc/self/fd/%d", directory);
            ssize_t count = syscall(SYS_readlinkat, AT_FDCWD, descriptor_path, base, sizeof(base) - 1);
            if (count < 0) return false;
            base[count] = '\0';
        }
        if (snprintf(input, sizeof(input), "%s/%s", base, path) >= (int)sizeof(input)) return false;
    }
    size_t length = 1;
    output[0] = '/';
    for (char *cursor = input; *cursor;) {
        while (*cursor == '/') cursor++;
        char *part = cursor;
        while (*cursor && *cursor != '/') cursor++;
        size_t count = (size_t)(cursor - part);
        if (!count || (count == 1 && part[0] == '.')) continue;
        if (count == 2 && part[0] == '.' && part[1] == '.') {
            while (length > 1 && output[--length] != '/') {}
            continue;
        }
        if (length > 1) output[length++] = '/';
        if (length + count >= PATH_MAX) return false;
        memcpy(output + length, part, count);
        length += count;
    }
    output[length] = '\0';
    return true;
}

static const char *redirect_path(int directory, const char *path) {
    if (!path[0]) return path;
    int saved_errno = errno;
    char absolute[PATH_MAX];
    const char *target = path;
    if (absolute_path(directory, path, absolute)) {
        if (!strcmp(absolute, "/proc/sys/kernel/osrelease")) target = PROFILE_ROOT "kernel-release";
        else if (!strcmp(absolute, "/proc/sys/kernel/version")) target = PROFILE_ROOT "kernel-version";
        else if (!strcmp(absolute, "/proc/version")) target = PROFILE_ROOT "proc-version";
    }
    errno = saved_errno;
    if (target != path) {
        pthread_once(&profile_once, initialize_profile);
        if (!profile_valid) { errno = EIO; return NULL; }
    }
    return target;
}

static bool read_only(int flags) {
    return (flags & O_ACCMODE) == O_RDONLY && !(flags & (O_CREAT | O_TRUNC | O_TMPFILE));
}

/** 覆盖 libc uname 的内核字段，保留真实 hostname 和架构。
 * @param value 系统信息输出指针。
 * @return 成功为 0，失败为 -1 并设置 errno。
 */
int uname(struct utsname *value) {
    if (syscall(SYS_uname, value) < 0) return -1;
    int saved_errno = errno;
    pthread_once(&profile_once, initialize_profile);
    if (!profile_valid) { errno = EIO; return -1; }
    memcpy(value->release, kernel_release, strlen(kernel_release) + 1);
    memcpy(value->version, kernel_version, strlen(kernel_version) + 1);
    errno = saved_errno;
    return 0;
}

static int open_common(int directory, const char *path, int flags, mode_t mode, bool at) {
    int saved_errno = errno;
    pthread_once(&symbols_once, initialize_symbols);
    errno = saved_errno;
    if (!next_open || !next_openat) { errno = ENOSYS; return -1; }
    const char *target = path && read_only(flags) ? redirect_path(directory, path) : path;
    if (path && !target) return -1;
    return at ? next_openat(directory, target, flags, mode) : next_open(target, flags, mode);
}

/* mode 参数只在内核要求时取出；不能读取调用方没有传入的可变参数。 */
static bool needs_mode(int flags) {
    return (flags & O_CREAT) || (flags & O_TMPFILE) == O_TMPFILE;
}

/** 重定向受支持的只读 open 路径。
 * @param path 文件路径。
 * @param flags 标准打开标志；创建时第三参数为 mode。
 * @return 文件描述符，失败为 -1。
 */
int open(const char *path, int flags, ...) {
    va_list args;
    va_start(args, flags);
    mode_t mode = needs_mode(flags) ? va_arg(args, mode_t) : 0;
    va_end(args);
    return open_common(AT_FDCWD, path, flags, mode, false);
}

/** 覆盖大文件 open64，参数与 open 一致。
 * @param path 文件路径。
 * @param flags 标准打开标志。
 * @return 文件描述符，失败为 -1。
 */
int open64(const char *path, int flags, ...) {
    va_list args;
    va_start(args, flags);
    mode_t mode = needs_mode(flags) ? va_arg(args, mode_t) : 0;
    va_end(args);
    return open_common(AT_FDCWD, path, flags | O_LARGEFILE, mode, false);
}

/** 重定向相对目录 fd 的只读打开。
 * @param directory 目录描述符或 AT_FDCWD。
 * @param path 文件路径。
 * @param flags 标准打开标志。
 * @return 文件描述符，失败为 -1。
 */
int openat(int directory, const char *path, int flags, ...) {
    va_list args;
    va_start(args, flags);
    mode_t mode = needs_mode(flags) ? va_arg(args, mode_t) : 0;
    va_end(args);
    return open_common(directory, path, flags, mode, true);
}

/** 覆盖大文件 openat64，参数与 openat 一致。
 * @param directory 目录描述符或 AT_FDCWD。
 * @param path 文件路径。
 * @param flags 标准打开标志。
 * @return 文件描述符，失败为 -1。
 */
int openat64(int directory, const char *path, int flags, ...) {
    va_list args;
    va_start(args, flags);
    mode_t mode = needs_mode(flags) ? va_arg(args, mode_t) : 0;
    va_end(args);
    return open_common(directory, path, flags | O_LARGEFILE, mode, true);
}

static int fortified_open(int directory, const char *path, int flags, bool at, bool large) {
    if (needs_mode(flags)) {
        /* 缺失创建 mode 时仍由 libc 执行原有 fortify 拒绝，不能静默补 0。 */
        pthread_once(&symbols_once, initialize_symbols);
        if (at && large && next_openat64_2) return next_openat64_2(directory, path, flags);
        if (at && !large && next_openat_2) return next_openat_2(directory, path, flags);
        if (!at && large && next_open64_2) return next_open64_2(path, flags);
        if (!at && !large && next_open_2) return next_open_2(path, flags);
        errno = ENOSYS;
        return -1;
    }
    return open_common(directory, path, flags | (large ? O_LARGEFILE : 0), 0, at);
}

/** 支持编译器生成的 fortified open。
 * @param path 文件路径。
 * @param flags 标准打开标志。
 * @return 文件描述符，失败为 -1。
 */
int __open_2(const char *path, int flags) { return fortified_open(AT_FDCWD, path, flags, false, false); }

/** 支持编译器生成的 fortified open64。
 * @param path 文件路径。
 * @param flags 标准打开标志。
 * @return 文件描述符，失败为 -1。
 */
int __open64_2(const char *path, int flags) { return fortified_open(AT_FDCWD, path, flags, false, true); }

/** 支持编译器生成的 fortified openat。
 * @param directory 目录描述符或 AT_FDCWD。
 * @param path 文件路径。
 * @param flags 标准打开标志。
 * @return 文件描述符，失败为 -1。
 */
int __openat_2(int directory, const char *path, int flags) { return fortified_open(directory, path, flags, true, false); }

/** 支持编译器生成的 fortified openat64。
 * @param directory 目录描述符或 AT_FDCWD。
 * @param path 文件路径。
 * @param flags 标准打开标志。
 * @return 文件描述符，失败为 -1。
 */
int __openat64_2(int directory, const char *path, int flags) { return fortified_open(directory, path, flags, true, true); }

static FILE *fopen_common(const char *path, const char *mode, bool large) {
    int saved_errno = errno;
    pthread_once(&symbols_once, initialize_symbols);
    errno = saved_errno;
    FILE *(*original)(const char *, const char *) = large ? next_fopen64 : next_fopen;
    if (!original) { errno = ENOSYS; return NULL; }
    const char *target = path && mode && mode[0] == 'r' && !strchr(mode, '+') ? redirect_path(AT_FDCWD, path) : path;
    return path && !target ? NULL : original(target, mode);
}

/** 重定向只读标准流。
 * @param path 文件路径。
 * @param mode 标准 fopen 模式。
 * @return 文件流，失败为 NULL。
 */
FILE *fopen(const char *path, const char *mode) { return fopen_common(path, mode, false); }

/** 重定向只读大文件标准流。
 * @param path 文件路径。
 * @param mode 标准 fopen 模式。
 * @return 文件流，失败为 NULL。
 */
FILE *fopen64(const char *path, const char *mode) { return fopen_common(path, mode, true); }
