#define _GNU_SOURCE
/* 固定映像只使用C99数字语法，保持Debian 12的解析ABI。 */
__asm__(".symver __isoc23_sscanf,__isoc99_sscanf@GLIBC_2.7");
__asm__(".symver __isoc23_strtol,strtol@GLIBC_2.2.5");
#include <errno.h>
#include <dirent.h>
#include <fcntl.h>
#include <openssl/evp.h>
#include <signal.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/sysmacros.h>
#include <sys/prctl.h>
#include <sys/ptrace.h>
#include <sys/uio.h>
#include <sys/user.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>
#include "native_schema.h"

#define SOURCE_SHA "39816d49d5ab92229952987225c23ea3fed7580699dcb4a444e0388e0ac1ce43"
typedef struct { pid_t tid; int detach; } Task;
typedef struct { uint64_t g, request, depth, receive_stream, receive_depth, receive_epoch, receive_object, raw_g, raw_ptr, raw_size, raw_epoch; int raw_pending; int ended, receive_state, receive_result; char job[97], id[128]; } Call;
static Task tasks[4096];
static Call calls[128];
static FILE *events;
static pid_t root_pid;
static unsigned long image_base;
static const char *folder, *generation, *binary;
static char current_job[97], decode_error[128];
static unsigned call_number;
static unsigned diagnostic_pause_count;
static int capture_tls;
static pid_t controller_pid;
static volatile sig_atomic_t checkpoint_requested;
static const unsigned long tls_write_site = 0x73819bfUL;
static const unsigned char tls_write_signature[] = {0x48,0x8b,0x44,0x24,0x30,0x48,0x8b,0x5c,0x24,0x60,0x48,0x8b,0x4c,0x24,0x68,0xc9};
static const size_t tls_sample_limit = 32UL * 1024 * 1024;
static char tls_job[97];
static uint64_t tls_connection;
static uint64_t tls_write_progress;
static size_t tls_bytes;
typedef struct { Call *call; unsigned char *data; size_t size; } TlsSample;
#ifndef DIAG_PAUSE_US
#define DIAG_PAUSE_US 0
#endif

/** 以长度为界写入JSON字符串，保留原始UTF-8及控制字符。 */
static void json_string(FILE *out, const char *data, size_t size) {
    fputc('"', out);
    for (size_t i = 0; i < size; i++) {
        unsigned char c = (unsigned char)data[i];
        if (c == '"' || c == '\\') { fputc('\\', out); fputc(c, out); }
        else if (c < 32) fprintf(out, "\\u%04x", c);
        else fputc(c, out);
    }
    fputc('"', out);
}

/** 从暂停的业务线程复制已声明范围，采集失败保持可见。 */
static int remote(pid_t tid, uint64_t address, void *buffer, size_t size) {
    struct iovec local = {buffer, size}, target = {(void *)(uintptr_t)address, size};
    if (size == 0) return 1;
    ssize_t count = process_vm_readv(tid, &local, 1, &target, 1, 0);
    if (count != (ssize_t)size) {
        snprintf(decode_error, sizeof(decode_error), "原生字段采集失败:%d", errno);
        return 0;
    }
    return 1;
}

/** 读取真实类型中的整数槽位。 */
static uint64_t word(pid_t tid, uint64_t address, size_t size) {
    uint64_t value = 0;
    remote(tid, address, &value, size);
    return value;
}

/** 完整读取Go字符串或字节切片，长度超限显式失败。 */
static char *go_bytes(pid_t tid, uint64_t slot, size_t *size) {
    uint64_t values[2] = {0, 0};
    if (!remote(tid, slot, values, sizeof(values))) return NULL;
    if (values[1] > 64UL*1024*1024) {
        snprintf(decode_error, sizeof(decode_error), "原型采集长度越界");
        return NULL;
    }
    *size = (size_t)values[1];
    char *data = calloc(*size+1, 1);
    if (!data || !remote(tid, values[0], data, *size)) { free(data); return NULL; }
    return data;
}

