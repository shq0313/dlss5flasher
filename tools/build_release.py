"""Allowlisted source snapshot and portable candidate; no upload operation."""
from __future__ import annotations
import hashlib
import json
import shutil
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP = {'__pycache__', '.git', 'direct_url.json'}
SOURCE_FILES = ('README.md', 'LICENSE', 'THIRD_PARTY_NOTICES.md', '.gitignore',
                'requirements.txt', 'requirements-lock.txt', 'launch.py', '启动.bat',
                'docs/依赖源码说明.md', 'tools/build_release.py')
SOURCE_TREES = ('app', 'native', 'tests', 'licenses')
RUNTIME_FILES = ('runtime/dlssnr_host_v2.dll', 'runtime/RTX-Video/vsr_host.dll',
                 'runtime/RTX-Video/nvngx_vsr.dll')

def copy_file(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)

def copy_tree(source, destination):
    for path in sorted(source.rglob('*')):
        rel = path.relative_to(source)
        if path.is_file() and not any(p in SKIP for p in rel.parts) and path.suffix not in {'.pyc', '.pdb', '.obj', '.lib'}:
            copy_file(path, destination / rel)

def digest(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def audit_and_zip(tree, destination):
    manifest = []
    for path in sorted(tree.rglob('*')):
        if not path.is_file() or path.name == 'MANIFEST.json':
            continue
        rel = path.relative_to(tree)
        if path.name.lower() in {'nvngx_dlssnr.dll', 'nvngx.dll_dlssnr.dll', '30.zip', '40.zip', '50.zip', 'settings.local.json', 'startup-error.log'}:
            raise RuntimeError(f'Excluded file: {rel}')
        if any(p.lower() in {'backups', '.work', 'output', '.git'} for p in rel.parts):
            raise RuntimeError(f'Excluded directory: {rel}')
        manifest.append({'path': rel.as_posix(), 'bytes': path.stat().st_size, 'sha256': digest(path)})
    (tree / 'MANIFEST.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    with zipfile.ZipFile(destination, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(tree.rglob('*')):
            if path.is_file():
                archive.write(path, Path('dlss5flasher') / path.relative_to(tree))
    with zipfile.ZipFile(destination) as archive:
        bad = archive.testzip()
        if bad:
            raise RuntimeError(f'ZIP CRC failed: {bad}')
    return {'name': destination.name, 'bytes': destination.stat().st_size,
            'sha256': digest(destination), 'files': len(manifest) + 1}

def main():
    target = ROOT / 'release' / datetime.now().strftime('%Y%m%d-%H%M%S')
    target.mkdir(parents=True, exist_ok=False)
    source = target / 'source'
    for rel in SOURCE_FILES:
        copy_file(ROOT / rel, source / rel)
    for rel in SOURCE_TREES:
        copy_tree(ROOT / rel, source / rel)
    portable = target / 'portable' / 'dlss5flasher'
    copy_tree(source, portable)
    for rel in ('python_embeded', 'ffmpeg-8.0.1-full_build'):
        copy_tree(ROOT / rel, portable / rel)
    for rel in RUNTIME_FILES:
        copy_file(ROOT / rel, portable / rel)
    placeholder = portable / 'runtime/DLSS-NR/1.3/bin/放置NR运行库.txt'
    placeholder.parent.mkdir(parents=True, exist_ok=True)
    placeholder.write_text('自行准备适配显卡的 nvngx_dlssnr.dll，放在本目录。\n也可点击右上角“运行库”选择 DLL。发布包不包含此文件。\n', encoding='utf-8')
    report = {'status': 'local-candidate-not-published', 'binary_redistribution_review': 'pending-see-docs', 'artifacts': []}
    for tree, name in ((source, 'dlss5flasher-source.zip'), (portable, 'dlss5flasher-windows-x64-candidate.zip')):
        report['artifacts'].append(audit_and_zip(tree, target / name))
    (target / 'release-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    (target / 'SHA256SUMS.txt').write_text(''.join(f"{a['sha256']}  {a['name']}\n" for a in report['artifacts']), encoding='utf-8')
    print(target)
    print(json.dumps(report, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
