"""制作真实Path文件操作场景，并明确授权一个用户块取消恢复目标。"""
from draft_content import build_project


def main() -> None:
    """生成四场景九任务，保留独立构建许可与最小工程范围。@return None。"""
    reproduction = '''from tempfile import TemporaryDirectory
from path import Path

with TemporaryDirectory() as directory:
    document = Path(directory) / "orders.txt"
    document.write_bytes(b"original\\r\\n")
    try:
        with document.in_place(encoding="utf-8") as (reader, writer):
            writer.write("partial")
            raise KeyboardInterrupt("synthetic cancellation")
    except KeyboardInterrupt:
        pass
    print(document.bytes())
    print(reader.closed, writer.closed)
    reader.close()
    writer.close()
'''
    materials = {
        'materials/line-policy.md': 'In a dedicated temporary directory, write the Unicode value "茶\\r\\nB\\rC\\n" with write_text(..., encoding="utf-8") using default linesep, explicit linesep=None and explicit "\\r\\n". The target runtime is Linux. Compare actual bytes. Separately copy b"\\x00\\xff\\r\\n\\x80\\r\\x00" using existing binary APIs/chunks. No real file may be read or changed.\n',
        'materials/traversal.md': 'Create only a synthetic tree with a.txt, level/b.txt, level/deep/c.txt and skip/secret.txt. Compare glob("**/*.txt") and walkfiles("*.txt"). For a separate inventory, skip the entire skip subtree while retaining all other files with the existing walk generator. Explain whether matching/filtering alone prunes directories and how generator.send return values must be consumed. No symlinks, real directories or unbounded traversal are involved.\n',
        'materials/merge.md': 'In temporary source/target directories, source has same.txt=new, ignored.tmp=temporary and nested/keep.txt=nested; target has same.txt=old and target-only.txt=retain. Call source.merge_tree(target, ignore=shutil.ignore_patterns("*.tmp"), copy_function=an_explicit_copy2_wrapper). Record copied names. The requirement is a merge retaining target-only data, not mirror deletion; do not operate on real directories.\n',
        'materials/cancellation-symptom.md': 'A rewrite was cancelled and the original file content was not available afterward. The API used, exact exception, file modes, backup options and reader/writer lifecycle have not been supplied. Obtain sufficient evidence before attributing the incident.\n',
        'disclosure/cancellation.py': reproduction,
        'disclosure/cancellation-events.md': 'This complete synthetic user-block reproduction uses in_place, text mode and default backup. KeyboardInterrupt propagates to the caller. Before the final explicit cleanup, the new output does not contain the original bytes and both streams remain open; the default backup has been removed. No real file or production operation was used.\n',
        'disclosure/unavailable.md': 'The actual API, exact exception, modes, backup options and stream lifecycle cannot be provided. No equivalent incident reproduction is available.\n',
        'materials/recovery-policy.md': 'Plan recovery boundaries for the existing in_place context. Current successful completion publishes the replacement, ordinary RuntimeError in the user block restores original bytes and propagates, and the supplied cancellation requirement applies to abnormal exits from that same yielded user block. Distinguish it from setup/open failures, hard kill, power loss, fsync durability, cross-device replacement and concurrent writers, none of which is included in this task. No files may be changed for the plan.\n',
        'materials/cancellation.py': reproduction,
        'materials/repair.md': 'Modify only library/path/__init__.py and library/tests/test_path.py. In the yielded in_place user block, all abnormal BaseException exits, including KeyboardInterrupt, SystemExit, GeneratorExit and a custom BaseException subclass, must close both streams, restore the exact original bytes/permissions, remove the temporary backup and propagate the same exception object. Preserve success and ordinary RuntimeError behavior, text/binary modes, custom backup extensions, signatures and original tests. Deliver meaningful public tests failing on the pinned original and passing after repair. Do not broaden to pre-yield setup failures, crash durability, fsync or concurrent-writer policy. All tests must use dedicated temporary files.\n'}
    definitions = [
        ('PA-U01', 'understand', '解释文本换行转换和已有保真选项',
            'Trace the supplied three write_text newline policies on the target Linux runtime. Give actual byte-level differences and explain which existing argument preserves the mixed original newlines. Do not edit files.',
            ['materials/line-policy.md'], 'explained_with_existing_solution',
            'The default normalizes standard newlines to Linux LF; linesep=None preserves the original mixed CRLF/CR/LF, and explicit CRLF normalizes them all to CRLF. UTF-8 handles 茶. Use existing linesep rather than a required library patch and do not generalize Linux byte output to every platform.', ['write_text_line_policy_is_explicit']),
        ('PA-C01', 'consult', '为字节保真选择已有二进制接口',
            'Recommend an existing-API approach for the supplied exact binary-copy requirement, including invalid UTF-8 bytes and mixed newlines. Explain bounded chunking versus text normalization. No implementation or real file access is authorized.',
            ['materials/line-policy.md'], 'advice_no_code_change',
            'Use existing bytes/write_bytes or binary chunks with a binary writer to preserve every byte, including NUL/FF and mixed newlines. Use chunked reads when whole-file memory is unsuitable. Do not decode arbitrary bytes as text or claim text conversion automatically preserves all bytes.', ['binary_chunks_preserve_exact_bytes']),
        ('PA-U02', 'understand', '解释glob双星与递归文件盘点的区别',
            'Trace glob("**/*.txt") and walkfiles("*.txt") on the supplied complete synthetic tree. Explain the actual recursion guarantee and which files each covers. Do not edit files or traverse real paths.',
            ['materials/traversal.md'], 'explained',
            'This Path.glob delegates without recursive=True; ** is not recursive here. It matches the one-level level/b.txt and skip/secret.txt, while walkfiles recursively includes a.txt, those two and level/deep/c.txt. Do not attribute pathlib recursive-glob behavior to this API.', ['glob_double_star_is_not_recursive']),
        ('PA-C02', 'consult', '用已有生成器协议剪枝一棵子树',
            'Meet the supplied inventory requirement to skip the entire skip subtree with current walk capabilities. Explain how to consume generator.send results and why a match filter or sending a bare False is not the same policy. No project files may be changed.',
            ['materials/traversal.md'], 'advice_no_code_change',
            'Iterate walk so each returned directory can receive a callable returning False; the source falls back to is_dir for a falsy sent value, so bare False is not that callable. Consume the item returned by send or it can be lost. Walk all needed directories for pruning, then filter results; matching names alone does not prevent descent. No new walk option or unbounded symlink scan is required.', ['walk_send_can_prune_one_subtree']),
        ('PA-U03', 'understand', '解释目录合并保留目标独有数据',
            'Trace the supplied temporary merge and resulting same.txt, nested/keep.txt, ignored.tmp and target-only.txt. Is this operation a mirror that removes target-only data? Do not edit files.',
            ['materials/merge.md'], 'explained',
            'same.txt becomes new, nested/keep.txt is copied, ignored.tmp is not copied, and target-only.txt remains retain. merge_tree overlays source content and retains target-only files; it is not a deletion/mirror synchronization operation.', ['merge_overwrites_and_retains_target_only']),
        ('PA-C03', 'consult', '复用已有忽略和自定义复制策略',
            'Assess whether the supplied ignore/copy-policy requirements require a new merge_tree feature. Use the actual current parameters and callback behavior, and distinguish any undeclared mirror-deletion policy. No changes or real directory operation are authorized.',
            ['materials/merge.md'], 'advice_no_code_change',
            'The existing ignore callback and copy_function are passed recursively, and the supplied wrapper copies only keep.txt and same.txt. Reuse actual parameters instead of proposing already-present functionality. Retain target-only data for this merge; a separate mirror/deletion requirement would need explicit business boundaries and is not authorized here.', ['existing_ignore_and_copy_function_are_used']),
        ('PA-D01', 'diagnose', '先取重写API和异常时序再判断原文丢失',
            'Investigate the supplied cancellation symptom. Request the actual API, exact exception, modes, backup options and stream lifecycle or a sufficient minimal reproduction. Diagnose only consumed evidence and state the limit if unavailable. Do not edit files.',
            ['materials/cancellation-symptom.md'], 'diagnosed_no_code_change',
            'Initially request sufficient actual rewrite and cancellation evidence without assigning a cause. Relate disclosed behavior to the pinned implementation and distinguish user-block, setup, filesystem and process-lifecycle boundaries. Support only the conclusion established by consumed evidence; unavailable material permits insufficient_information.', None),
        ('PA-P01', 'plan', '界定用户块恢复和持久文件保证',
            'Plan the supplied in_place recovery boundary and acceptance cases. Distinguish ordinary success/error and requested user-block cancellation cleanup from pre-yield setup failures, hard termination, durability and concurrent writers. Do not implement changes.',
            ['materials/recovery-policy.md'], 'planned_with_explicit_boundaries',
            'Define exact byte restoration, stream closure, backup cleanup and same-exception propagation for abnormal yielded-user-block exits while preserving success/RuntimeError and modes/options. Cover acceptance of text/binary and custom backup paths. Do not promise crash atomicity, durability or concurrent-writer safety from this limited cleanup change.', ['normal_success_and_backup_cleanup', 'ordinary_runtime_error_restores_bytes']),
        ('PA-M01', 'modify', '修复用户块取消时的原文件恢复',
            'Implement the explicitly authorized user-block cancellation recovery described in the supplied repair requirements. Preserve all existing behavior and original tests, and add meaningful public regression tests in the authorized existing test file. Modify only the two listed files and use dedicated temporary files.',
            ['materials/cancellation.py', 'materials/repair.md'], 'implemented_and_verified',
            'Every required BaseException from the yielded user block restores the exact original bytes/permissions, closes reader and writer, removes the temporary backup and propagates the same original object. Preserve success, ordinary errors, text/binary and custom extension behavior, signatures and original native tests. Do not implement only a finite tuple of common exceptions or broaden to unrelated crash/setup guarantees.', ['all_user_block_interruptions_restore_bytes', 'same_exception_objects_propagate', 'interrupted_streams_close', 'backup_and_permissions_preserved', 'normal_success_and_backup_cleanup'])]
    scenes = [('PA-S01', '文件格式与字节保真', '用现有文本和二进制接口表达不同保真要求', ['PA-U01', 'PA-C01']),
        ('PA-S02', '目录资产盘点', '区分非递归glob、递归盘点和显式剪枝', ['PA-U02', 'PA-C02']),
        ('PA-S03', '目录内容合并', '保留目标独有内容并复用已有复制策略', ['PA-U03', 'PA-C03']),
        ('PA-S04', '取消时的文件重写恢复', '按实际材料定位并验证明确授权的最小恢复修复', ['PA-D01', 'PA-P01', 'PA-M01'])]
    build_project('path', {'title': 'Path文件处理工作场景', 'category': '文件保真与工作流',
        'description': '固定真实源码上的字节、目录和取消恢复九项独立任务，包含一个授权最小工程修复。'},
        definitions, scenes, materials,
        modifications={'PA-M01': ['library/path/__init__.py', 'library/tests/test_path.py']},
        branches={'PA-D01': [{'id': 'cancellation-evidence', 'when': 'The actual API, exact exception, modes, backup options and stream lifecycle have not been disclosed, the conversation does not say they are unavailable, and the answer reasonably requests a sufficient reproduction.',
            'materials': ['disclosure/cancellation.py', 'disclosure/cancellation-events.md']}]},
        extra_entries={'PA-S04': [{'id': 'diagnose_only', 'task_ids': ['PA-D01']},
            {'id': 'unavailable', 'task_ids': ['PA-D01'], 'materials': ['disclosure/unavailable.md']},
            {'id': 'modify_direct', 'task_ids': ['PA-M01']}]},
        license_files=['seed/app/licenses/LICENSE.path.build.txt'])


if __name__ == '__main__':
    main()
