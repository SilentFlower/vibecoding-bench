/* 仅链接到测试产物，控制能力探测与加载失败。其余隔离逻辑由内核执行。 */
#include <errno.h>
#include <linux/landlock.h>
#include <seccomp.h>
#include <stdarg.h>
#include <stddef.h>
#include <stdlib.h>
#include <string.h>
#include <sys/syscall.h>

long __real_syscall(long number, ...);
int __real_seccomp_load(scmp_filter_ctx filter);

/** 在 Landlock 探测时选择测试分支，真实规则仍由当前内核执行。
 * @param number 测试中的 Landlock 调用编号。@param ... 内核调用的原参数。
 * @return 探测版本或实际调用结果。
 */
long __wrap_syscall(long number, ...) {
    va_list args;
    long result;
    va_start(args, number);
    if (number == SYS_landlock_create_ruleset) {
        struct landlock_ruleset_attr *attr = va_arg(args, struct landlock_ruleset_attr *);
        size_t size = va_arg(args, size_t);
        int flags = va_arg(args, int);
        result = __real_syscall(number, attr, size, flags);
        if (!attr && flags == LANDLOCK_CREATE_RULESET_VERSION) {
            const char *abi = getenv("TUI_GUARD_TEST_ABI");
            if (abi && !strcmp(abi, "1")) result = 1;
            if (result >= 2 && abi && !strcmp(abi, "2")) result = 2;
        }
    } else {
        int rules = va_arg(args, int);
        int argument = va_arg(args, int);
        if (number == SYS_landlock_add_rule) {
            struct landlock_path_beneath_attr *path = va_arg(args, struct landlock_path_beneath_attr *);
            int flags = va_arg(args, int);
            result = __real_syscall(number, rules, argument, path, flags);
        } else if (number == SYS_landlock_restrict_self) {
            result = __real_syscall(number, rules, argument);
        } else {
            abort();
        }
    }
    va_end(args);
    return result;
}

/** 按测试条件注入安装失败。@param filter 待安装过滤器。@return 安装结果。 */
int __wrap_seccomp_load(scmp_filter_ctx filter) {
    if (getenv("TUI_GUARD_TEST_LOAD_FAILURE")) return -EIO;
    return __real_seccomp_load(filter);
}
