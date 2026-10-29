"""制作合成日历的时间语义、属性保真和重复日程接入任务。"""
import json
from pathlib import Path

from draft_content import build_project


def main() -> None:
    """冻结六项本地日历业务判断，不接入真实账户或服务。@return None。"""
    rows = [
        ('IC-U01', 'understand', '解释全天事件的日期和结束边界', 'Create Event with DTSTART=date(2026,10,22). Inspect inferred end,then add DTEND=date(2026,10,23),serialize/reparse and inspect native date type and duration. Explain inclusive start/non-inclusive end from the supplied Event contract. No edits.',
            'DATE serializes with VALUE=DATE and reparses as date. The default end for this start-only date event is the next date;an explicit October23 DTEND describes one day October22 because end is exclusive. Preserve date type and matching DATE end semantics;do not turn it into a midnight UTC instant or count the end date as another occupied day.', 'all_day_date_events_use_an_exclusive_next_date_end'),
        ('IC-U02', 'understand', '解释日历TEXT的转义与往返', 'Set SUMMARY to the exact literal "计划,项目;路径\\test" followed by a newline and "说明". Serialize Event to bytes and reparse. Explain Unicode,comma,semicolon,backslash,newline and CRLF handling. No edits.',
            'TEXT serialization escapes comma,semicolon,backslash and newline using the calendar grammar,uses UTF-8 bytes and CRLF content lines,and the parsed summary restores the original Unicode text. Use the property encoder rather than hand-concatenating raw content lines. This preserves this property control,not arbitrary original file formatting or byte-for-byte roundtrip.', 'calendar_text_escaping_roundtrips_the_actual_unicode_and_delimiters'),
        ('IC-C01', 'consult', '保留多个参与者及各自参数', 'Add a vCalAddress mailto:a@example.invalid with ROLE=REQ-PARTICIPANT as attendee,then add mailto:b@example.invalid using ATTENDEE. Compare property shape before/after,case-insensitive lookup and serialized/reparsed per-value parameters. Advise an import representation. No implementation.',
            'One attendee is scalar;adding another appends into a list rather than replacing it. Lookup is case insensitive and the first value retains its own ROLE parameter. Normalize scalar/list handling at the caller boundary while preserving each participant and parameters;do not overwrite the first attendee or flatten parameterized properties into one string.', 'repeated_properties_preserve_multiple_values_and_per_value_parameters'),
        ('IC-C02', 'consult', '区分浮动时间、命名时区和UTC', 'Serialize/reparse DTSTART for2026-10-22 09:00 as naive datetime,Europe/Berlin aware datetime and UTC aware datetime. Compare content-line forms and decoded offsets. Advise cross-user scheduling input. No edits.',
            'Naive input produces a floating DTSTART without Z/TZID and decodes without tzinfo. Berlin uses TZID=Europe/Berlin and this date resolves to+02:00;UTC uses trailing Z and zero offset. These09:00 wall values do not all identify the same instant. Choose the intended representation,retain zone definitions/context and ambiguity policy,and do not infer a viewer or server timezone for floating values.', 'floating_named_zone_and_utc_datetime_representations_have_distinct_meanings'),
        ('IC-P01', 'plan', '规划重复日程的展开与身份', 'A synthetic Calendar holds one VEVENT with UID=recurrence-local-001,UTC DTSTART2026-01-01 09:00,RRULE FREQ=DAILY;COUNT=3 and fixed DTSTAMP. Compare walk("VEVENT") count with the rule count. Plan occurrence display/import,windowing,exception identity and validation. No implementation or real calendar access.',
            'walk returns the one stored VEVENT component,not three expanded occurrences;RRULE COUNT remains[3]. Select and validate an explicit recurrence-expansion strategy with bounded time windows/counts,timezone/DST rules,RDATE/EXDATE,RECURRENCE-ID overrides and stable UID plus recurrence identity. Keep source components and exceptions separately;do not duplicate the master component three times or claim walk already expands it.', 'walking_a_recurring_event_returns_the_stored_component_not_expanded_occurrences')]
    definitions, materials, answers = [], {}, {}
    outcomes = {'understand': 'explained', 'consult': 'advice_no_code_change', 'plan': 'planned_without_library_change'}
    for identifier, kind, title, prompt, requirement, field in rows:
        path = 'materials/' + identifier.lower() + '.md'
        materials[path] = prompt + '\n'
        definitions.append((identifier, kind, title, prompt, [path], outcomes[kind], requirement, [field]))
        answers[identifier] = requirement + ' No changes were made;all data is synthetic and no calendar account was accessed.'
    definitions.append(('IC-D01', 'diagnose', '诊断设置时长后DTEND为何消失', 'A calendar export loses an explicit DTEND after editing duration. Request complete property mutation order,typed start/end/duration and serialized before/after controls. No edits.', [], 'diagnosed_or_information_requested',
        'Use consumed property-setter evidence to distinguish a representation change from loss of the computed end. Missing controls support insufficient_information. Do not restore mutually competing end representations or patch serialization without an explicit new contract.', None))
    materials['disclosure/duration-setter.md'] = 'Synthetic Event initially has start=UTC2026-01-01 09:00 and end=UTC10:00,serialized as DTSTART and DTEND. Set event.duration=timedelta(hours=2). It serializes DTSTART09:00Z and DURATION:PT2H with no DTEND;event.end computes UTC11:00 and duration is2 hours. The documented duration setter keeps start locked,removes explicit DTEND and stores DURATION. No other mutation or remote calendar is involved.\n'
    materials['disclosure/unavailable.md'] = 'Mutation order,typed start/end/duration and serialized before/after controls are unavailable.\n'
    answers.update({'IC-D01-question': 'Please provide the complete property mutation order,typed start/end/duration and serialized before/after controls. I need the actual setter and representation evidence;no edits are authorized.',
        'IC-D01': 'The duration setter deliberately keeps start locked,removes the explicit DTEND property and stores DURATION. The supplied computed11:00 end proves the end semantics remain available;this is a representation change rather than evidence of lost duration. Choose and test one supported end representation at the caller boundary. Do not reinsert competing DTEND and DURATION or patch the serializer from this symptom. No changes were made.',
        'IC-D01-unavailable': 'The mutation/type/serialization controls are unavailable. Record insufficient_information and request them later;no exact cause is established. No edits.'})
    build_project('collective-icalendar', {'title': 'Icalendar日程接入工作场景', 'category': '日期、属性与重复日程',
        'description': '全天结束边界、TEXT转义、参与者参数、时间表示、重复日程方案及时长表示诊断。'}, definitions,
        [('IC-S01', '日历值语义', '保留日期类型和文本内容', ['IC-U01', 'IC-U02']),
         ('IC-S02', '日程接入咨询', '明确参与者和时间表示', ['IC-C01', 'IC-C02']),
         ('IC-S03', '重复日程方案', '界定展开、例外和身份', ['IC-P01']),
         ('IC-S04', '结束表示诊断', '核对实际属性修改顺序', ['IC-D01'])], materials,
        branches={'IC-D01': [{'id': 'duration-representation', 'when': 'Mutation order,typed values and before/after controls have not been supplied or declared unavailable and are reasonably requested.', 'materials': ['disclosure/duration-setter.md']}]},
        extra_entries={'IC-S04': [{'id': 'unavailable', 'task_ids': ['IC-D01'], 'materials': ['disclosure/unavailable.md']}]})
    Path(__file__).with_name('collective-icalendar-answers.json').write_text(json.dumps(answers, indent=2) + '\n')


if __name__ == '__main__':
    main()
