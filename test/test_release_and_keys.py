import io
import json
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'desktop'))
from release_install import safe_extract, choose_program
from ai_config import _crypt, api_error


class ReleaseTests(unittest.TestCase):
    def test_portable_archive_extracts_and_selects_program_without_executing(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); archive=root/'app.zip'
            with zipfile.ZipFile(archive,'w') as bundle:
                bundle.writestr('app.exe',b'MZfixture'); bundle.writestr('helper.exe',b'MZfixture')
            destination=safe_extract(archive,root/'unpacked')
            self.assertEqual(choose_program(destination,'app').name,'app.exe')

    def test_path_escape_windows_drives_and_streams_are_rejected(self):
        for name in ['../outside.exe','C:/outside.exe','folder/file:stream.exe','/absolute.exe','..\\outside.exe']:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary); archive=root/'bad.zip'
                with zipfile.ZipFile(archive,'w') as bundle:bundle.writestr(name,b'fixture')
                with self.assertRaises(ValueError):safe_extract(archive,root/'unpacked')
                self.assertFalse((root/'unpacked').exists())

    def test_ambiguous_program_is_not_chosen_at_random(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            (root/'one.exe').write_bytes(b'MZ'); (root/'two.exe').write_bytes(b'MZ')
            self.assertIsNone(choose_program(root,'unknown'))

    @unittest.skipUnless(os.name=='nt','Windows DPAPI')
    def test_ai_key_is_encrypted_for_current_windows_user(self):
        raw=b'sk-fixture-not-a-real-key'
        encrypted=_crypt(raw)
        self.assertNotIn(raw,encrypted)
        self.assertEqual(_crypt(encrypted,True),raw)

    def test_common_api_errors_explain_configuration_or_balance(self):
        self.assertIn('Key',api_error(401)); self.assertIn('余额',api_error(402)); self.assertIn('模型',api_error(404))


if __name__=='__main__':unittest.main()
