import sys
import unittest
from unittest.mock import patch
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'desktop'))
from network_config import engine_environment


class NetworkConfigTest(unittest.TestCase):
    def test_windows_proxy_and_loopback(self):
        env = engine_environment({}, {'http':'http://127.0.0.1:12345', 'https':'http://127.0.0.1:12345'})
        self.assertEqual(env['HTTPS_PROXY'], 'http://127.0.0.1:12345')
        self.assertEqual(env['NODE_USE_ENV_PROXY'], '1')
        self.assertIn('127.0.0.1', env['NO_PROXY'])
        self.assertIn('localhost', env['no_proxy'])

    def test_explicit_proxy_priority_and_no_proxy_preserved(self):
        env = engine_environment({'https_proxy':'http://example:1234', 'no_proxy':'internal.test'}, {'https':'http://other:5678'})
        self.assertNotIn('HTTPS_PROXY', env)
        self.assertEqual(env['https_proxy'], 'http://example:1234')
        self.assertIn('internal.test', env['NO_PROXY'])

    def test_no_proxy_does_not_invent_a_server(self):
        self.assertNotIn('HTTPS_PROXY', engine_environment({}, {}))

    def test_no_proxy_environment_does_not_hide_windows_registry(self):
        with patch('network_config.urllib.request.getproxies_registry', create=True, return_value={'https':'http://127.0.0.1:12345'}), patch('network_config.urllib.request.getproxies_environment', return_value={'no':'localhost'}):
            self.assertEqual(engine_environment({'NO_PROXY':'localhost'})['HTTPS_PROXY'], 'http://127.0.0.1:12345')


if __name__ == '__main__': unittest.main()
