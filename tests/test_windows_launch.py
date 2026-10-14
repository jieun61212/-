import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock
from scripts.windows_setup import verify_wheels
from scripts.windows_launch import open_when_ready


class WindowsLaunchTests(unittest.TestCase):
    def test_wheel_checksums_and_tampering(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            wheel = root / 'example.whl'; wheel.write_bytes(b'package')
            (root / 'SHA256SUMS.json').write_text(json.dumps({wheel.name: hashlib.sha256(b'package').hexdigest()}))
            verify_wheels(root)
            wheel.write_bytes(b'changed')
            with self.assertRaises(RuntimeError):
                verify_wheels(root)

    def test_extra_wheel_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'SHA256SUMS.json').write_text('{}')
            (root / 'unexpected.whl').write_bytes(b'package')
            with self.assertRaises(RuntimeError):
                verify_wheels(root)

    def test_browser_only_after_functional_health(self):
        opener = Mock(return_value=True)
        with patch('urllib.request.urlopen', return_value=io.BytesIO(b'{"status":"ok","database":"ok"}')):
            self.assertTrue(open_when_ready('http://127.0.0.1:12345', opener=opener))
        opener.assert_called_once_with('http://127.0.0.1:12345')

    def test_browser_not_opened_for_unready_app(self):
        opener = Mock()
        with patch('urllib.request.urlopen', side_effect=OSError('unavailable')):
            self.assertFalse(open_when_ready('http://127.0.0.1:12345', opener=opener, timeout=.01))
        opener.assert_not_called()

    def test_cmd_files_crlf_no_accidental_control_characters(self):
        for name in ['처음 설치.cmd', '프로그램 시작.cmd']:
            data = (Path(__file__).resolve().parents[1] / name).read_bytes()
            self.assertTrue(data.startswith(b'@echo off\r\n'))
            self.assertFalse(any(byte < 32 and byte not in (10,13) for byte in data))
            self.assertNotIn(b'\n', data.replace(b'\r\n', b''))
