"""制作固定5.2版本的字节检测状态和归档任务。"""
from draft_content import build_project


def main() -> None:
    """冻结六项独立编码任务，不引用未接入的后续重写接口。@return None。"""
    materials = {
        'materials/ascii.md': 'Detect b"plain text" and compare strict decoding with ascii,utf-8 and cp1252. Explain actual encoding/confidence output and whether it uniquely establishes the original source encoding. No edits.\n',
        'materials/early-done.md': 'Feed one UniversalDetector with codecs.BOM_UTF8+b"hello";inspect done/result. Feed a later b"\\xff" and close(). Separately strict-decode the entire concatenated bytes as utf-8-sig. Explain detector early stopping versus complete-stream validation. No edits.\n',
        'materials/reset.md': 'On one detector,feed UTF8 BOM+hello and close. Without resetting,feed plain text and close again. Then reset(),feed plain text and close. Advise the lifetime for independent imported documents and inspect every result. No implementation.\n',
        'materials/codec-label.md': 'detect(b"\\xfe\\xff\\x00\\x00") returns a detected unusual UCS4 label. Inspect that exact label and codecs.lookup(label). Advise an explicit supported-decoder/error boundary;do not rename it to UTF-32 without proving its octet order. No edits.\n',
        'materials/archive-plan.md': 'The original bytes are b"Caf\\xe9". Both latin-1 and cp1252 strictly decode to Café and encode back to the same bytes. Plan an archive that preserves original bytes,source encoding metadata/detector settings and uncertainty,strict decoder outcomes and normalized text separately. A round trip or confidence score alone cannot prove the original encoding. No real file writes or implementation.\n',
        'disclosure/chunked-bom.md': 'Complete fresh inputs are codecs.BOM_UTF8+"Hello café".encode(). detect on the whole bytes returns UTF-8-SIG/confidence1. A fresh UniversalDetector receives each byte as a one-byte chunk and close returns utf-8/confidence0.7525. No detector reuse or input byte change occurs. The pinned5.2 implementation checks the BOM only in its first nonempty feed call,which receives only EF here. Explain the chunk-boundary effect and an explicitly tested buffering/decoding policy without claiming all encodings or chunkings are fixed. No source repair is authorized.\n',
        'disclosure/unavailable.md': 'The complete original bytes,chunk boundaries,detector version/reset/feed/close sequence and whole-input control cannot be supplied.\n'}
    definitions = [
        ('CD-U01', 'understand', '界定ASCII检测置信度', 'Explain actual detection and all strict decoding controls. No edits.', ['materials/ascii.md'], 'explained',
            'The ASCII-only input is reported ascii/confidence1,but ascii,UTF8 andcp1252 all decode those same bytes identically. This is compatible evidence,not unique original-encoding provenance or a calibrated probability about a source system.', ['ascii_confidence_does_not_identify_the_original_encoding']),
        ('CD-U02', 'understand', '区分检测完成和全流字节有效', 'Explain every early-done and whole-stream decoding result. No edits.', ['materials/early-done.md'], 'explained',
            'BOM detection sets doneTrue and UTF-8-SIG immediately. Later feed is ignored and close retains that result,while strict decoding the complete concatenated stream rejectsFF. Early prediction completion does not validate every later byte;retain complete-byte decoding/error checks separately.', ['early_detector_done_does_not_validate_the_complete_byte_stream']),
        ('CD-C01', 'consult', '明确跨文档检测器的重置', 'Advise actual reused/reset detector controls. No implementation.', ['materials/reset.md'], 'advice_no_code_change',
            'Feeding a new document after completion without reset keeps the prior UTF-8-SIG result because done stops processing. reset clears state and the new plain text is detected ascii. Use a fresh detector or reset between independent documents and finalize each one explicitly.', ['detector_reuse_requires_reset_between_independent_documents']),
        ('CD-C02', 'consult', '处理检测标签与解码器不兼容', 'Advise the exact detected label and Python codec lookup failure. No edits.', ['materials/codec-label.md'], 'advice_no_code_change',
            'The exact label is X-ISO-10646-UCS-4-3412;codecs.lookup raises LookupError. A recognized detection label need not name an available Python codec. Preserve bytes/label and report unsupported decoding or use an explicitly verified order-aware decoder;do not substitute ordinary UTF32 without proof.', ['a_detected_encoding_label_may_not_name_a_python_codec']),
        ('CD-P01', 'plan', '规划保留编码歧义的文本归档', 'Plan separate original-byte,encoding-evidence and decoded-text records. No implementation.', ['materials/archive-plan.md'], 'planned_without_library_change',
            'Both latin1 andcp1252 produce Café and round-trip the exact supplied bytes,so those controls cannot select original encoding. Preserve immutable original bytes and source metadata,detector version/settings/chunking,label/confidence and uncertainty;record strict decoding outcomes and normalized text separately. Define unsupported/error/manual policies without treating confidence or roundtrip as source provenance.', ['identical_decodings_can_leave_source_encoding_ambiguous']),
        ('CD-D01', 'diagnose', '诊断分块检测与整份结果不同', 'Whole-input and chunked encoding detection disagree. Request original bytes,boundaries,version/reset/feed/close order and complete controls before diagnosing. No edits.', [], 'diagnosed_or_information_requested',
            'Use only actually consumed byte/chunk/lifecycle evidence. Request missing complete controls,trace the exact version state/initial-prefix behavior when established,and propose a tested caller-level buffering/decoding policy within scope. Missing evidence supports insufficient_information. No source patch or universal chunk-independence guarantee is authorized.', None)]
    scenes = [('CD-S01', '检测结果的含义', '明确置信和完整字节验收', ['CD-U01', 'CD-U02']),
        ('CD-S02', '检测生命周期与解码', '重置状态并核codec', ['CD-C01', 'CD-C02']),
        ('CD-S03', '文本归档方案', '保留原件和编码歧义', ['CD-P01']),
        ('CD-S04', '分块检测诊断', '核完整字节和状态证据', ['CD-D01'])]
    build_project('chardet', {'title': 'Chardet5.2字节检测工作场景', 'category': '检测状态、解码与归档证据',
        'description': 'ASCII歧义、提前完成、重置、codec兼容、原件归档和分块诊断。'}, definitions, scenes, materials,
        branches={'CD-D01': [{'id': 'complete-chunked-bom',
            'when': 'Complete original bytes,chunk boundaries,version/reset/feed/close order and whole-input control have not been supplied or declared unavailable,and are reasonably requested.',
            'materials': ['disclosure/chunked-bom.md']}]},
        extra_entries={'CD-S04': [{'id': 'unavailable', 'task_ids': ['CD-D01'], 'materials': ['disclosure/unavailable.md']}]})


if __name__ == '__main__':
    main()
