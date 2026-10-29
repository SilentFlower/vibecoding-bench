"""制作真实日志字段归属、处理阶段及收尾任务。"""
from draft_content import build_project


def main() -> None:
    """冻结六项独立任务，材料与授权围绕真实Logger行为。@return None。"""
    materials = {
        'materials/extra-layers.md': 'Remove only this synthetic process\'s initial sinks and add a local capture sink that snapshots message.record["extra"]. Configure global extra={origin:global,stable:global};bound=logger.bind(origin="bound",bound_only="yes"). Inside logger.contextualize(origin="context",request="A"),call bound.info("inside",origin="call") then logger.info("context"). After exit call logger.info("outside"). Explain all three actual extra maps and context exit behavior,without changing library code or real logging configuration.\n',
        'materials/lazy-filter.md': 'Use one local sink at INFO with filter=lambda record:False. A zero-argument expensive() appends called to a list and returns value. Call logger.opt(lazy=True).debug("debug {item}",item=expensive),record call count,then the corresponding INFO call. Explain actual call count and absent sink records by the real processing stages;do not infer a runtime speed guarantee from this synthetic counter. No edits.\n',
        'materials/options.md': 'Use a local record capture sink. base=logger.opt(capture=False);base.info("first",attribute="synthetic");base.opt(raw=True).info("second",attribute="synthetic");logger.opt(raw=True,capture=False).info("third",attribute="synthetic"). Compare captured extra and advise how to retain the intended message/metadata policy when choosing opt options. No real sensitive values or source edits.\n',
        'materials/failure-signaling.md': 'Define failing() that raises ValueError("synthetic rejection"). Compare logger.catch(failing)(),logger.catch(default="rejected")(failing)(),and logger.catch(reraise=True)(failing)(). Use local captured logs with diagnose=False/backtrace=False. Advise a caller-visible business result/exception contract;an emitted error log is not an automatic failed return or propagated exception. No implementation or production invocation.\n',
        'materials/async-shutdown.md': 'Inside one asyncio.run-owned loop,register an async sink that signals entered,awaits a release Event,then appends its actual message. Log pending and call completion=logger.complete(). Wait for entered and inspect that output is still absent;release the Event,await completion and inspect the one completed message before removing that sink. Plan producer/sink/loop lifetime and shutdown ownership from these controls. Do not invent a timeout or cross-loop durability guarantee. No external logging target or implementation.\n',
        'disclosure/partial-configuration.md': 'Complete isolated reproduction: register old StringIO sink with format={message}. Call logger.configure(handlers=[{sink:firstStringIO,format:{message},catch:False},{sink:secondStringIO,level:NOT_A_REAL_LEVEL}]). The second addition raises ValueError. Afterwards logger.info("after failed replacement") writes nothing to old or secondStringIO,but firstStringIO receives "after failed replacement\\n". Removing the retained old handler ID now raises ValueError. The old sink was removed before sequential new additions;the first addition succeeded before the second failed. Diagnose the real state and advise caller-owned validation/recovery without claiming atomic rollback or modifying the library.\n',
        'disclosure/unavailable.md': 'The complete handler configuration,registration/replacement order,exception and old/new sink observations cannot be supplied. No complete reproduction distinguishes removal,filtering,registration failure or output target changes.\n'}
    definitions = [
        ('LG-U01', 'understand', '追踪结构化日志的字段优先级',
            'Explain the three complete record extra maps and context restoration. No edits.',
            ['materials/extra-layers.md'], 'explained',
            'For the supplied keys,global extra is overlaid by context,then bind,then captured call kwargs. inside has origincall/stableglobal/requestA/bound_onlyyes;the context record has origincontext/stableglobal/requestA;outside has originglobal/stableglobal. Exiting contextualize restores the prior context. Bound logger wrappers share the core;do not infer isolated sink sets or deep immutable payload snapshots.',
            ['record_extra_precedence_and_context_exit_are_distinct']),
        ('LG-U02', 'understand', '解释惰性日志与过滤器的调用时点',
            'Explain the complete lazy callback counter and filtered output controls. No edits.',
            ['materials/lazy-filter.md'], 'explained',
            'The DEBUG call is below the minimum configured handler level,so its callback is not evaluated. The INFO call reaches record preparation,so lazy invokes expensive once before the per-sink filter discards the record. There are no emitted records but one callback. Distinguish global level gating from sink filter execution;do not promise filters avoid all computation or make a timing/throughput claim.',
            ['lazy_values_skip_global_level_but_run_before_sink_filters']),
        ('LG-C01', 'consult', '保持消息与附加字段的选项策略',
            'Advise actual opt option composition from all three complete controls. No implementation.',
            ['materials/options.md'], 'advice_no_code_change',
            'opt creates a wrapper using the current invocation options/defaults rather than merging earlier opt arguments. first has empty extra;calling base.opt(raw=True) resets capture to its defaultTrue so second captures attribute;the combined rawTrue/captureFalse call keeps third empty. Specify the intended options together or explicitly reapply them at the chosen wrapper boundary;raw output alone does not mean captured metadata is disabled.',
            ['opt_calls_replace_options_instead_of_merging_previous_values']),
        ('LG-C02', 'consult', '明确记录异常后的业务失败信号',
            'Advise the business return/exception contract from the complete catch controls. No edits.',
            ['materials/failure-signaling.md'], 'advice_no_code_change',
            'Default catch logs and suppresses this exception,returningNone. The explicit default returns rejected; reraiseTrue logs and propagates ValueError. All three log events do not establish identical caller-visible outcomes. Choose an unambiguous result/sentinel or propagation policy appropriate to the caller and test the failure path;do not treat an error log itself as a failed task result or a transaction rollback.',
            ['catch_logging_does_not_by_itself_preserve_failure_signaling']),
        ('LG-P01', 'plan', '规划异步日志任务的有界收尾归属',
            'Plan producer,sink and loop shutdown ordering from the actual event-gated controls. No implementation.',
            ['materials/async-shutdown.md'], 'planned_without_library_change',
            'complete first handles queued synchronous messages and returns an awaitable for coroutine sink tasks in the owning loop. Calling it alone does not release the blocked sink or complete its pending output. Stop/coordinate producers,await the completion in the appropriate loop while it remains live,and only then remove/close the owned sink and loop. Define application deadline/error handling separately;do not claim a built-in deadline,cross-loop completion or external persistence guarantee.',
            ['async_sink_completion_requires_awaiting_in_the_owning_loop']),
        ('LG-D01', 'diagnose', '先核配置与输出再解释替换失败',
            'After a logging configuration replacement fails,the old output disappears and only some new output works. Request complete handler setup/order,the exception and each sink observation before diagnosing. No edits.',
            [], 'diagnosed_or_information_requested',
            'Use only actually consumed configuration and output evidence. Request missing setup/order/exception before choosing a cause. With a complete delivered reproduction,trace configure/remove and sequential add behavior,identify the actual surviving and removed handlers,and advise caller-owned preparation/recovery rather than assume transactional rollback or patch the library. Missing material supports insufficient_information.', None)]
    scenes = [
        ('LG-S01', '日志记录阶段', '核字段和惰性处理顺序', ['LG-U01', 'LG-U02']),
        ('LG-S02', '日志调用策略', '保持选项与业务失败信号', ['LG-C01', 'LG-C02']),
        ('LG-S03', '异步日志收尾', '持有sink和事件循环生命周期', ['LG-P01']),
        ('LG-S04', '日志配置诊断', '核完整替换与失败现场', ['LG-D01'])]
    build_project('loguru', {'title': 'Loguru结构化日志工作场景', 'category': '上下文、调用策略与收尾',
        'description': '字段优先级、惰性时点、选项重置、异常信号、异步收尾和配置诊断六项任务。'},
        definitions, scenes, materials,
        branches={'LG-D01': [{'id': 'complete-handler-reproduction',
            'when': 'The complete handler configuration/order,exception and old/new output observations have not been supplied or declared unavailable,and sufficient evidence is reasonably requested.',
            'materials': ['disclosure/partial-configuration.md']}]},
        extra_entries={'LG-S04': [{'id': 'unavailable', 'task_ids': ['LG-D01'],
            'materials': ['disclosure/unavailable.md']}]})


if __name__ == '__main__':
    main()