/** 依据生成的字段定义递归读取返回对象。 */
static void dump_struct(FILE *out, pid_t tid, uint64_t address, const Field *fields, size_t count) {
    const char *opaque[64];
    size_t opaque_count = 0;
    int comma = 0;
    fputc('{', out);
    for (size_t i = 0; i < count; i++) {
        const Field *field = &fields[i];
        uint64_t slot = address+field->offset;
        if (field->kind == 7 || field->kind == 8) {
            uint64_t present = word(tid, slot+(field->kind == 7 ? 8 : 0), 8);
            if (present && opaque_count < 64) opaque[opaque_count++] = field->name;
            continue;
        }
        if (comma++) fputc(',', out);
        json_string(out, field->name, strlen(field->name));
        fputc(':', out);
        if (field->kind == 1 || field->kind == 2) {
            size_t size = 0;
            char *data = go_bytes(tid, slot, &size);
            if (field->kind == 2 && data) {
                size_t capacity = 4*((size+2)/3)+1;
                unsigned char *encoded = malloc(capacity);
                if (encoded) { int n = EVP_EncodeBlock(encoded, (unsigned char *)data, (int)size); json_string(out, (char *)encoded, (size_t)n); }
                else { snprintf(decode_error, sizeof(decode_error), "观察器内存分配失败"); fputs("null", out); }
                free(encoded);
            } else if (data) json_string(out, data, size);
            else fputs("null", out);
            free(data);
        } else if (field->kind == 9) { double value = 0; remote(tid, slot, &value, 8); fprintf(out, "%.17g", value);
        } else if (field->kind == 3) fputs(word(tid, slot, 1) ? "true" : "false", out);
        else if (field->kind == 4) fprintf(out, "%llu", (unsigned long long)word(tid, slot, field->bytes));
        else if (field->kind == 5) {
            uint64_t pointer = word(tid, slot, 8);
            if (pointer) dump_struct(out, tid, pointer, fields_0, COUNT_0);
            else fputs("null", out);
        } else if (field->kind == 6) {
            uint64_t pointer = word(tid, slot, 8), length = word(tid, slot+8, 8);
            if (length > 256) { snprintf(decode_error, sizeof(decode_error), "原型工具数量越界"); length = 0; }
            fputc('[', out);
            for (uint64_t n = 0; n < length; n++) {
                if (n) fputc(',', out);
                dump_struct(out, tid, word(tid, pointer+n*8, 8), fields_1, COUNT_1);
            }
            fputc(']', out);
        }
    }
    if (opaque_count) {
        if (comma) fputc(',', out);
        fputs("\"opaque_fields\":[", out);
        for (size_t i = 0; i < opaque_count; i++) {
            if (i) fputc(',', out);
            json_string(out, opaque[i], strlen(opaque[i]));
        }
        fputc(']', out);
    }
    fputc('}', out);
}

/** 开始带固定代次的私有事件。 */
static void begin_event(const char *event, const Call *call) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    fputs("{\"event\":", events); json_string(events, event, strlen(event));
    fputs(",\"generation\":", events); json_string(events, generation, strlen(generation));
    fprintf(events, ",\"ns\":%llu", (unsigned long long)ts.tv_sec*1000000000ULL+(unsigned long long)ts.tv_nsec);
    if (call) {
        fputs(",\"request_id\":", events); json_string(events, call->job, strlen(call->job));
        fputs(",\"call_id\":", events); json_string(events, call->id, strlen(call->id));
    }
}

/** 将观察失败交给控制层，业务取消与收口沿既有协议处理。 */
static void error_event(const char *message) {
    begin_event("observer_error", NULL);
    fputs(",\"error\":", events); json_string(events, message, strlen(message));
    fputs("}\n", events); fflush(events);
}

/** 登记线程或等待脱离观察的官方辅助进程。 */
static Task *task(pid_t tid) {
    for (size_t i = 0; i < 4096; i++) if (tasks[i].tid == tid) return &tasks[i];
    for (size_t i = 0; i < 4096; i++) if (!tasks[i].tid) { tasks[i].tid = tid; tasks[i].detach = 0; return &tasks[i]; }
    return NULL;
}

/** 取得与实际goroutine绑定的活动模型调用。 */
static Call *find_call(uint64_t goroutine) {
    for (size_t i = 0; i < 128; i++) if (calls[i].g == goroutine) return &calls[i];
    return NULL;
}

/** 读取控制侧已经原子发布的活动作业。 */
static int active_job(char *out) {
    char path[4096], buffer[256];
    snprintf(path, sizeof(path), "%s/active.json", folder);
    FILE *in = fopen(path, "r");
    if (!in) return 0;
    size_t size = fread(buffer, 1, sizeof(buffer)-1, in); fclose(in); buffer[size] = 0;
    char *key = strstr(buffer, "\"request_id\"");
    char *start = key ? strchr(key+12, '"') : NULL;
    char *end = start ? strchr(start+1, '"') : NULL;
    if (!end || end-start-1 < 1 || end-start-1 > 96) return 0;
    size_t length = (size_t)(end-start-1);
    memcpy(out, start+1, length); out[length] = 0;
    for (size_t i = 0; i < length; i++) if (!((out[i] >= 'a' && out[i] <= 'z') || (out[i] >= 'A' && out[i] <= 'Z') || (out[i] >= '0' && out[i] <= '9') || out[i] == '_' || out[i] == '-')) return 0;
    return 1;
}

