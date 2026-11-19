"""使用真实Docker白名单和镜像自身代码验证AGY打包，所有模型入口关闭。"""
import argparse
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import manage
from agy_auth import SOURCE_BYTES, SOURCE_SHA256
from verify_agy_images import verify_images


def main() -> None:
    """构建隔离镜像并核对实际包。@return 无；任何失败保持非零。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path.cwd()
    args.output.mkdir(parents=True, exist_ok=True)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    names = {role: f'flower2api-ci-artifact-{role}:v3-package-check' for role in ('control', 'account')}
    with tempfile.TemporaryDirectory(prefix='agy-image-context-') as temporary:
        context = Path(temporary)
        shutil.copytree(root / 'services/orchestrator', context / 'orchestrator', ignore=manage.source_snapshot_ignore)
        (context / 'agy-auth').mkdir()
        os.link(args.binary.resolve(), context / 'agy-auth/agy-1.5.9')
        ignore = (root / 'images/v3/Dockerfile.dockerignore').read_text()
        old = ignore.replace('!agy-auth\n!agy-auth/agy-1.5.9\n!agy-auth/agy-auth-unavailable\n', '')
        (context / 'Probe.Dockerfile').write_text('FROM scratch\nCOPY agy-auth/ /agy-auth/\n')
        (context / 'Probe.Dockerfile.dockerignore').write_text(old)
        rejected = subprocess.run(['docker', 'build', '-f', str(context / 'Probe.Dockerfile'), str(context)],
            text=True, capture_output=True)
        (args.output / 'old-context.log').write_text(rejected.stdout + rejected.stderr)
        if rejected.returncode == 0 or 'agy-auth' not in rejected.stderr:
            raise ValueError('原白名单遗漏未被真实Docker复现')
        (context / 'Probe.Dockerfile.dockerignore').write_text(ignore)
        (context / 'images/v3').mkdir(parents=True)
        for name in ('Dockerfile', 'Dockerfile.dockerignore'):
            shutil.copyfile(root / 'images/v3' / name, context / 'images/v3' / name)
        compiler = 'flower2api-ci-artifact-runtime-build:v3-package-check'
        with (args.output / 'runtime-build.log').open('w') as log:
            subprocess.run(['docker', 'build', '--target', 'agy-runtime-build',
                '-f', str(context / 'images/v3/Dockerfile'), '-t', compiler, str(context)],
                stdout=log, stderr=subprocess.STDOUT, check=True)
        lines = []
        for role, base in [('account', 'flower2api-agy-auth:task-smoke'),
                ('control', 'ghcr.io/silentflower/flower2api-control:v3-portability-check-20261119')]:
            lines += [f'FROM {base} AS {role}', 'ENV PYTHONDONTWRITEBYTECODE=1']
            if role == 'account':
                lines += ['COPY agy-auth/ /usr/local/bin/',
                    'COPY orchestrator/agy_runtime/ /opt/v3/python/agy_runtime/',
                    'COPY orchestrator/runtime_files.py /usr/local/bin/',
                    f'COPY --from={compiler} /opt/v3/python/agy_runtime/ /opt/v3/python/agy_runtime/']
            else:
                lines += ['COPY orchestrator/ /app/']
            lines += [f'LABEL vibebench.product="v3" vibebench.role="{role}" vibebench.release="package-check"',
                f'LABEL vibebench.parent-revision="{revision}" vibebench.gateway-revision="{revision}"',
                f'LABEL vibebench.agy-runtime-protocol="1" vibebench.agy-runtime-source-sha256="{SOURCE_SHA256}"',
                f'LABEL vibebench.agy-auth-source-sha256="{SOURCE_SHA256}"']
        (context / 'Probe.Dockerfile').write_text('\n'.join(lines) + '\n')
        for role in names:
            with (args.output / (role + '-build.log')).open('w') as log:
                subprocess.run(['docker', 'build', '--target', role, '-f', str(context / 'Probe.Dockerfile'),
                    '-t', names[role], str(context)], stdout=log, stderr=subprocess.STDOUT, check=True)
    manifest = {'schema': 3, 'layout_version': 1, 'release': 'package-check',
        'parent_revision': revision, 'gateway_revision': revision,
        'agy_auth': {'available': True, 'source_version': '1.5.9', 'bytes': SOURCE_BYTES, 'sha256': SOURCE_SHA256},
        'images': {role: {'reference': name, 'digest': json.loads(subprocess.check_output(
            ['docker', 'image', 'inspect', name], text=True))[0]['Id']} for role, name in names.items()}}
    path = args.output / 'manifest.json'
    path.write_text(json.dumps(manifest, indent=2) + '\n')
    result = verify_images(path)
    result['old_context_rejected'] = True
    result['scope'] = '当前源码与真实白名单的隔离镜像；正式完整镜像另由CI验收'
    (args.output / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
