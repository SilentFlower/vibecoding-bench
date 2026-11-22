#define _GNU_SOURCE
#include <errno.h>
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
/* 固定内核映射只含 C99 数字；实验观察器保持 Debian 12 的解析 ABI。 */
__asm__(".symver __isoc23_sscanf,__isoc99_sscanf@GLIBC_2.7");
__asm__(".symver __isoc23_strtol,strtol@GLIBC_2.2.5");

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

/** 观察固定版本的令牌消费、SSE逻辑块、模型入口及遥测返回。 */
static void observe(pid_t tid, unsigned site, struct user_regs_struct *regs) {
    decode_error[0] = 0;
    uint64_t goroutine = regs->r14;

    if (site == 1) {
        if (regs->rbx || !regs->rax) {
            begin_event("oauth_token_error", NULL);
            fprintf(events, ",\"wrapper\":%u}\n", site);
            return;
        }
        size_t length = (size_t)word(tid, regs->rax + 8, 8);
        if (!length || length > 8192) { error_event("访问令牌布局核对失败"); return; }
        size_t size = 0;
        char *value = go_bytes(tid, regs->rax, &size);
        if (!value) { error_event("访问令牌读取失败"); return; }
        unsigned char digest[32]; unsigned int bytes = 0;
        EVP_Digest(value, size, digest, &bytes, EVP_sha256(), NULL);
        free(value);
        if (bytes != 32) { error_event("访问令牌摘要失败"); return; }
        char hex[65];
        for (unsigned i = 0; i < 32; i++) snprintf(hex + i * 2, 3, "%02x", digest[i]);
        Call *owner = find_call(goroutine);
        begin_event("oauth_token_read", owner);
        fprintf(events, ",\"wrapper\":%u,\"caller_offset\":%llu,\"goroutine\":%llu,\"token_sha256\":\"%s\"}\n", site, (unsigned long long)(word(tid, regs->rbp + 8, 8) - image_base), (unsigned long long)goroutine, hex);
        return;
    }

    if (site == 3) {
        char job[97];
        if (!active_job(job) || !regs->rbx || regs->rbx > 1048576) return;
        Call *owner = NULL;
        for (size_t i = 0; i < 128; i++) if (calls[i].g && !calls[i].ended && !strcmp(calls[i].job, job)) {
            if (owner) return;
            owner = &calls[i];
        }
        if (!owner) return;
        size_t size = (size_t)regs->rbx;
        char *data = calloc(size + 1, 1);
        if (!data || !remote(tid, regs->rax, data, size)) { free(data); return; }
        unsigned char *encoded = malloc(4 * ((size + 2) / 3) + 1);
        if (!encoded) { free(data); return; }
        int bytes = EVP_EncodeBlock(encoded, (unsigned char *)data, (int)size);
        uint64_t caller = word(tid, regs->rsp, 8);
        begin_event("native_sse_block", owner);
        fprintf(events, ",\"source\":\"codeassist_to_stream_response_chunk\",\"caller_offset\":%llu,\"bytes\":%zu,\"data_base64\":", (unsigned long long)(caller - image_base), size);
        json_string(events, (char *)encoded, (size_t)bytes); fputs("}\n", events);
        free(data); free(encoded);
        return;
    }
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
}

/** 为每个原生线程配置执行观察；代码页保持原内容。 */
static int configure(pid_t tid) {
    for (unsigned i = 0; i < 4; i++) if (ptrace(PTRACE_POKEUSER, tid, (void *)offsetof(struct user, u_debugreg[i]), (void *)(image_base+sites[i])) < 0) return 0;
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
        actual_image.st_ino != expected_image.st_ino || actual_image.st_size != expected_image.st_size) return 0;
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
    if (failed || digest_size != 32 || strcmp(hex, SOURCE_SHA)) return 0;
    snprintf(path, sizeof(path), "/proc/%d/maps", root_pid);
    file = fopen(path, "r"); if (!file) return 0;
    while (fgets(line, sizeof(line), file)) {
        unsigned long first, last, offset;
        unsigned major_number, minor_number; unsigned long long inode; char permissions[5];
        if (sscanf(line, "%lx-%lx %4s %lx %x:%x %llu", &first, &last, permissions, &offset,
                   &major_number, &minor_number, &inode) != 7) continue;
        if (makedev(major_number, minor_number) != actual_image.st_dev || inode != actual_image.st_ino) continue;
        /* 按实际背板识别映像；共享代码的可写映射保持每进程私有。 */
        if (permissions[1] == 'w' && permissions[3] == 's') { fclose(file); return 0; }
        if (offset == 0) image_base = first;
    }
    fclose(file); if (!image_base) return 0;
    const unsigned char *expected[] = {expected_0, expected_1, expected_2, expected_3};
    const size_t sizes[] = {sizeof(expected_0), sizeof(expected_1), sizeof(expected_2), sizeof(expected_3)};
    for (unsigned i = 0; i < 4; i++) {
        unsigned char actual[16];
        if (!remote(root_pid, image_base+sites[i], actual, sizes[i]) || memcmp(actual, expected[i], sizes[i])) return 0;
    }
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
    folder = getenv("AGY_BRIDGE_FOLDER"); generation = getenv("AGY_BRIDGE_GENERATION"); binary = getenv("AGY_BRIDGE_BINARY");
    const char *fd_env = getenv("AGY_BRIDGE_EVENT_FD"), *input = getenv("AGY_BRIDGE_STDIN");
    if (!folder || !generation || !binary || !fd_env || !input) return 2;
    events = fdopen(atoi(fd_env), "w"); if (!events) return 2;
    setvbuf(events, NULL, _IOLBF, 0);
    root_pid = fork();
    if (root_pid < 0) return 2;
    if (root_pid == 0) {
        prctl(PR_SET_PDEATHSIG, SIGKILL);
        int fd = open(input, O_RDONLY); if (fd < 0 || dup2(fd, STDIN_FILENO) < 0) _exit(126);
        if (fd != STDIN_FILENO) close(fd);
        if (ptrace(PTRACE_TRACEME, 0, NULL, NULL) < 0) _exit(126);
        raise(SIGSTOP); execv(argv[1], argv+1); _exit(127);
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
                for (unsigned i = 0; i < 4; i++) if (regs.rip == image_base+sites[i]) { observe(tid, i, &regs); handled = 1; break; }
                if (handled) {
                    /* 只在首个成功接收的观察位置暂停，用于定位并发信号与恢复的关系。 */
                    if (regs.rip == image_base+sites[1] && DIAG_PAUSE_US && diagnostic_pause_count++ == 0) usleep(DIAG_PAUSE_US);
                    /* RF只跳过这次恢复的执行断点，原生下一次调用继续触发。 */
                    regs.eflags |= 1UL << 16;
                    ptrace(PTRACE_SETREGS, tid, NULL, &regs);
                    ptrace(PTRACE_POKEUSER, tid, (void *)offsetof(struct user, u_debugreg[6]), NULL);
                    ptrace(PTRACE_CONT, tid, NULL, NULL); continue;
                }
            }
        }
        ptrace(PTRACE_CONT, tid, NULL, (void *)(long)sig);
    }
    fflush(events);
    return verified ? 0 : 2;
}