/** 从固定 Go TLS 返回处复制已经接受的模型 HTTP 字节，普通遥测流量不进入采集。 */
static TlsSample tls_sample(pid_t tid, const struct user_regs_struct *regs) {
    TlsSample result = {0};
    char job[97];
    if (!active_job(job)) return result;
    if (strcmp(tls_job, job)) {
        strcpy(tls_job, job);
        tls_connection = 0;
        tls_write_progress = 0;
        tls_bytes = 0;
    }
    Call *owner = NULL;
    for (size_t i = 0; i < 128; i++) {
        if (calls[i].g && !calls[i].ended && !strcmp(calls[i].job, job)) {
            if (owner) return result;
            owner = &calls[i];
        }
    }
    if (!owner || tls_bytes > tls_sample_limit) return result;
    decode_error[0] = 0;
    uint64_t count = word(tid, regs->rsp + 0x30, 8);
    uint64_t conn = word(tid, regs->rsp + 0xa8, 8);
    uint64_t data = word(tid, regs->rsp + 0xd8, 8);
    uint64_t requested = word(tid, regs->rsp + 0xe0, 8);
    if (decode_error[0] || !conn || !count || count > requested) return result;
    if (tls_connection && conn != tls_connection) return result;
    uint64_t progress = word(tid, conn + 0x318, 8);
    if (decode_error[0] || !progress) return result;
    if (!tls_connection) {
        const char expected[] = "POST /v1internal:streamGenerateContent";
        char prefix[sizeof(expected) - 1];
        if (count < sizeof(prefix) || !remote(tid, data, prefix, sizeof(prefix)) || memcmp(prefix, expected, sizeof(prefix))) return result;
        tls_connection = conn;
    }
    /* 原生偶尔重复到达同一返回断点。连接的 bytesSent 只随真实写入递增。 */
    if (progress == tls_write_progress) return result;
    result.call = owner;
    if (progress < tls_write_progress || count > tls_sample_limit - tls_bytes) {
        tls_bytes = tls_sample_limit + 1;
        return result;
    }
    tls_write_progress = progress;
    result.data = malloc((size_t)count);
    if (!result.data || !remote(tid, data, result.data, (size_t)count)) {
        free(result.data);
        result.data = NULL;
        tls_bytes = tls_sample_limit + 1;
        return result;
    }
    result.size = (size_t)count;
    tls_bytes += result.size;
    return result;
}

/** 恢复原生线程后才向私有观察管道交付采集副本。 */
static void emit_tls_sample(TlsSample sample) {
    if (!sample.call) return;
    /* 分段交给 Python，避免大正文变成一行多 MiB 的管道消息。 */
    const size_t block = 64 * 1024;
    unsigned char *encoded = sample.data ? malloc(4 * ((block + 2) / 3) + 1) : NULL;
    if (encoded) {
        for (size_t offset = 0; offset < sample.size; offset += block) {
            size_t size = sample.size - offset;
            if (size > block) size = block;
            int bytes = EVP_EncodeBlock(encoded, sample.data + offset, (int)size);
            begin_event("model_tls_write", sample.call);
            fprintf(events, ",\"bytes\":%zu,\"data_base64\":", size);
            json_string(events, (char *)encoded, (size_t)bytes);
            fputs("}\n", events);
        }
    } else {
        begin_event("model_tls_write", sample.call);
        fputs(",\"bytes\":0,\"data_base64\":null}\n", events);
    }
    free(encoded);
    free(sample.data);
}

/** 保存断点与信号现场，诊断事件和业务返回片段分别归档。 */
static void diagnostic_stop(pid_t tid, int sig, unsigned event) {
    if (!image_base || !OBSERVE_ALL_STOPS) return;
    struct user_regs_struct regs;
    siginfo_t info;
    memset(&info, 0, sizeof(info));
    if (ptrace(PTRACE_GETREGS, tid, NULL, &regs) < 0) return;
    int info_ok = ptrace(PTRACE_GETSIGINFO, tid, NULL, &info) == 0;
    unsigned long dr6 = ptrace(PTRACE_PEEKUSER, tid, (void *)offsetof(struct user, u_debugreg[6]), NULL);
    unsigned long dr7 = ptrace(PTRACE_PEEKUSER, tid, (void *)offsetof(struct user, u_debugreg[7]), NULL);
    begin_event("observer_stop", NULL);
    fprintf(events, ",\"tid\":%d,\"signal\":%d,\"ptrace_event\":%u,\"si_code\":%d,\"info_ok\":%s,\"pc\":%llu,\"pc_offset\":%llu,\"rax\":%llu,\"goroutine\":%llu,\"rsp\":%llu,\"rbp\":%llu,\"eflags\":%llu,\"dr6\":%lu,\"dr7\":%lu}\n",
            tid, sig, event, info.si_code, info_ok ? "true" : "false", (unsigned long long)regs.rip,
            (unsigned long long)(regs.rip-image_base), (unsigned long long)regs.rax,
            (unsigned long long)regs.r14, (unsigned long long)regs.rsp,
            (unsigned long long)regs.rbp, (unsigned long long)regs.eflags, dr6, dr7);
}

