"""制作真实编码猜测、文本归一化与日志状态任务。"""
from draft_content import build_project


def main() -> None:
    """冻结短样本反例、完整业务控制和只读诊断分支。@return None。"""
    materials = {
        'materials/bom-controls.md': 'For each text,prefix its UTF-8 bytes with EF BB BF. The short text is Café €;the longer control is exactly "The café serves tea every morning. Prices are shown in euros: €5. " repeated6 times. Run from_bytes(raw).best() and inspect encoding,bom,str(match),raw and output(). Separately decode each known-format raw input with utf-8-sig. Explain the actual pinned results,including any short-input misidentification,without assuming a BOM bypasses the entire detection policy. No edits.\n',
        'materials/equivalent-code-pages.md': 'Use raw="café café café".encode("cp1252") and from_bytes(raw,cp_isolation=["cp1252","latin_1"]). Inspect the actual result count,best text,has_submatch and could_be_from_charset. A supplier audit must distinguish the returned leading candidate from proof of the originating code page. No edits or claim that coherence is a calibrated probability.\n',
        'materials/isolation.md': 'Use raw="café".encode("cp1252"). Compare from_bytes(raw,cp_isolation=["utf_8"]).best() with the isolated cp1252 result and raw.decode("cp1252"). The source format contract may explicitly state cp1252;otherwise the bytes alone are only detection evidence. Advise caller handling of no candidate rather than declaring the payload binary or silently deleting it. No edits.\n',
        'materials/output-policy.md': 'Use the UTF-8 bytes of Café — € with cp_isolation=["utf_8"]. Compare str(best),best.output("ascii") and str(best).encode("ascii","strict"). The source docstring says output errors are ignored;inspect actual code and output rather than assume that wording is correct. The destination policy must explicitly choose rejection or accepted character loss. No implementation.\n',
        'materials/xml-plan.md': 'Use the cp1252 bytes of <?xml version="1.0" encoding="windows-1252"?><note>café</note>,with cp_isolation=["cp1252"]. Compare match.raw,str(match) and match.output() decoded as UTF-8. Plan original/derived artifact ownership,encoding provenance,header/content consistency and format-specific semantic validation before a normalized feed is used. An encoding declaration rewrite is not XML validation or signature preservation. No implementation,publication or writes to source files.\n',
        'disclosure/logging-state.md': 'In an isolated process,the application records the charset_normalizer.api logger configuration:level0,with its pre-existing handlers. It calls from_bytes(b"hello",steps=0,explain=True). The pinned call raises ZeroDivisionError while computing a sampling range. Afterwards logger.level is5 and the library explain_handler remains installed;all original handlers remain. Normal explain=False calls may consequently still emit detailed diagnostics. The source exposes this private state for diagnosis;it is not a promised public logger API. The observation restores only the handler added by that call and its previous level before exiting. Diagnose the invalid sampling input and exception cleanup path,and advise caller-owned configuration recovery without deleting unrelated handlers or editing the library.\n',
        'disclosure/unavailable.md': 'The complete byte input/type,detector arguments,exception and before/after logger/handler configuration cannot be supplied. No complete reproduction distinguishes explicit logging configuration from an exception cleanup issue.\n'}
    definitions = [
        ('CN-U01', 'understand', '核BOM线索与短样本误猜边界',
            'Explain the actual complete short/long BOM controls,raw/decoded/output distinctions and known-format decoding boundary. No edits.',
            ['materials/bom-controls.md'], 'explained',
            'The pinned short Café € BOM sample is misidentified as shift_jis_2004 with bomFalse and different decoded text,while raw remains original. The longer control yields UTF-8,bomTrue,correct text and output UTF-8 without its source BOM. BOM priority does not override chaos/selection policy. For the supplied trusted UTF-8-sig source contract,the strict decoder gives the intended text;do not claim generic detection proves original encoding or output byte identity.',
            ['bom_hint_does_not_override_the_full_detection_policy']),
        ('CN-U02', 'understand', '区分合组候选与原始代码页证明',
            'Explain the complete equivalent-decoding result and what it establishes about the supplier encoding. No edits.',
            ['materials/equivalent-code-pages.md'], 'explained',
            'The actual two isolated code pages decode the bytes to the same café text and are grouped into one result with a submatch. could_be_from_charset retains cp1252 and latin_1;the leading encoding is not proof of a unique originating page. Preserve ambiguity/provenance and distinguish plausible decoding from a calibrated probability or supplier-format guarantee.',
            ['equivalent_decodings_are_grouped_without_proving_the_origin']),
        ('CN-C01', 'consult', '正确处理限定编码后的无候选',
            'Advise no-match handling from the complete restricted and known-format controls. No edits.',
            ['materials/isolation.md'], 'advice_no_code_change',
            'UTF-8 isolation yields an empty result and bestNone for these cp1252 bytes,while the cp1252 control and strict known-format decoding give café. The restricted failure does not establish binary data. Guard bestNone,preserve the raw input and choose decoding from an explicit trusted source contract or retain uncertainty;do not silently discard the record or assume an unreported source encoding.',
            ['restricted_no_match_does_not_prove_binary_input']),
        ('CN-C02', 'consult', '明确目标编码的替换或拒绝策略',
            'Advise the destination loss policy using the actual output and strict-encoding controls. No implementation.',
            ['materials/output-policy.md'], 'advice_no_code_change',
            'Current output uses errors=replace,so ASCII output is Caf? ? ?,not silently ignored characters or lossless text. The original decoded string remains Café — €,and strict ASCII encoding raises UnicodeEncodeError. Select and document whether destination loss is acceptable or must fail;do not rely on the stale ignored wording or call a normalized replacement lossless. Existing strict encoding is an available alternative.',
            ['output_reencoding_replaces_unrepresentable_characters']),
        ('CN-P01', 'plan', '规划XML原件与归一化派生物',
            'Plan encoding provenance and semantic acceptance from the complete XML normalization controls. No implementation.',
            ['materials/xml-plan.md'], 'planned_without_library_change',
            'raw retains the original cp1252 bytes and str retains their windows-1252 declaration;UTF-8 output rewrites that declaration to utf-8 and re-encodes café. Preserve original and derived artifacts separately with explicit hashes/format provenance,validate the chosen output header/content and parse/compare required XML semantics before use. Do not claim output alone validates XML,preserves original signatures or provides byte-identical archival data.',
            ['normalized_output_rewrites_the_declared_encoding_without_replacing_raw']),
        ('CN-D01', 'diagnose', '先核失败与日志证据再解释详细日志遗留',
            'Detailed detector logs persist after a failed import attempt. Request the complete input/type,arguments,exception and logger/handler snapshots before diagnosing. No edits.',
            [], 'diagnosed_or_information_requested',
            'Use only actually consumed evidence. Request missing call and before/after logger state before choosing a cause. With a complete delivered reproduction,trace the actual input validation/sampling and explain setup/cleanup paths,distinguish caller input from persistent logging effects,and advise valid arguments plus recovery of caller-owned state without removing unrelated handlers or claiming concurrency guarantees. Unavailable evidence supports insufficient_information;no patch is authorized.', None)]
    scenes = [
        ('CN-S01', '字节识别证据', '保留原件与编码歧义', ['CN-U01', 'CN-U02']),
        ('CN-S02', '导入和输出决策', '显式选择编码与丢失策略', ['CN-C01', 'CN-C02']),
        ('CN-S03', 'XML归一化归属', '分别验原件和派生物', ['CN-P01']),
        ('CN-S04', '日志状态诊断', '核完整失败与配置证据', ['CN-D01'])]
    build_project('charset-normalizer', {'title': 'Charset Normalizer字节导入工作场景',
        'category': '编码证据、转换与日志归属', 'description': 'BOM反例、等价候选、无匹配、字符替换、XML归一化和日志诊断六项任务。'},
        definitions, scenes, materials,
        branches={'CN-D01': [{'id': 'complete-logging-reproduction',
            'when': 'The complete input/type,arguments,exception and before/after logger configuration have not been supplied or declared unavailable,and sufficient evidence is reasonably requested.',
            'materials': ['disclosure/logging-state.md']}]},
        extra_entries={'CN-S04': [{'id': 'unavailable', 'task_ids': ['CN-D01'],
            'materials': ['disclosure/unavailable.md']}]})


if __name__ == '__main__':
    main()
