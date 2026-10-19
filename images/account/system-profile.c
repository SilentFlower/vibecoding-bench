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
static int computer_status;
static int (*next_open)(const char *, int, ...);
static int (*next_openat)(int, const char *, int, ...);
static FILE *(*next_fopen)(const char *, const char *);
static FILE *(*next_fopen64)(const char *, const char *);
static int (*next_open_2)(const char *, int);
static int (*next_open64_2)(const char *, int);
static int (*next_openat_2)(int, const char *, int);
static int (*next_openat64_2)(int, const char *, int);
static int (*next_stat)(const char *, struct stat *);
static int (*next_lstat)(const char *, struct stat *);
static int (*next_stat64)(const char *, struct stat64 *);
static int (*next_lstat64)(const char *, struct stat64 *);
static int (*next_fstatat)(int, const char *, struct stat *, int);
static int (*next_fstatat64)(int, const char *, struct stat64 *, int);
static int (*next_statx)(int, const char *, int, unsigned int, struct statx *);
static int (*next_access)(const char *, int);
static int (*next_faccessat)(int, const char *, int, int);
static int (*next_chdir)(const char *);
static int (*next_xstat)(int, const char *, struct stat *);
static int (*next_lxstat)(int, const char *, struct stat *);
static int (*next_xstat64)(int, const char *, struct stat64 *);
static int (*next_lxstat64)(int, const char *, struct stat64 *);

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
    if (count < 2 || count > (ssize_t)size || output[count - 1] != '\n') { errno = EIO; return false; }
    output[count - 1] = '\0';
    if (memchr(output, '\n', (size_t)count - 1) || memchr(output, '\0', (size_t)count - 1)) {
        errno = EIO;
        return false;
    }
    return true;
}

