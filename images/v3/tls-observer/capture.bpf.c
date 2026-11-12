/* 固定 x64 原生 TLS 返回边界的只读探针。构建时只依赖 Linux UAPI。 */
#include <linux/bpf.h>

#define SEC(name) __attribute__((section(name), used))
#define UINT(name, value) int (*name)[value]
#define TYPE(name, value) value *name

static void *(*map_lookup)(void *, const void *) = (void *)BPF_FUNC_map_lookup_elem;
static long (*namespace_pid)(unsigned long, unsigned long, struct bpf_pidns_info *, unsigned int) = (void *)BPF_FUNC_get_ns_current_pid_tgid;
static void *(*reserve)(void *, unsigned long, unsigned long) = (void *)BPF_FUNC_ringbuf_reserve;
static void (*submit)(void *, unsigned long) = (void *)BPF_FUNC_ringbuf_submit;
static void (*discard)(void *, unsigned long) = (void *)BPF_FUNC_ringbuf_discard;
static long (*read_user)(void *, unsigned int, const void *) = (void *)BPF_FUNC_probe_read_user;

struct registers {
    unsigned long r15, r14, r13, r12, bp, bx, r11, r10, r9, r8;
    unsigned long ax, cx, dx, si, di, orig_ax, ip, cs, flags, sp, ss;
};
struct counts { unsigned long writes, bytes, dropped, read_errors, oversized; };
struct target { unsigned long device, inode; unsigned int pid, padding; };
struct record {
    unsigned long pid_tid, ssl, sequence;
    unsigned int accepted, requested;
    char data[];
};
struct { UINT(type, BPF_MAP_TYPE_RINGBUF); UINT(max_entries, 1 << 24); } events SEC(".maps");
struct { UINT(type, BPF_MAP_TYPE_ARRAY); UINT(max_entries, 1); TYPE(key, unsigned int); TYPE(value, struct counts); } stats SEC(".maps");
struct { UINT(type, BPF_MAP_TYPE_ARRAY); UINT(max_entries, 1); TYPE(key, unsigned int); TYPE(value, struct target); } config SEC(".maps");

/* 不同容量使用独立子程序，确保ring保留长度为校验器可见的常量。 */
#define EMIT(name, capacity) \
__attribute__((noinline)) static int name(struct registers *ctx, unsigned long pid_tid, unsigned long sequence, struct counts *counts) \
{ \
    int accepted = (int)ctx->ax; \
    if (accepted <= 0 || accepted > capacity || accepted > (unsigned int)ctx->r15) return 0; \
    struct record *record = reserve(&events, sizeof(struct record) + capacity, 0); \
    if (!record) { __sync_fetch_and_add(&counts->dropped, 1); return 0; } \
    record->pid_tid = pid_tid; record->ssl = ctx->bx; record->sequence = sequence; \
    record->accepted = accepted; record->requested = (unsigned int)ctx->r15; \
    unsigned long size = (unsigned int)accepted; \
    asm volatile("%0 &= 16777215" : "+r"(size)); \
    if (size > capacity) { discard(record, 0); __sync_fetch_and_add(&counts->oversized, 1); return 0; } \
    if (read_user(record->data, size, (void *)ctx->r14)) { __sync_fetch_and_add(&counts->read_errors, 1); discard(record, 0); return 0; } \
    submit(record, 0); return 0; \
}
EMIT(emit16k, 16384)
EMIT(emit64k, 65536)
EMIT(emit256k, 262144)
EMIT(emit1m, 1048576)
EMIT(emit4m, 4194304)
EMIT(emit8m, 8388608)

/** 按一次SSL接受量选择有界副本容量。@param ctx 固定ABI。@return 始终为零。 */
SEC("uprobe") int capture(struct registers *ctx)
{
    int accepted = (int)ctx->ax;
    if (accepted <= 0) return 0;
    unsigned int key = 0;
    struct counts *counts = map_lookup(&stats, &key);
    if (!counts) return 0;
    unsigned long sequence = __sync_fetch_and_add(&counts->writes, 1) + 1;
    __sync_fetch_and_add(&counts->bytes, accepted);
    struct target *target = map_lookup(&config, &key);
    struct bpf_pidns_info identity = {};
    if (!target || namespace_pid(target->device, target->inode, &identity, sizeof(identity)) || identity.tgid != target->pid) {
        __sync_fetch_and_add(&counts->read_errors, 1); return 0;
    }
    if (accepted > (unsigned int)ctx->r15) { __sync_fetch_and_add(&counts->oversized, 1); return 0; }
    unsigned long pid_tid = ((unsigned long)identity.tgid << 32) | identity.pid;
    if (accepted <= 16384) return emit16k(ctx, pid_tid, sequence, counts);
    if (accepted <= 65536) return emit64k(ctx, pid_tid, sequence, counts);
    if (accepted <= 262144) return emit256k(ctx, pid_tid, sequence, counts);
    if (accepted <= 1048576) return emit1m(ctx, pid_tid, sequence, counts);
    if (accepted <= 4194304) return emit4m(ctx, pid_tid, sequence, counts);
    if (accepted <= 8388608) return emit8m(ctx, pid_tid, sequence, counts);
    __sync_fetch_and_add(&counts->oversized, 1); return 0;
}
char LICENSE[] SEC("license") = "GPL";