/** 处理四个固定硬件观察位置。 */
static void observe(pid_t tid, unsigned site, struct user_regs_struct *regs) {
    decode_error[0] = 0;
    uint64_t goroutine = regs->r14;
    if (site == 0) {
        char job[97];
        if (!active_job(job)) { error_event("活动作业缺失"); return; }
        uint64_t depth = word(tid, goroutine+8, 8)-regs->rsp;
        Call *call = find_call(goroutine);
        if (call && !call->ended && call->request == regs->rdi && call->depth == depth && !strcmp(call->job, job)) {
            begin_event("observer_repeat", call); fputs(",\"site\":\"route\"}\n", events); return;
        }
        if (!call) for (size_t i = 0; i < 128; i++) if (!calls[i].g || calls[i].ended) { call = &calls[i]; break; }
        if (!call) { error_event("活动原生调用数量越界"); return; }
        if (strcmp(current_job, job)) { strcpy(current_job, job); call_number = 0; }
        memset(call, 0, sizeof(*call)); call->g = goroutine; call->request = regs->rdi; call->depth = depth;
        strcpy(call->job, job); snprintf(call->id, sizeof(call->id), "%s.%u", job, ++call_number);
        size_t conversation_size = 0, id_size = 0;
        char *conversation = go_bytes(tid, regs->rdi, &conversation_size), *id = go_bytes(tid, regs->rdi+136, &id_size);
        if (decode_error[0]) { free(conversation); free(id); error_event(decode_error); return; }
        begin_event("model_start", call);
        fputs(",\"native_context\":{\"ConversationID\":", events); json_string(events, conversation, conversation_size);
        fputs(",\"RequestID\":", events); json_string(events, id, id_size);
        fprintf(events, ",\"Messages\":%llu,\"Tools\":%llu}}\n", (unsigned long long)word(tid, regs->rdi+72, 8), (unsigned long long)word(tid, regs->rdi+40, 8));
        free(conversation); free(id); return;
    }
    if (site == 2) {
        uint64_t client=word(tid,regs->rsp+0x130,8);
        begin_event("telemetry_upload_sample",NULL);
        fprintf(events,",\"client\":%llu,\"goroutine\":%llu,\"source\":%llu,\"returned_count\":%llu,\"upload_status_raw\":%llu,\"error_present\":%s}\n",
            (unsigned long long)client,(unsigned long long)goroutine,
            (unsigned long long)word(tid,client+16,4),(unsigned long long)regs->rax,
            (unsigned long long)regs->rbx,regs->rcx ? "true" : "false");
        if (decode_error[0]) error_event(decode_error);
        return;
    }
    if (site == 3) {
        char job[97];
        if (!active_job(job)) { error_event("SDK原始帧缺少活动作业"); return; }
        Call *owner = NULL;
        for (size_t i=0;i<128;i++) if (calls[i].g && !calls[i].ended && !strcmp(calls[i].job,job)) {
            if (owner) { error_event("SDK原始帧存在多个活动模型调用"); return; }
            owner=&calls[i];
        }
        if (!owner) { error_event("SDK原始帧缺少模型调用"); return; }
        if (regs->rbx > 64UL*1024*1024) { error_event("SDK原始帧采集长度越界"); return; }
        size_t size=(size_t)regs->rbx;
        unsigned char *data=malloc(size?size:1);
        unsigned char *encoded=malloc(4*((size+2)/3)+1);
        if (!data || !encoded || !remote(tid,regs->rax,data,size)) { free(data);free(encoded);error_event("SDK原始帧读取失败");return; }
        owner->raw_g=goroutine;owner->raw_ptr=regs->rax;owner->raw_size=size;owner->raw_pending=1;owner->raw_epoch++;
        int bytes=EVP_EncodeBlock(encoded,data,(int)size);
        begin_event("gemini_response",owner);
        fprintf(events,",\"source\":\"codeassist_scanner_block\",\"raw_epoch\":%llu,\"bytes\":%zu,\"goroutine\":%llu,\"tid\":%d,\"data_base64\":",(unsigned long long)owner->raw_epoch,size,(unsigned long long)goroutine,tid);
        json_string(events,(char *)encoded,(size_t)bytes);fputs("}\n",events);free(data);free(encoded);return;
    }
    Call *call = find_call(goroutine);
    if (!call) { error_event("原生返回缺少调用归属"); return; }
    if (site == 1) {
        /* 固定Receive的chanrecv返回处：AL为接收结果，RCX为GetChatMessageResponse。 */
        uint64_t stream=word(tid,regs->rsp+0x38,8);
        int success=(regs->rax & 0xff) != 0;
        uint64_t value=regs->rcx;
        if (decode_error[0]) {error_event(decode_error);return;}
        if (call->ended) {
            if (success) {error_event("结束后原生返回发生变化");return;}
            begin_event("observer_repeat",call);fputs(",\"site\":\"native_eof\"}\n",events);return;
        }
        call->receive_stream=stream;call->receive_result=success;call->receive_object=value;call->raw_pending=0;
        if (!success) {
            call->ended=1;begin_event("model_end",call);
            /* EOF不代表业务成功；错误通道由官方Err稍后消费，最终还须核对真实控制RPC。 */
            fprintf(events,",\"native_error_present\":null,\"source\":\"native_receive_channel_closed\"}\n");return;
        }
        call->receive_epoch++;
        if (!value) {error_event("原生成功接收缺少消息对象");return;}
        char *json=NULL;size_t size=0;FILE *buffer=open_memstream(&json,&size);
        if (!buffer) {error_event("观察器内存分配失败");return;}
        dump_struct(buffer,tid,value,fields_2,COUNT_2);fclose(buffer);
        if (decode_error[0]) error_event(decode_error);
        else {begin_event("response_chunk",call);fprintf(events,",\"receive_epoch\":%llu,\"chunk\":",(unsigned long long)call->receive_epoch);fwrite(json,1,size,events);fputs("}\n",events);}
        free(json);
    }
}