static void initialize_profile(void) {
    profile_valid = load_field(PROFILE_ROOT "kernel-release", kernel_release, sizeof(kernel_release))
        && load_field(PROFILE_ROOT "kernel-version", kernel_version, sizeof(kernel_version));
    char marker[8], field[256];
    if (!load_field(PROFILE_ROOT "computer-profile-version", marker, sizeof(marker))) {
        /* 旧 CPU 画像没有此标记；损坏或不可读的已发布标记不能退回宿主身份。 */
        computer_status = errno == ENOENT ? 0 : -1;
        return;
    }
    computer_status = !strcmp(marker, "1")
        && load_field(PROFILE_ROOT "dmi/sys_vendor", field, sizeof(field))
        && load_field(PROFILE_ROOT "dmi/product_name", field, sizeof(field))
        && load_field(PROFILE_ROOT "dmi/product_version", field, sizeof(field))
        && load_field(PROFILE_ROOT "dmi/product_family", field, sizeof(field))
        && load_field(PROFILE_ROOT "dmi/product_serial", field, sizeof(field))
        && load_field(PROFILE_ROOT "dmi/product_uuid", field, sizeof(field)) ? 1 : -1;
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
    *(void **)(&next_stat) = dlsym(RTLD_NEXT, "stat");
    *(void **)(&next_lstat) = dlsym(RTLD_NEXT, "lstat");
    *(void **)(&next_stat64) = dlsym(RTLD_NEXT, "stat64");
    *(void **)(&next_lstat64) = dlsym(RTLD_NEXT, "lstat64");
    *(void **)(&next_fstatat) = dlsym(RTLD_NEXT, "fstatat");
    *(void **)(&next_fstatat64) = dlsym(RTLD_NEXT, "fstatat64");
    *(void **)(&next_statx) = dlsym(RTLD_NEXT, "statx");
    *(void **)(&next_access) = dlsym(RTLD_NEXT, "access");
    *(void **)(&next_faccessat) = dlsym(RTLD_NEXT, "faccessat");
    *(void **)(&next_chdir) = dlsym(RTLD_NEXT, "chdir");
    *(void **)(&next_xstat) = dlsym(RTLD_NEXT, "__xstat");
    *(void **)(&next_lxstat) = dlsym(RTLD_NEXT, "__lxstat");
    *(void **)(&next_xstat64) = dlsym(RTLD_NEXT, "__xstat64");
    *(void **)(&next_lxstat64) = dlsym(RTLD_NEXT, "__lxstat64");
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

static const char *dmi_target(const char *absolute) {
    const char *prefixes[] = {"/sys/class/dmi/id", "/sys/devices/virtual/dmi/id"};
    const char *fields[] = {"sys_vendor", "product_name", "product_version", "product_family", "product_serial", "product_uuid"};
    const char *targets[] = {PROFILE_ROOT "dmi/sys_vendor", PROFILE_ROOT "dmi/product_name",
        PROFILE_ROOT "dmi/product_version", PROFILE_ROOT "dmi/product_family",
        PROFILE_ROOT "dmi/product_serial", PROFILE_ROOT "dmi/product_uuid"};
    for (size_t index = 0; index < sizeof(prefixes) / sizeof(prefixes[0]); index++) {
        size_t length = strlen(prefixes[index]);
        if (!strcmp(absolute, prefixes[index])) return PROFILE_ROOT "dmi";
        if (strncmp(absolute, prefixes[index], length) || absolute[length] != '/') continue;
        for (size_t field = 0; field < sizeof(fields) / sizeof(fields[0]); field++) {
            if (!strcmp(absolute + length + 1, fields[field])) return targets[field];
        }
    }
    return NULL;
}

static const char *redirect_path(int directory, const char *path) {
    if (!path || !path[0]) return path;
    int saved_errno = errno;
    char absolute[PATH_MAX];
    const char *target = path;
    if (absolute_path(directory, path, absolute)) {
        if (!strcmp(absolute, "/proc/sys/kernel/osrelease")) target = PROFILE_ROOT "kernel-release";
        else if (!strcmp(absolute, "/proc/sys/kernel/version")) target = PROFILE_ROOT "kernel-version";
        else if (!strcmp(absolute, "/proc/version")) target = PROFILE_ROOT "proc-version";
        else {
            const char *dmi = dmi_target(absolute);
            if (dmi) {
                pthread_once(&profile_once, initialize_profile);
                if (computer_status < 0) { errno = EIO; return NULL; }
                if (computer_status > 0) target = dmi;
            }
        }
    }
    errno = saved_errno;
    if (target != path) {
        pthread_once(&profile_once, initialize_profile);
        if (!profile_valid) { errno = EIO; return NULL; }
    }
    return target;
}

static bool read_only(int flags) {
    /* O_TMPFILE 包含 O_DIRECTORY 位，不能把普通只读目录也误判为写入。 */
    return (flags & O_ACCMODE) == O_RDONLY && !(flags & (O_CREAT | O_TRUNC))
        && (flags & O_TMPFILE) != O_TMPFILE;
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

/* 元数据与内容共用白名单；否则先检查可读性的客户端会把有效字段当作不存在。 */
static bool metadata_path(int directory, const char *path, const char **target) {
    int saved_errno = errno;
    pthread_once(&symbols_once, initialize_symbols);
    errno = saved_errno;
    *target = redirect_path(directory, path);
    return !path || *target;
}

static int unavailable(void) { errno = ENOSYS; return -1; }

/** 读取受支持路径的元数据。
 * @param path 文件路径。
 * @param value 元数据输出。
 * @return 成功为 0，失败为 -1。
 */
int stat(const char *path, struct stat *value) {
    const char *target;
    if (!metadata_path(AT_FDCWD, path, &target)) return -1;
    return next_stat ? next_stat(target, value) : unavailable();
}

/** 读取不跟随最终符号链接的元数据。
 * @param path 文件路径。
 * @param value 元数据输出。
 * @return 成功为 0，失败为 -1。
 */
int lstat(const char *path, struct stat *value) {
    const char *target;
    if (!metadata_path(AT_FDCWD, path, &target)) return -1;
    return next_lstat ? next_lstat(target, value) : unavailable();
}

/** 读取大文件元数据。
 * @param path 文件路径。
 * @param value 元数据输出。
 * @return 成功为 0，失败为 -1。
 */
int stat64(const char *path, struct stat64 *value) {
    const char *target;
    if (!metadata_path(AT_FDCWD, path, &target)) return -1;
    return next_stat64 ? next_stat64(target, value) : unavailable();
}

/** 读取不跟随最终链接的大文件元数据。
 * @param path 文件路径。
 * @param value 元数据输出。
 * @return 成功为 0，失败为 -1。
 */
int lstat64(const char *path, struct stat64 *value) {
    const char *target;
    if (!metadata_path(AT_FDCWD, path, &target)) return -1;
    return next_lstat64 ? next_lstat64(target, value) : unavailable();
}

/** 读取相对目录描述符的元数据。
 * @param directory 目录描述符或 AT_FDCWD。
 * @param path 文件路径。
 * @param value 元数据输出。
 * @param flags 原有解析标志。
 * @return 成功为 0，失败为 -1。
 */
int fstatat(int directory, const char *path, struct stat *value, int flags) {
    const char *target;
    if (!metadata_path(directory, path, &target)) return -1;
    return next_fstatat ? next_fstatat(directory, target, value, flags) : unavailable();
}

/** 读取相对目录描述符的大文件元数据。
 * @param directory 目录描述符或 AT_FDCWD。
 * @param path 文件路径。
 * @param value 元数据输出。
 * @param flags 原有解析标志。
 * @return 成功为 0，失败为 -1。
 */
int fstatat64(int directory, const char *path, struct stat64 *value, int flags) {
    const char *target;
    if (!metadata_path(directory, path, &target)) return -1;
    return next_fstatat64 ? next_fstatat64(directory, target, value, flags) : unavailable();
}

/** 保留 statx 掩码与标志并映射受支持路径。
 * @param directory 目录描述符或 AT_FDCWD。
 * @param path 文件路径。
 * @param flags 原有解析标志。
 * @param mask 请求的元数据掩码。
 * @param value 元数据输出。
 * @return 成功为 0，失败为 -1。
 */
int statx(int directory, const char *path, int flags, unsigned int mask, struct statx *value) {
    const char *target;
    if (!metadata_path(directory, path, &target)) return -1;
    return next_statx ? next_statx(directory, target, flags, mask, value) : unavailable();
}

/** 检查受支持路径的实际只读权限。
 * @param path 文件路径。
 * @param mode 标准 access 权限掩码。
 * @return 成功为 0，失败为 -1。
 */
int access(const char *path, int mode) {
    const char *target;
    if (!metadata_path(AT_FDCWD, path, &target)) return -1;
    return next_access ? next_access(target, mode) : unavailable();
}

/** 检查相对目录路径的权限，保留有效身份等标志。
 * @param directory 目录描述符或 AT_FDCWD。
 * @param path 文件路径。
 * @param mode 标准权限掩码。
 * @param flags 原有检查标志。
 * @return 成功为 0，失败为 -1。
 */
int faccessat(int directory, const char *path, int mode, int flags) {
    const char *target;
    if (!metadata_path(directory, path, &target)) return -1;
    return next_faccessat ? next_faccessat(directory, target, mode, flags) : unavailable();
}

/** 让已支持的 DMI 目录可用于后续相对读取。
 * @param path 目标目录。
 * @return 成功为 0，失败为 -1。
 */
int chdir(const char *path) {
    const char *target;
    if (!metadata_path(AT_FDCWD, path, &target)) return -1;
    return next_chdir ? next_chdir(target) : unavailable();
}

/** 保留旧 glibc 客户端的 stat ABI 版本。
 * @param version 原 ABI 版本。
 * @param path 文件路径。
 * @param value 元数据输出。
 * @return 成功为 0，失败为 -1。
 */
int __xstat(int version, const char *path, struct stat *value) {
    const char *target;
    if (!metadata_path(AT_FDCWD, path, &target)) return -1;
    return next_xstat ? next_xstat(version, target, value) : unavailable();
}

/** 保留旧 glibc 客户端的 lstat ABI 版本。
 * @param version 原 ABI 版本。
 * @param path 文件路径。
 * @param value 元数据输出。
 * @return 成功为 0，失败为 -1。
 */
int __lxstat(int version, const char *path, struct stat *value) {
    const char *target;
    if (!metadata_path(AT_FDCWD, path, &target)) return -1;
    return next_lxstat ? next_lxstat(version, target, value) : unavailable();
}

/** 支持 Node 等客户端使用的大文件旧 stat 入口。
 * @param version 原 ABI 版本。
 * @param path 文件路径。
 * @param value 元数据输出。
 * @return 成功为 0，失败为 -1。
 */
int __xstat64(int version, const char *path, struct stat64 *value) {
    const char *target;
    if (!metadata_path(AT_FDCWD, path, &target)) return -1;
    return next_xstat64 ? next_xstat64(version, target, value) : unavailable();
}

/** 支持大文件旧 lstat 入口。
 * @param version 原 ABI 版本。
 * @param path 文件路径。
 * @param value 元数据输出。
 * @return 成功为 0，失败为 -1。
 */
int __lxstat64(int version, const char *path, struct stat64 *value) {
    const char *target;
    if (!metadata_path(AT_FDCWD, path, &target)) return -1;
    return next_lxstat64 ? next_lxstat64(version, target, value) : unavailable();
}

#if defined(__x86_64__) && defined(SYS_statx)
/* Node/libuv 经 libc syscall 调 statx，绕过 stat 符号；仅此动态入口复用同一映射。 */
__attribute__((used, noinline))
static long profile_statx_syscall(long number, int directory, const char *path, int flags,
        unsigned int mask, struct statx *value) {
    (void)number;
    return statx(directory, path, flags, mask, value);
}

#define PROFILE_ASM_VALUE_INNER(value) #value
#define PROFILE_ASM_VALUE(value) PROFILE_ASM_VALUE_INNER(value)

/** 为动态客户端的 statx 调用保留同一画像，其余系统调用原样进入内核。
 * @param number Linux 系统调用号；后续参数保留调用方原有 ABI。
 * @return 原系统调用结果，失败时返回 -1 并设置 errno。
 */
__attribute__((naked))
long syscall(long number __attribute__((unused)), ...) {
    /* 汇编原样转交寄存器和第六参数，避免用 va_arg 读取调用方并未传入的参数。 */
    __asm__(
        "cmp $" PROFILE_ASM_VALUE(SYS_statx) ", %rdi\n"
        "je profile_statx_syscall\n"
        "mov %rdi, %rax\n"
        "mov %rsi, %rdi\n"
        "mov %rdx, %rsi\n"
        "mov %rcx, %rdx\n"
        "mov %r8, %r10\n"
        "mov %r9, %r8\n"
        "mov 8(%rsp), %r9\n"
        "syscall\n"
        "cmp $-4095, %rax\n"
        "jae .Lprofile_syscall_error\n"
        "ret\n"
        ".Lprofile_syscall_error:\n"
        "neg %eax\n"
        "push %rax\n"
        "call __errno_location@PLT\n"
        "pop %rdx\n"
        "mov %edx, (%rax)\n"
        "mov $-1, %rax\n"
        "ret\n"
    );
}
#endif
