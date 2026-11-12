"""核验固定 ELF 容器、提取源模块并裁剪桥接工作进程的 ICU 展示资源。"""
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import struct
import sys

KERNEL = {
    '.rodata': '9f91e7f58e9adf8fff8c732181cc206d679f1239e4a1ae48a52d20b39dcfa8ff',
    '.bun_builtins': '0f0631ca198344c231782e2b11f1478dee1ef1bc1471633ba9231cf92d00ce9b',
    '.text': '413d169839d53a8d479b7b2002d7a0b8ff8681a57dc53d13beda5ee96022125a',
    '.data': '00366dc1835ad0f8cf830623a4d7eaf04c6c2f2596d6c9f2fe35bdc8c75ced28',
}


def checked(data, offset, size):
    """读取已验证的边界。
    @param data 容器字节。
    @param offset 起点。
    @param size 长度。
    @return 不越界的字节片段。
    """
    if offset < 0 or size < 0 or offset + size > len(data):
        raise ValueError('容器指针越界')
    return data[offset:offset + size]


def sections(data):
    """解析限定为 Linux x64 的 ELF 节目录。
    @param data 完整 ELF。
    @return 节名到偏移及大小的映射。
    """
    if data[:7] != b'\x7fELF\x02\x01\x01' or struct.unpack_from('<H', data, 18)[0] != 62:
        raise ValueError('仅支持已核验的 Linux x64 ELF')
    offset = struct.unpack_from('<Q', data, 40)[0]
    stride, count, names = struct.unpack_from('<HHH', data, 58)
    if stride != 64 or not 0 < count < 128 or names >= count:
        raise ValueError('未知 ELF 节表布局')
    table = [struct.unpack('<IIQQQQIIQQ', checked(data, offset + i * stride, stride)) for i in range(count)]
    strings = checked(data, table[names][4], table[names][5])
    result = {}
    for item in table:
        name = checked(strings, item[0], len(strings) - item[0]).split(b'\0', 1)[0].decode('ascii')
        if name in result:
            raise ValueError('ELF 节名重复')
        if item[1] != 8:
            checked(data, item[4], item[5])
        result[name] = (item[4], item[5])
    return result


def kernel_sections(data):
    """核验构建前后的四个原生节。
    @param data 完整 ELF。
    @return 各原生节 SHA256。
    """
    table = sections(data)
    result = {name: hashlib.sha256(checked(data, *table[name])).hexdigest() for name in KERNEL}
    if result != KERNEL:
        raise ValueError('固定原生内核的节摘要不匹配')
    return result


def extract(source, destination, expected):
    """提取固定来源的可读模块，不携带原版字节码缓存。
    @param source 已固定身份的官方文件。
    @param destination 临时模块目录。
    @param expected 源程序完整 SHA256。
    @return 写入模块与逐项来源清单。
    """
    raw = source.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError('官方源程序校验不匹配')
    kernel_sections(raw)
    section = checked(raw, *sections(raw)['.bun'])
    if len(section) != 163574530 or section[-16:] != b'\n---- Bun! ----\n' or struct.unpack_from('<Q', section)[0] != len(section) - 8:
        raise ValueError('未知 Bun 应用容器布局')
    graph = section[8:]
    limit, offset, size, entry, argv, argv_size, flags = struct.unpack_from('<Q6I', graph, len(graph) - 48)
    if limit != len(graph) - 48 or size != 2511 * 52 or entry != 6 or flags != 0x1bff:
        raise ValueError('未知 Bun 模块表合同')
    checked(graph, argv, argv_size)
    module_data = graph[:limit]
    manifest = []
    seen = set()
    destination.mkdir(parents=True, exist_ok=False)
    for i in range(2511):
        record = struct.unpack('<12I4B', checked(graph, offset + i * 52, 52))
        fields = []
        for j in range(0, 12, 2):
            start, length = record[j:j + 2]
            fields.append(checked(module_data, start, length))
        name = fields[0].decode('utf-8')
        if not name.startswith('/$bunfs/root/'):
            raise ValueError('模块不属于固定根目录')
        relative = name[len('/$bunfs/root/'):]
        parts = PurePosixPath(relative)
        if not relative or parts.is_absolute() or '..' in parts.parts or str(parts) != relative or relative in seen:
            raise ValueError('模块路径越界或重复')
        seen.add(relative)
        encoding, loader, module_format, record_tag = record[12:]
        if encoding not in [0, 1, 2] or loader not in [1, 5, 10, 13] or module_format not in [0, 1] or record_tag not in [0, 1]:
            raise ValueError('未知模块编码或记录标签')
        content = fields[1]
        if encoding == 1:
            content = content.decode('latin-1').encode('utf-8')
        elif encoding == 2:
            content = content.decode('utf-16-le').encode('utf-8')
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        manifest.append({'name': name, 'encoding': encoding, 'loader': loader, 'format': module_format, 'bytes': len(content), 'sha256': hashlib.sha256(content).hexdigest()})
    if manifest[entry]['name'] != '/$bunfs/root/cli':
        raise ValueError('固定官方入口不匹配')
    (destination.parent / 'modules.json').write_text(json.dumps(manifest, ensure_ascii=False))