/** 为每个原生线程配置执行观察；代码页保持原内容。 */
static int configure(pid_t tid) {
    /* 四个硬件槽中，Debug 复用遥测观察槽记录 TLS。原生发送及队列不经过观察器重写。 */
    for (unsigned i = 0; i < 4; i++) {
        unsigned long site = i == 2 && capture_tls ? tls_write_site : sites[i];
        if (ptrace(PTRACE_POKEUSER, tid, (void *)offsetof(struct user, u_debugreg[i]), (void *)(image_base+site)) < 0) return 0;
    }
    if (ptrace(PTRACE_POKEUSER, tid, (void *)offsetof(struct user, u_debugreg[6]), NULL) < 0) return 0;
    return ptrace(PTRACE_POKEUSER, tid, (void *)offsetof(struct user, u_debugreg[7]), (void *)0x55UL) == 0;
}

/** 从实际执行映像验证完整身份、映射及固定指令。 */
static int verify_image(void) {
    char path[128], line[8192];
    snprintf(path, sizeof(path), "/proc/%d/exe", root_pid);
    struct stat expected_image, actual_image;
    if (stat(binary, &expected_image) != 0 || stat(path, &actual_image) != 0 ||
        !S_ISREG(actual_image.st_mode) || actual_image.st_dev != expected_image.st_dev ||
        actual_image.st_ino != expected_image.st_ino || actual_image.st_size != expected_image.st_size) { error_event("execution_file_identity"); return 0; }
    FILE *file = fopen(path, "rb");
    if (!file) return 0;
    EVP_MD_CTX *ctx = EVP_MD_CTX_new();
    if (!ctx) { fclose(file); return 0; }
    EVP_DigestInit_ex(ctx, EVP_sha256(), NULL);
    unsigned char block[65536], digest[32]; size_t size; unsigned int digest_size;
    while ((size = fread(block, 1, sizeof(block), file))) EVP_DigestUpdate(ctx, block, size);
    int failed = ferror(file); fclose(file);
    EVP_DigestFinal_ex(ctx, digest, &digest_size); EVP_MD_CTX_free(ctx);
    char hex[65]; for (unsigned i = 0; i < 32; i++) snprintf(hex+i*2, 3, "%02x", digest[i]);
    if (failed || digest_size != 32 || strcmp(hex, SOURCE_SHA)) { error_event("execution_source_checksum"); return 0; }
    snprintf(path, sizeof(path), "/proc/%d/maps", root_pid);
    file = fopen(path, "r"); if (!file) return 0;
    unsigned parsed_maps = 0, matching_inodes = 0, matching_devices = 0;
    while (fgets(line, sizeof(line), file)) {
        unsigned long first, last, offset;
        unsigned major_number, minor_number; unsigned long long inode; char permissions[5];
        if (sscanf(line, "%lx-%lx %4s %lx %x:%x %llu", &first, &last, permissions, &offset,
                   &major_number, &minor_number, &inode) != 7) continue;
        parsed_maps++;
        if (inode == actual_image.st_ino) matching_inodes++;
        if (makedev(major_number, minor_number) == actual_image.st_dev) matching_devices++;
        if (makedev(major_number, minor_number) != actual_image.st_dev || inode != actual_image.st_ino) continue;
        /* 按实际背板识别映像；共享代码的可写映射保持每进程私有。 */
        if (permissions[1] == 'w' && permissions[3] == 's') { fclose(file); return 0; }
        if (offset == 0) image_base = first;
    }
    fclose(file); if (!image_base) { char reason[128]; snprintf(reason, sizeof(reason), "execution_base_missing_maps_%u_inode_%u_device_%u", parsed_maps, matching_inodes, matching_devices); error_event(reason); return 0; }
    const unsigned char *expected[] = {expected_0, expected_1, expected_2, expected_3};
    const size_t sizes[] = {sizeof(expected_0), sizeof(expected_1), sizeof(expected_2), sizeof(expected_3)};
    for (unsigned i = 0; i < 4; i++) {
        unsigned char actual[16];
        if (!remote(root_pid, image_base+sites[i], actual, sizes[i]) || memcmp(actual, expected[i], sizes[i])) { char reason[64]; snprintf(reason, sizeof(reason), "execution_site_%u", i); error_event(reason); return 0; }
    }
    if (capture_tls) {
        unsigned char actual[sizeof(tls_write_signature)];
        if (!remote(root_pid, image_base + tls_write_site, actual, sizeof(actual)) || memcmp(actual, tls_write_signature, sizeof(actual))) capture_tls = 0;
    }
    return 1;
}

