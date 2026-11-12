#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>
#include "7z.h"
#include "7zAlloc.h"
#include "7zCrc.h"
#include "Sha256.h"
#include "payload-meta.h"

#ifndef MFD_EXEC
#define MFD_EXEC 0x0010U
#endif

extern const unsigned char ccrb_payload_start[];
extern const unsigned char ccrb_payload_end[];
extern char **environ;

/** 直接读取内嵌归档，加载期间不创建磁盘展开文件。 */
typedef struct {
    ILookInStream interface;
    const Byte *data;
    size_t size;
    size_t position;
} MemoryArchive;

static MemoryArchive *archive_state(ILookInStreamPtr value) {
    return (MemoryArchive *)(void *)value;
}

static SRes archive_look(ILookInStreamPtr value, const void **buffer, size_t *size) {
    MemoryArchive *archive = archive_state(value);
    size_t remaining = archive->size - archive->position;
    if (*size > remaining) *size = remaining;
    *buffer = archive->data + archive->position;
    return SZ_OK;
}

static SRes archive_skip(ILookInStreamPtr value, size_t size) {
    MemoryArchive *archive = archive_state(value);
    if (size > archive->size - archive->position) return SZ_ERROR_INPUT_EOF;
    archive->position += size;
    return SZ_OK;
}

static SRes archive_read(ILookInStreamPtr value, void *buffer, size_t *size) {
    const void *source;
    SRes result = archive_look(value, &source, size);
    if (result != SZ_OK) return result;
    memcpy(buffer, source, *size);
    return archive_skip(value, *size);
}

static SRes archive_seek(ILookInStreamPtr value, Int64 *position, ESzSeek origin) {
    MemoryArchive *archive = archive_state(value);
    Int64 base;
    if (origin == SZ_SEEK_SET) base = 0;
    else if (origin == SZ_SEEK_CUR) base = (Int64)archive->position;
    else if (origin == SZ_SEEK_END) base = (Int64)archive->size;
    else return SZ_ERROR_FAIL;
    if (*position < -base || *position > (Int64)archive->size - base) return SZ_ERROR_INPUT_EOF;
    *position += base;
    archive->position = (size_t)*position;
    return SZ_OK;
}

/** 校验、解包并原位执行固定原生载荷。
 * @param argc 原始参数个数。
 * @param argv 保留给原生工作进程的参数。
 * @return 仅在加载失败时返回非零；成功后由同一进程执行原生程序。
 */
int main(int argc, char **argv) {
    (void)argc;
    static const ISzAlloc allocator = { SzAlloc, SzFree };
    MemoryArchive archive = {
        { archive_look, archive_skip, archive_read, archive_seek },
        ccrb_payload_start,
        (size_t)((uintptr_t)ccrb_payload_end - (uintptr_t)ccrb_payload_start),
        0
    };
    CSzArEx database;
    Byte *buffer = NULL;
    size_t buffer_size = 0, offset = 0, output_size = 0;
    UInt32 block = UINT32_MAX;
    int result = 111, descriptor = -1;
    CrcGenerateTable();
    Sha256Prepare();
    SzArEx_Init(&database);
    if (SzArEx_Open(&database, &archive.interface, &allocator, &allocator) != SZ_OK) goto cleanup;
    if (database.NumFiles != 1 || SzArEx_IsDir(&database, 0) || SzArEx_GetFileSize(&database, 0) != CCRB_IMAGE_BYTES) goto cleanup;
    if (SzArEx_Extract(&database, &archive.interface, 0, &block, &buffer, &buffer_size, &offset, &output_size, &allocator, &allocator) != SZ_OK) goto cleanup;
    if (output_size != CCRB_IMAGE_BYTES || offset > buffer_size || output_size > buffer_size - offset) goto cleanup;
    CSha256 hash;
    Byte digest[SHA256_DIGEST_SIZE];
    Sha256_Init(&hash);
    Sha256_Update(&hash, buffer + offset, output_size);
    Sha256_Final(&hash, digest);
    if (memcmp(digest, ccrb_image_sha256, sizeof(digest)) != 0) goto cleanup;
    descriptor = memfd_create("ccrb-native-runtime", MFD_CLOEXEC | MFD_ALLOW_SEALING | MFD_EXEC);
    if (descriptor < 0 && errno == EINVAL) descriptor = memfd_create("ccrb-native-runtime", MFD_CLOEXEC | MFD_ALLOW_SEALING);
    if (descriptor < 0) goto cleanup;
    size_t written = 0;
    while (written < output_size) {
        ssize_t amount = write(descriptor, buffer + offset + written, output_size - written);
        if (amount < 0 && errno == EINTR) continue;
        if (amount <= 0) goto cleanup;
        written += (size_t)amount;
    }
    if (fchmod(descriptor, 0700) != 0 || fcntl(descriptor, F_ADD_SEALS, F_SEAL_WRITE | F_SEAL_SHRINK | F_SEAL_GROW | F_SEAL_SEAL) != 0) goto cleanup;
    // 先释放解压缓冲，再在同一 PID 执行封存载荷，避免常驻两份应用内存。
    ISzAlloc_Free(&allocator, buffer);
    buffer = NULL;
    SzArEx_Free(&database, &allocator);
    fexecve(descriptor, argv, environ);
    fputs("原生运行时执行失败\n", stderr);
    close(descriptor);
    return result;
cleanup:
    if (descriptor >= 0) close(descriptor);
    ISzAlloc_Free(&allocator, buffer);
    SzArEx_Free(&database, &allocator);
    fputs("原生运行时载荷校验或加载失败\n", stderr);
    return result;
}