def prune(source, destination, report):
    """仅裁剪固定工作环境无需的 locale 定制资源。
    @param source 由官方原生内核编译的专用入口。
    @param destination 裁剪后的完整 ELF。
    @param report 元数据报告路径。
    @return 写入保留原生代码的候选及差异摘要。
    """
    raw = source.read_bytes()
    hashes = kernel_sections(raw)
    header, base, dictionary = 1524704, 1524848, 13635856
    if raw[header + 2:header + 4] != b'\xda\x27' or raw[header + 12:header + 16] != b'CmnD' or struct.unpack_from('<I', raw, base)[0] != 3990:
        raise ValueError('ICU 固定目录布局不匹配')
    if hashlib.sha256(checked(raw, dictionary, 131072)).hexdigest() != 'ab8658c8ab8d5eb92f17b7c6625d2b39e19bf27e1752dafe5852522118ff1d01' or struct.unpack_from('<I', raw, dictionary + 131072)[0] != 131072:
        raise ValueError('ICU 共享字典不匹配')
    entries = [struct.unpack_from('<II', raw, base + 4 + i * 8) for i in range(3990)]
    first_data = base + entries[0][1]
    if first_data != 1647104:
        raise ValueError('ICU 数据起点不匹配')
    output = bytearray(raw)
    kept, removed, previous = [], [], ''
    for i, (name_offset, data_offset) in enumerate(entries):
        name = checked(raw, base + name_offset, first_data - base - name_offset).split(b'\0', 1)[0].decode('ascii')
        if not name.startswith('icudt78l/') or name <= previous:
            raise ValueError('ICU 名称目录不匹配')
        previous = name
        start = base + data_offset
        end = base + entries[i + 1][1] if i + 1 < len(entries) else dictionary
        if start < first_data or not start <= end <= dictionary:
            raise ValueError('ICU 数据边界不匹配')
        relative = name.split('/', 1)[1]
        leaf = relative.rsplit('/', 1)[-1]
        stem = leaf[:-4] if leaf.endswith('.res') else ''
        locale = re.fullmatch(r'[a-z]{2,3}(?:_[A-Za-z0-9]+)*', stem)
        retain = not locale or stem in ['root', 'pool', 'res_index', 'en'] or stem.startswith('en_') or relative.startswith('brkitr/')
        if retain:
            kept.append(entries[i])
        else:
            output[start:end] = b'\0' * (end - start)
            removed.append({'name': name, 'bytes': end - start})
    if len(kept) != 801 or len(removed) != 3189 or sum(row['bytes'] for row in removed) != 5839120:
        raise ValueError('ICU 裁剪集合发生变化')
    # 保留项地址不变；只压紧目录，原生指令和所有 Unicode 分词资源保持原字节。
    struct.pack_into('<I', output, base, len(kept))
    output[base + 4:base + 4 + 3990 * 8] = b'\0' * (3990 * 8)
    for i, entry in enumerate(kept):
        struct.pack_into('<II', output, base + 4 + i * 8, *entry)
    for name in ['.text', '.bun_builtins', '.data']:
        if hashlib.sha256(checked(output, *sections(raw)[name])).hexdigest() != hashes[name]:
            raise ValueError('裁剪意外修改了原生代码')
    destination.write_bytes(output)
    destination.chmod(0o755)
    report.write_text(json.dumps({'image_bytes': len(output), 'image_sha256': hashlib.sha256(output).hexdigest(), 'kernel_before': hashes, 'icu_kept': len(kept), 'icu_removed': len(removed), 'zeroed_bytes': 5839120, 'locale_policy': 'root/en、完整字符/规范化及全部 brkitr；LANG=C.UTF-8', 'removed': removed}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    if len(sys.argv) != 5 or sys.argv[1] not in ['extract', 'prune']:
        raise SystemExit('用法：image.py extract 来源 临时模块目录 源SHA256 | prune 输入 输出 报告')
    if sys.argv[1] == 'extract':
        extract(Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4])
    else:
        prune(Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4]))
