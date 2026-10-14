"""Start the local app on a free port and open the browser only after readiness."""
import json
import os
from pathlib import Path
import socket
import sys
import threading
import time
import urllib.request
import webbrowser

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def open_when_ready(address, opener=webbrowser.open, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(address + '/api/health', timeout=1) as response:
                result = json.load(response)
            if result.get('status') == 'ok' and result.get('database') == 'ok':
                return opener(address)
        except (OSError, ValueError):
            pass
        time.sleep(.2)
    print('브라우저를 열지 못했습니다. 이 창의 오류 메시지를 확인해 주세요.')
    return False


def main():
    os.chdir(ROOT)
    import uvicorn
    # A new free port avoids killing or reusing an unrelated local service.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(('127.0.0.1', 0))
        address = 'http://127.0.0.1:' + str(listener.getsockname()[1])
        threading.Thread(target=open_when_ready, args=(address,), daemon=True).start()
        print('법률 원고 스튜디오를 시작합니다. 브라우저가 자동으로 열립니다.')
        print('사용 중에는 이 창을 열어 두세요. 종료하려면 Ctrl+C를 누르세요.')
        config = uvicorn.Config('app.main:app', access_log=False, log_level='warning')
        uvicorn.Server(config).run(sockets=[listener])


if __name__ == '__main__':
    main()
