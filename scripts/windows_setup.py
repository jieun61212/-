"""Install the bundled, checksum-verified Windows Python 3.12 wheels."""
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import venv

ROOT = Path(__file__).resolve().parents[1]


def verify_wheels(directory):
    manifest = json.loads((directory / 'SHA256SUMS.json').read_text('utf-8'))
    if set(manifest) != {p.name for p in directory.glob('*.whl')}:
        raise RuntimeError('설치 파일 목록이 일치하지 않습니다. ZIP 파일을 다시 받아 주세요.')
    for name, expected in manifest.items():
        if Path(name).name != name or not name.endswith('.whl'):
            raise RuntimeError('잘못된 설치 파일 목록입니다.')
        if hashlib.sha256((directory / name).read_bytes()).hexdigest() != expected:
            raise RuntimeError('설치 파일이 손상됐습니다. ZIP 파일을 다시 받아 주세요.')


def main():
    if sys.platform != 'win32' or sys.version_info[:2] != (3, 12) or struct.calcsize('P') != 8:
        raise RuntimeError('Windows용 Python 3.12 (64비트)가 필요합니다.')
    os.chdir(ROOT)
    wheels = ROOT / 'windows_packages'
    verify_wheels(wheels)
    environment = ROOT / '.venv'
    python = environment / 'Scripts/python.exe'
    if not python.exists():
        venv.EnvBuilder(with_pip=True).create(environment)
    subprocess.run([str(python), '-m', 'pip', 'install', '--disable-pip-version-check',
                    '--no-index', '--find-links', str(wheels), '-r', str(ROOT / 'requirements-windows.lock')], check=True)
    subprocess.run([str(python), '-m', 'pip', 'check'], check=True)
    print('\n설치 완료! 이제 프로그램 시작.cmd를 더블클릭하세요.')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('\n설치 실패:', str(error))
        sys.exit(1)
