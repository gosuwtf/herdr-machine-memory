import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import memory

BRIDGE = ("ssh -C -F /tmp/herdr-ssh-1-1/config -S /tmp/hssh-1000/abc-%C "
          "-o ControlMaster=auto -o BatchMode=yes -T me@box printf ' %s ' "
          "'herdr-remote-output-ready:1' exec /usr/bin/herdr remote-client-bridge")


class MemoryTests(unittest.TestCase):
    def test_linux_excludes_available_cache(self):
        self.assertEqual(memory.linux_memory(
            'MemTotal: 1000 kB\nMemFree: 100 kB\nMemAvailable: 400 kB\n'),
            (600 * 1024, 1000 * 1024))

    def test_mac_uses_reported_page_size(self):
        stats = ('Mach Virtual Memory Statistics: (page size of 16384 bytes)\n'
                 'Pages free: 10.\nPages inactive: 20.\nPages speculative: 5.\n')
        self.assertEqual(memory.mac_memory(stats, 100 * 16384),
                         (65 * 16384, 100 * 16384))

    def test_unavailable_machine(self):
        def fail():
            raise OSError
        self.assertEqual(memory.indicator('test', fail), 'test: unavailable')

    def test_format(self):
        self.assertEqual(memory.indicator('rip', lambda: (6 * 1024**3, 16 * 1024**3)),
                         'rip: 38%')

    def test_parse_bridges_only_herdr_ssh(self):
        ps = '\n'.join([BRIDGE, 'ssh -T me@other uptime',
                        'ssh: /tmp/hssh-1000/abc-123 [mux]', 'vim ' + BRIDGE])
        self.assertEqual(memory.parse_bridges(ps),
                         [('me@box', '/tmp/hssh-1000/abc-%C')])

    def test_control_sockets_match_prefix(self):
        with tempfile.TemporaryDirectory() as tmp:
            import socket
            sock = socket.socket(socket.AF_UNIX)
            sock.bind(os.path.join(tmp, 'abc-123'))
            Path(tmp, 'abc-file').touch()
            self.assertEqual(memory.control_sockets(os.path.join(tmp, 'abc-%C')),
                             [os.path.join(tmp, 'abc-123')])
            sock.close()

    def test_only_local_and_connected_peers_shown(self):
        saved = {'me@b': 'beta', 'me@a': 'alpha', 'me@off': 'offline'}
        peers = {'me@a': '/s/a', 'me@b': '/s/b', 'me@adhoc': '/s/c'}
        with patch.object(memory, 'saved_machines', return_value=saved), \
                patch.object(memory, 'connected_peers', return_value=peers), \
                patch.object(memory, 'load_labels', return_value={'alpha': 'a1'}), \
                patch.object(memory.platform, 'node', return_value='home.local'), \
                patch.object(memory, 'local_memory', return_value=(1, 4)), \
                patch.object(memory, 'remote_memory', return_value=(2, 4)):
            self.assertEqual(memory.status_line(),
                             'home: 25% · beta: 50% · a1: 50% · adhoc: 50%')


if __name__ == '__main__':
    unittest.main()