/** 父进程持有独占空闲许可后，请求使用线程组停态交接。 */
static void request_checkpoint(int number, siginfo_t *information, void *context) {
    (void)number; (void)context;
    if (information->si_pid != controller_pid) return;
    checkpoint_requested = 1;
    if (root_pid > 0) kill(root_pid, SIGSTOP);
}

/** 按真实线程表确认全部线程已离开 ptrace 并仍处于线程组停止状态。 */
static size_t stopped_threads(pid_t tids[], size_t capacity) {
    char path[128];
    snprintf(path, sizeof(path), "/proc/%d/task", root_pid);
    DIR *directory = opendir(path);
    if (!directory) return 0;
    size_t count = 0;
    struct dirent *entry;
    while ((entry = readdir(directory))) {
        char *end;
        long tid = strtol(entry->d_name, &end, 10);
        if (!tid || *end) continue;
        if (count == capacity) { count = 0; break; }
        snprintf(path, sizeof(path), "/proc/%d/task/%ld/status", root_pid, tid);
        FILE *status = fopen(path, "r");
        if (!status) { count = 0; break; }
        int stopped = 0, untraced = 0;
        char line[256], state;
        unsigned tracer;
        while (fgets(line, sizeof(line), status)) {
            if (sscanf(line, "State: %c", &state) == 1) stopped = state == 'T';
            if (sscanf(line, "TracerPid: %u", &tracer) == 1) untraced = tracer == 0;
        }
        fclose(status);
        if (!stopped || !untraced) { count = 0; break; }
        tids[count++] = (pid_t)tid;
    }
    closedir(directory);
    return count;
}

