"""用独立 scratch 镜像验证 Docker COPY/ADD 是否保留内容硬链接。"""

import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import uuid


def main() -> None:
    """构建仅含合成文件的镜像并检查归档，最后只清理本次镜像。@return None。"""
    report = {}
    with tempfile.TemporaryDirectory(prefix='v3-storage-research-') as temporary:
        root = Path(temporary)
        payload = root / 'payload'
        payload.mkdir()
        (payload / 'first.bin').write_bytes(b'v3-storage-research\n' * 65536)
        os.link(payload / 'first.bin', payload / 'second.bin')
        with tarfile.open(root / 'payload.tar', 'w') as archive:
            archive.add(payload, arcname='payload')
        for mode in ('copy', 'add'):
            reference = 'vibebench-storage-research:probe-' + uuid.uuid4().hex
            instruction = 'COPY payload /payload' if mode == 'copy' else 'ADD payload.tar /'
            (root / 'Dockerfile').write_text('FROM scratch\nLABEL vibebench.research="storage-probe"\n' + instruction + '\n')
            try:
                built = subprocess.run(['docker', 'build', '--network=none', '--pull=false', '-q', '-t', reference, str(root)],
                    capture_output=True, text=True, check=True, timeout=60)
                bundle = subprocess.check_output(['docker', 'image', 'save', reference], timeout=30)
                with tarfile.open(fileobj=io.BytesIO(bundle)) as archive:
                    manifest = json.load(archive.extractfile('manifest.json'))
                    entries = []
                    for name in manifest[0]['Layers']:
                        with tarfile.open(fileobj=archive.extractfile(name)) as layer:
                            entries.extend({'name': item.name, 'size': item.size, 'hardlink': item.islnk(),
                                'target': item.linkname} for item in layer if item.name.endswith('.bin'))
                report[mode] = {'hardlinks_preserved': any(item['hardlink'] for item in entries), 'entries': entries,
                    'image_id': built.stdout.strip()}
            finally:
                subprocess.run(['docker', 'image', 'rm', '--no-prune', reference], capture_output=True, text=True, check=False)
    print(json.dumps({'status': 'completed', 'synthetic_only': True, 'network': 'none',
        'production_writes': 0, 'results': report}, ensure_ascii=False))


if __name__ == '__main__':
    main()
