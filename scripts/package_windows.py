"""Package source and Windows wheels, excluding local data and credentials."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
MODULES = ['app', 'config', 'content_generator', 'exporter', 'lawfirm_profiles',
           'pdf_analyzer', 'project_rules', 'prompt_builder', 'validator', 'scripts', 'tests']
FILES = ['README.md', 'AGENTS.md', 'requirements.txt', 'requirements.lock',
         'requirements-windows.lock', 'requirements-dev.txt', '처음 설치.cmd', '프로그램 시작.cmd', '윈도우_사용방법.txt']


def build(wheels, output):
    wheel_files = sorted(wheels.glob('*.whl'))
    if len(wheel_files) < 20:
        raise ValueError('윈도우용 의존성 파일이 부족합니다.')
    files = [ROOT / name for name in FILES]
    for folder in MODULES:
        files.extend(p for p in (ROOT / folder).rglob('*') if p.is_file()
                     and '__pycache__' not in p.parts and p.suffix in {'.py', '.json', '.md', '.js', '.css', '.html', '.sh'})
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as bundle:
        for file in sorted(files):
            bundle.write(file, 'legal-blog-windows/' + file.relative_to(ROOT).as_posix())
        for file in wheel_files:
            bundle.write(file, 'legal-blog-windows/windows_packages/' + file.name)
        manifest = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in wheel_files}
        bundle.writestr('legal-blog-windows/windows_packages/SHA256SUMS.json', json.dumps(manifest, indent=2))
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix('.sha256.txt').write_text(digest + '  ' + output.name + '\n')
    return len(files), len(wheel_files), output.stat().st_size


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--wheels', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    arguments = parser.parse_args()
    print(build(arguments.wheels, arguments.output))
