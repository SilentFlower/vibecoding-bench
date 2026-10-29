"""保留固定源码历史实际构建的Rust原件，不声称本轮重新编译。"""
from hashlib import sha256
import json
from pathlib import Path
from shutil import copyfile
from subprocess import check_output


def main() -> None:
    """校来源、安装原件和解释器ABI后准备只读项目完整原生入口。@return None。"""
    root, research = Path.cwd(), Path(__file__).resolve().parent
    work = root / '.deploy/project-catalog-hundred/stage-03'
    item = next(row for row in json.loads((research/'source-index.json').read_text())['projects'] if row['slug'] == 'pendulum')
    source = root / item['historical_checkout']
    if check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip() != item['revision']:
        raise ValueError('固定源码提交不符')
    historical = source.parent
    install = historical/'installation-result.json'
    evidence = json.loads(install.read_text())
    if evidence['return_code'] != 0 or evidence['source_commit'] != item['revision'] or not evidence['python'].startswith('3.12.'):
        raise ValueError('原构建来源或Python ABI不符')
    relative = 'src/pendulum/_pendulum.cpython-312-x86_64-linux-gnu.so'
    binary = source/relative
    if binary.is_symlink() or not binary.is_file() or not binary.read_bytes().startswith(b'\x7fELF'):
        raise ValueError('缺少原实际ELF扩展')
    project = work/'drafts/projects/pendulum'
    destination = project/'seed/library'/relative
    if destination.exists():
        raise ValueError('拒绝覆盖生成物')
    copyfile(binary,destination)
    destination.chmod(0o755)
    for name in ('babel-2.18-LICENSE.txt','babel-2.18-LICENSE.unicode.txt'):
        copyfile(historical/name,project/'seed/app'/name)
    row = {'path':relative,'sha256':sha256(binary.read_bytes()).hexdigest(),'size':binary.stat().st_size,
        'git_mode':None,'git_blob':None,'snapshot_mode':'100755','representation':'preserved-upstream-generated-runtime-file'}
    inputs = {path:sha256((source/path).read_bytes()).hexdigest() for path in ('pyproject.toml','rust/Cargo.toml','rust/Cargo.lock')}
    record = {'project':'pendulum','source_commit':item['revision'],'files':[row],'file_count':1,
        'origin':{'installation_result':str(install.relative_to(root)),'installation_result_sha256':sha256(install.read_bytes()).hexdigest(),
            'install_log_sha256':sha256((historical/'install.log').read_bytes()).hexdigest(),'build_input_sha256':inputs,
            'abi':'CPython3.12-linux-x86_64','version':'3.3.0'},'rebuilt_in_current_run':False,
        'scope':'只读场景固定原版Rust运行原件；当前目标镜像完整扩展及Python集合另验，不是修改候选重新构建合同'}
    target = research/'pendulum-generated-runtime-files.json'
    if target.exists():
        raise ValueError('拒绝覆盖来源原件')
    target.write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
    proof_path = work/'source-proofs/pendulum.json'
    proof = json.loads(proof_path.read_text())
    proof.update(generated_files=[row],generated_provenance={'path':str(target.relative_to(root)),'sha256':sha256(target.read_bytes()).hexdigest()})
    proof_path.write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n')
    profile_path = work/'drafts/environments/pendulum-py312/profile/profile.json'
    profile = json.loads(profile_path.read_text());profile['regression']={'timeout_sec':180,'memory_mb':768,'pids_limit':128}
    profile_path.write_text(json.dumps(profile,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'project':'pendulum','runtime_sha256':row['sha256'],'rebuilt_in_current_run':False}))


if __name__ == '__main__':
    main()