/** 从停态取回所有线程，执行体和硬件断点核验通过后才允许续跑。 */
static int checkpoint_handoff(unsigned long options, const sigset_t *resume_signal) {
    pid_t tids[sizeof(tasks) / sizeof(tasks[0])];
    size_t count = 0;
    const struct timespec retry = {0, 5000000};
    /* 最后一项 detach 返回时，SIGSTOP 仍可能在内核向线程组分发。 */
    for (unsigned attempt = 0; attempt < 200 && !(count = stopped_threads(tids, sizeof(tids) / sizeof(tids[0]))); attempt++)
        nanosleep(&retry, NULL);
    if (!count) return 0;
    begin_event("observer_checkpoint_stopped", NULL);
    fprintf(events, ",\"native_pid\":%d,\"threads\":%zu}\n", root_pid, count);
    for (;;) {
        siginfo_t sender;
        int received = sigwaitinfo(resume_signal, &sender);
        if (received < 0 && errno != EINTR) return 0;
        if (received == SIGUSR2 && sender.si_pid == controller_pid) break;
    }
    count = stopped_threads(tids, sizeof(tids) / sizeof(tids[0]));
    if (!count) return 0;
    for (size_t index = 0; index < count; index++) {
        int status;
        pid_t tid = tids[index], waited;
        if (!task(tid) || ptrace(PTRACE_SEIZE, tid, NULL, (void *)options) < 0
                || ptrace(PTRACE_INTERRUPT, tid, NULL, NULL) < 0) return 0;
        do { waited = waitpid(tid, &status, __WALL); } while (waited < 0 && errno == EINTR);
        if (waited != tid || !WIFSTOPPED(status)) return 0;
    }
    image_base = 0;
    if (!verify_image()) return 0;
    for (size_t index = 0; index < count; index++)
        if (!configure(tids[index])) return 0;
    checkpoint_requested = 0;
    for (size_t index = 0; index < count; index++)
        if (ptrace(PTRACE_CONT, tids[index], NULL, NULL) < 0) return 0;
    if (kill(root_pid, SIGCONT) < 0) return 0;
    begin_event("observer_checkpoint_resumed", NULL);
    fprintf(events, ",\"native_pid\":%d,\"threads\":%zu}\n", root_pid, count);
    return 1;
}

/**
 * 启动固定执行体并观察其原生线程，信号继续交给原程序处理。
 * @param argc 启动参数数量。
 * @param argv 执行体及原生CLI参数。
 * @return 观察器正常收口返回零，准入失败返回二。
 */
