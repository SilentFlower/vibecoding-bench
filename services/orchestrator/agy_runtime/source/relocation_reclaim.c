#define _GNU_SOURCE
/* 固定映像只使用C99数字语法，保持Debian 12的解析ABI。 */
__asm__(".symver __isoc23_sscanf,__isoc99_sscanf@GLIBC_2.7");
__asm__(".symver __isoc23_strtol,strtol@GLIBC_2.2.5");
#include <errno.h>
#include <fcntl.h>
#include <link.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>

/* 固定 1.5.9 的真实区段范围由 elf-sections.json 提供。 */
#define SOURCE_BYTES 265700040
#define RELA_START 0xa180UL
#define RELA_BYTES 24657768UL


/**
 * 仅回收实验副本中重定位表的完整文件页，后续读取继续从原文件装页。
 * @param info 动态加载器提供的对象定义。
 * @param info_bytes 当前结构长度。
 * @param unused 保留回调参数。
 * @return 主执行对象返回一，其他对象返回零。
 */
static int reclaim_main(struct dl_phdr_info *info, size_t info_bytes, void *unused) {
    (void)info_bytes;
    (void)unused;
    if (info->dlpi_name != NULL && info->dlpi_name[0] != '\0') return 0;
    struct stat st;
    char path[4096];
    ssize_t path_bytes = readlink("/proc/self/exe", path, sizeof(path) - 1);
    if (path_bytes < 0) return 1;
    path[path_bytes] = '\0';
    const char *expected_path = getenv("AGY_RECLAIM_BINARY");
    if (expected_path == NULL) return 1;
    int fd = open("/proc/self/exe", O_RDONLY | O_CLOEXEC);
    if (fd < 0) return 1;
    struct stat expected_stat;
    /* proc FD路径与memfd显示名不同，按背板身份核对。 */
    if (fstat(fd, &st) != 0 || stat(expected_path, &expected_stat) != 0 ||
        st.st_dev != expected_stat.st_dev || st.st_ino != expected_stat.st_ino || st.st_size != SOURCE_BYTES) {
        close(fd);
        return 1;
    }
    long page = sysconf(_SC_PAGESIZE);
    if (page <= 0) { close(fd); return 1; }
    uintptr_t first = (RELA_START + page - 1) / page * page;
    uintptr_t last = (RELA_START + RELA_BYTES) / page * page;
    size_t bytes = last - first;
    void *address = (void *)(info->dlpi_addr + first);
    size_t page_count = bytes / page;
    unsigned char *vector = calloc(page_count, 1);
    size_t before = 0, after = 0;
    if (vector && mincore(address, bytes, vector) == 0) {
        for (size_t i = 0; i < page_count; i++) before += vector[i] & 1;
    }
    /* 只对文件映射提建议，执行体和私有重定位结果继续保持原来的内容。 */
    int advice = madvise(address, bytes, MADV_DONTNEED);
    int advice_errno = advice == 0 ? 0 : errno;
    int cache_advice = 0;
    if (getenv("AGY_STUDY_FADVISE") != NULL) {
        cache_advice = posix_fadvise(fd, (off_t)first, (off_t)bytes, POSIX_FADV_DONTNEED);
    }
    if (vector && mincore(address, bytes, vector) == 0) {
        for (size_t i = 0; i < page_count; i++) after += vector[i] & 1;
    }
    dprintf(STDERR_FILENO, "{\"study\":\"rela_reclaim\",\"pid\":%d,\"bytes\":%zu,\"madvise\":%d,\"errno\":%d,\"fadvise\":%d,\"cached_pages_before\":%zu,\"cached_pages_after\":%zu}\n",
            getpid(), bytes, advice, advice_errno, cache_advice, before, after);
    free(vector);
    close(fd);
    return 1;
}

/**
 * 在共享库构造阶段提交实验进程的冷页回收建议。
 * @return 无返回值。
 */
__attribute__((constructor)) static void begin_reclaim(void) {
    dl_iterate_phdr(reclaim_main, NULL);
}
