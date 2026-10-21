"""制作用户块取消恢复的最小参考、内置异常特判反例和原版公开测试控制。"""
from pathlib import Path
from shutil import copytree


WORKSPACE = Path.cwd() / '.deploy/project-catalog-hundred/stage-01'
TESTS = '''

def test_in_place_recovers_original_after_keyboard_interrupt(tmp_path):
    """文本重写取消必须恢复原字节并传播同一中断。@param tmp_path 临时目录。@return None。"""
    document = Path(str(tmp_path)) / 'document.txt'
    original = '茶\\r\\noriginal\\n'.encode('utf-8')
    document.write_bytes(original)
    interruption = KeyboardInterrupt('synthetic cancellation')
    with pytest.raises(KeyboardInterrupt) as caught:
        with document.in_place(encoding='utf-8') as (reader, writer):
            writer.write('partial')
            raise interruption
    assert caught.value is interruption
    assert document.bytes() == original
    assert reader.closed and writer.closed
    assert not Path(str(document) + '.bak').exists()


def test_in_place_recovers_original_after_system_exit(tmp_path):
    """二进制退出与自定义备份同样恢复原内容。@param tmp_path 临时目录。@return None。"""
    document = Path(str(tmp_path)) / 'document.bin'
    original = b'\\x00\\xff\\r\\noriginal'
    document.write_bytes(original)
    interruption = SystemExit(19)
    with pytest.raises(SystemExit) as caught:
        with document.in_place(mode='rb', backup_extension='.saved') as (reader, writer):
            writer.write(b'partial')
            raise interruption
    assert caught.value is interruption
    assert document.bytes() == original
    assert reader.closed and writer.closed
    assert not Path(str(document) + '.saved').exists()
'''


def main() -> None:
    """严格只改实现和现有公开测试文件，原失败现场独立保留。@return None。"""
    seed = WORKSPACE / 'drafts/projects/path/seed'
    reference = WORKSPACE / 'references/path'
    control = WORKSPACE / 'public-test-controls/path-original'
    wrong = WORKSPACE / 'wrong-candidates/path-builtins-only'
    for directory in (reference, control, wrong):
        if directory.exists():
            raise ValueError('既有参考或反例不能覆盖')
    copytree(seed, reference)
    module = reference / 'library/path/__init__.py'
    original = module.read_text(encoding='utf-8')
    anchor = '        except Exception:\n            # move backup back\n'
    if original.count(anchor) != 1:
        raise ValueError('in_place用户块异常锚点与固定源码不一致')
    module.write_text(original.replace(anchor,
        '        except BaseException:\n'
        '            # 用户块的取消和退出也要先恢复备份，再传播原始异常。\n'), encoding='utf-8')
    tests = reference / 'library/tests/test_path.py'
    tests.write_text(tests.read_text(encoding='utf-8') + TESTS, encoding='utf-8')
    copytree(seed, control)
    (control / 'library/tests/test_path.py').write_bytes(tests.read_bytes())
    copytree(reference, wrong)
    (wrong / 'library/path/__init__.py').write_text(original.replace(anchor,
        '        except (Exception, KeyboardInterrupt, SystemExit):\n'
        '            # 仅特判常见内置异常，故意遗漏其他用户块取消类型。\n'), encoding='utf-8')
    print('Path最小参考、两项公开回归、原版控制和内置异常特判反例已制作。')


if __name__ == '__main__':
    main()