int main(int argc, char **argv) {
    if (argc < 2) return 2;
    /* 监督层异常退出时回收本观察器；原生子进程继续沿已有父退出信号收口。 */
    controller_pid = getppid();
    if (prctl(PR_SET_PDEATHSIG, SIGKILL) != 0 || getppid() != controller_pid) return 2;
    folder = getenv("AGY_BRIDGE_FOLDER"); generation = getenv("AGY_BRIDGE_GENERATION"); binary = getenv("AGY_BRIDGE_BINARY");
    capture_tls = getenv("AGY_BRIDGE_CAPTURE_TLS") != NULL;
    const char *fd_env = getenv("AGY_BRIDGE_EVENT_FD"), *input = getenv("AGY_BRIDGE_STDIN");
    if (!folder || !generation || !binary || !fd_env || !input) return 2;
    events = fdopen(atoi(fd_env), "w"); if (!events) return 2;
    setvbuf(events, NULL, _IOLBF, 0);
    root_pid = fork();
    if (root_pid < 0) return 2;
    if (root_pid == 0) {
        unsetenv("AGY_BRIDGE_CAPTURE_TLS");
        unsetenv("AGY_BRIDGE_CHECKPOINT");
        prctl(PR_SET_PDEATHSIG, SIGKILL);
        int fd = open(input, O_RDONLY); if (fd < 0 || dup2(fd, STDIN_FILENO) < 0) _exit(126);
        if (fd != STDIN_FILENO) close(fd);
        if (ptrace(PTRACE_TRACEME, 0, NULL, NULL) < 0) _exit(126);
        raise(SIGSTOP); execv(argv[1], argv+1); _exit(127);
    }
    sigset_t resume_signal;
    if (getenv("AGY_BRIDGE_CHECKPOINT")) {
        struct sigaction checkpoint = {.sa_sigaction = request_checkpoint, .sa_flags = SA_SIGINFO};
        sigemptyset(&checkpoint.sa_mask);
        sigemptyset(&resume_signal);
        sigaddset(&resume_signal, SIGUSR2);
        if (sigprocmask(SIG_BLOCK, &resume_signal, NULL) < 0 || sigaction(SIGUSR1, &checkpoint, NULL) < 0) return 2;
    }
    task(root_pid);
    int status, verified = 0;
    unsigned long options = PTRACE_O_TRACEEXEC | PTRACE_O_TRACECLONE | PTRACE_O_TRACEFORK | PTRACE_O_TRACEVFORK | PTRACE_O_EXITKILL;
    for (;;) {
        pid_t tid = waitpid(-1, &status, __WALL);
        if (tid < 0) { if (errno == EINTR) continue; break; }
        Task *entry = task(tid);
        if (!entry) { error_event("线程观察数量越界"); kill(root_pid, SIGKILL); break; }
        if (WIFEXITED(status) || WIFSIGNALED(status)) {
            entry->tid = 0;
            if (tid == root_pid) {
                begin_event("native_exit", NULL); fprintf(events, ",\"code\":%d,\"signal\":%d}\n", WIFEXITED(status) ? WEXITSTATUS(status) : -1, WIFSIGNALED(status) ? WTERMSIG(status) : 0);
            }
            continue;
        }
        if (!WIFSTOPPED(status)) continue;
        if (entry->detach) { ptrace(PTRACE_DETACH, tid, NULL, NULL); entry->tid = 0; continue; }
        int sig = WSTOPSIG(status); unsigned event = (unsigned)status >> 16;
        diagnostic_stop(tid, sig, event);
        if (event == PTRACE_EVENT_EXEC && tid == root_pid) {
            if (!verify_image() || !configure(tid)) { error_event("实际执行映像准入失败"); kill(root_pid, SIGKILL); continue; }
            verified = 1;
            begin_event("observer_ready", NULL); fprintf(events, ",\"native_pid\":%d,\"source_sha256\":\"%s\",\"backend\":\"ptrace_hardware\"}\n", root_pid, SOURCE_SHA);
            ptrace(PTRACE_CONT, tid, NULL, NULL); continue;
        }
        if (event == PTRACE_EVENT_CLONE || event == PTRACE_EVENT_FORK || event == PTRACE_EVENT_VFORK) {
            unsigned long child = 0; ptrace(PTRACE_GETEVENTMSG, tid, NULL, &child);
            Task *new_entry = task((pid_t)child);
            if (new_entry) new_entry->detach = event != PTRACE_EVENT_CLONE;
            if (checkpoint_requested) {
                /* 先消费新线程事件再停止父线程，避免漏掉仍挂在观察器上的子线程。 */
                kill(root_pid, SIGSTOP);
            }
            ptrace(PTRACE_CONT, tid, NULL, NULL); continue;
        }
        if (checkpoint_requested) {
            if (!verified || (ptrace(PTRACE_DETACH, tid, NULL, (void *)(long)SIGSTOP) < 0 && errno != ESRCH)) {
                error_event("checkpoint_detach_failed"); kill(root_pid, SIGKILL); return 2;
            }
            entry->tid = 0;
            int attached = 0;
            for (size_t index = 0; index < sizeof(tasks) / sizeof(tasks[0]); index++) attached |= tasks[index].tid != 0;
            if (!attached && !checkpoint_handoff(options, &resume_signal)) {
                error_event("checkpoint_reattach_failed"); kill(root_pid, SIGKILL); return 2;
            }
            continue;
        }
        if (event == PTRACE_EVENT_STOP) {
            if (verified && !configure(tid)) { error_event("thread_reattach_failed"); kill(root_pid, SIGKILL); return 2; }
            ptrace(PTRACE_CONT, tid, NULL, NULL); continue;
        }
        if (sig == SIGSTOP) {
            ptrace(PTRACE_SETOPTIONS, tid, NULL, (void *)options);
            if (verified) configure(tid);
            ptrace(PTRACE_CONT, tid, NULL, NULL); continue;
        }
        if (sig == SIGTRAP && !event && verified) {
            struct user_regs_struct regs;
            if (ptrace(PTRACE_GETREGS, tid, NULL, &regs) == 0) {
                int handled = 0;
                TlsSample sample = {0};
                for (unsigned i = 0; i < 4; i++) {
                    int tls = i == 2 && capture_tls;
                    if (regs.rip != image_base + (tls ? tls_write_site : sites[i])) continue;
                    if (tls) sample = tls_sample(tid, &regs);
                    else observe(tid, i, &regs);
                    handled = 1;
                    break;
                }
                if (handled) {
                    /* 只在首个成功接收的观察位置暂停，用于定位并发信号与恢复的关系。 */
                    if (regs.rip == image_base+sites[1] && DIAG_PAUSE_US && diagnostic_pause_count++ == 0) usleep(DIAG_PAUSE_US);
                    /* RF只跳过这次恢复的执行断点，原生下一次调用继续触发。 */
                    regs.eflags |= 1UL << 16;
                    ptrace(PTRACE_SETREGS, tid, NULL, &regs);
                    ptrace(PTRACE_POKEUSER, tid, (void *)offsetof(struct user, u_debugreg[6]), NULL);
                    ptrace(PTRACE_CONT, tid, NULL, NULL);
                    emit_tls_sample(sample);
                    continue;
                }
            }
        }
        ptrace(PTRACE_CONT, tid, NULL, (void *)(long)sig);
    }
    fflush(events);
    return verified ? 0 : 2;
}
