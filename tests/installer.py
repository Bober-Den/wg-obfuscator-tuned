"""Exercise installer transactions in a disposable filesystem, without devices.

Production paths are rewritten only in a temporary test copy of install.sh.
systemd/uname/id are mocked; native Keenetic PID tests use a tiny test UDP ELF,
not the ARM64 prebuilt. No production network, credentials or root is needed.
"""
import hashlib
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / 'install.sh').read_text(encoding='utf-8')
HEADER = '  sl  local_address rem_address st\n'
SERVER_HASH = '1e014cb01b9da9b5ffc7f51c6962bdabd6d5bf49e87190e6310f47b59f4c55cf'
CLIENT_HASH = '6f71fae6dd8437e0e9c707495d49d0d8cb2a6fb992bea7e29d18a9076f4c70d1'


class InstallerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build = tempfile.TemporaryDirectory(prefix='wgot-test-build-')
        cls.fake_binary = Path(cls.build.name) / 'transport'
        code = Path(cls.build.name) / 'transport.c'
        code.write_text(r'''
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/socket.h>
#include <netinet/in.h>
int main(int argc, char **argv) {
    if (argc == 2 && !strcmp(argv[1], "--help")) return 0;
    if (getenv("WGOT_FAIL_BINARY")) return 2;
    if (argc != 3 || strcmp(argv[1], "-c")) return 3;
    FILE *c = fopen(argv[2], "r"); if (!c) return 4;
    char line[1024]; int port = 0;
    while (fgets(line, sizeof line, c)) sscanf(line, "source-lport = %d", &port);
    fclose(c);
    int fd = socket(AF_INET, SOCK_DGRAM, 0);
    struct sockaddr_in a = {0}; a.sin_family = AF_INET;
    a.sin_addr.s_addr = htonl(INADDR_LOOPBACK); a.sin_port = htons(port);
    if (bind(fd, (struct sockaddr *)&a, sizeof a)) return 5;
    FILE *t = fopen(getenv("WGOT_SOCKET_TABLE"), "a"); if (!t) return 6;
    fprintf(t, "0: 0100007F:%04X 00000000:0000 07\n", port); fclose(t);
    for (;;) pause();
}
''', encoding='utf-8')
        subprocess.run(['cc', '-O2', str(code), '-o', str(cls.fake_binary)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.build.cleanup()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='wgot-installer-')
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.fs = self.base / 'root'
        self.tools = self.base / 'tools'
        self.tools.mkdir()
        self.env = dict(os.environ, PATH=f'{self.tools}:{os.environ["PATH"]}')
        self.env.pop('GITHUB_TOKEN', None)
        self.env['TMPDIR'] = str(self.base / 'tmp')
        Path(self.env['TMPDIR']).mkdir()
        self.events = self.base / 'events'
        self.env['WGOT_EVENTS'] = str(self.events)
        self.env['WGOT_SOCKET_TABLE'] = str(self.fs / 'proc/net/udp')
        for directory in ['proc/net', 'run/systemd/system', 'etc/systemd/system',
                          'opt/bin', 'opt/etc/init.d', 'opt/etc/other-vpn']:
            (self.fs / directory).mkdir(parents=True, exist_ok=True)
        for family in ['udp', 'udp6']:
            (self.fs / f'proc/net/{family}').write_text(HEADER)
        self.write_exe(self.fs / 'opt/bin/sh', '#!/bin/sh\nexec /bin/sh "$@"\n')
        self.write_tool('uname', 'case "$1" in -m) echo "${WGOT_ARCH:-x86_64}";; -s) echo Linux;; esac')
        self.write_tool('id', 'echo 0')
        self.write_tool('sleep', '/bin/sleep 0.1')
        self.write_tool('systemctl', r'''
printf '%s\n' "$*" >>"$WGOT_EVENTS"
case "$1" in
    show) echo "${WGOT_LOAD_STATE:-not-found}" ;;
    enable)
        if [ "${WGOT_FAIL_START:-}" = yes ]; then exit 1; fi
        printf '0: 00000000:5DC0 00000000:0000 07\n' >>"$WGOT_SOCKET_TABLE" ;;
    is-active) [ "${WGOT_FAIL_ACTIVE:-}" != yes ] ;;
esac
''')
        for forbidden in ['ndmc', 'ndm', 'iptables', 'ip6tables', 'nft', 'ip',
                          'sysctl', 'opkg', 'killall', 'reboot', 'wg', 'wg-quick']:
            self.write_tool(forbidden, 'echo "FORBIDDEN $0 $*" >>"$WGOT_EVENTS"; exit 99')
        self.offline = self.base / 'source'
        for relative in ['prebuilt/linux-x86_64/wgot-server', 'prebuilt/keenetic-arm64/wgot-client']:
            dest = self.offline / relative
            dest.parent.mkdir(parents=True)
            shutil.copyfile(self.fake_binary, dest)
        digest = hashlib.sha256(self.fake_binary.read_bytes()).hexdigest()
        script = SOURCE.replace(SERVER_HASH, digest).replace(CLIENT_HASH, digest)
        # Rebind filesystem paths in the test copy, including generated scripts.
        for prefix in ['/usr/local/lib/wgot', '/etc/systemd/system', '/run/systemd/system',
                       '/proc/net/udp', '/opt']:
            script = script.replace(prefix, str(self.fs) + prefix)
        self.script = self.base / 'install.sh'
        self.script.write_text(script, encoding='utf-8')
        self.key = self.base / 'shared.key'
        self.key.write_text('synthetic-key-for-installer-tests-0123456789\n')
        self.sentinels = {}
        for name in ['etc/systemd/system/other-vpn.service', 'opt/etc/init.d/S90phobos',
                     'opt/etc/other-vpn/policies.json', 'opt/etc/other-vpn/devices.json',
                     'opt/etc/other-vpn/wireguard.conf']:
            path = self.fs / name
            path.write_text(f'keep {name}\n')
            self.sentinels[path] = path.read_bytes()
        self.addCleanup(self.assert_preserved)
        self.pids = []
        self.addCleanup(self.stop_test_processes)

    def stop_test_processes(self):
        for pid in self.pids:
            try:
                exe = Path(f'/proc/{pid}/exe').resolve()
                if str(exe).startswith(str(self.fs)):
                    os.kill(pid, signal.SIGTERM)
            except (ProcessLookupError, FileNotFoundError):
                pass

    def assert_preserved(self):
        for path, data in self.sentinels.items():
            self.assertEqual(path.read_bytes(), data, str(path))
        if self.events.exists():
            self.assertNotIn('FORBIDDEN', self.events.read_text())

    def write_exe(self, path, body):
        path.write_text(body, encoding='utf-8')
        path.chmod(0o755)

    def write_tool(self, name, body):
        self.write_exe(self.tools / name, '#!/bin/sh\n' + body + '\n')

    def run_install(self, *args, mode='vps', success=True):
        self.env['WGOT_ARCH'] = 'aarch64' if mode == 'keenetic' else 'x86_64'
        result = subprocess.run(['sh', str(self.script), mode, '--target', '198.51.100.10:51820',
                                 '--source-dir', str(self.offline), '--key-file', str(self.key), *args],
                                env=self.env, capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode == 0, success, result.stdout + result.stderr)
        return result

    def instance(self, mode='vps', name='main'):
        return self.fs / ('opt/etc/wgot' if mode == 'keenetic' else 'usr/local/lib/wgot') / name

    def occupy(self, port, family='udp'):
        with (self.fs / f'proc/net/{family}').open('a') as out:
            out.write(f'0: 00000000:{port:04X} 00000000:0000 07\n')

    def test_dry_run_writes_nothing(self):
        self.offline.rename(self.base / 'hidden-source')
        self.key.unlink()
        result = self.run_install('--dry-run')
        self.assertIn('Dry run', result.stdout)
        self.assertFalse(self.instance().exists())
        self.assertEqual(list(Path(self.env['TMPDIR']).iterdir()), [])

    def test_ipv4_and_ipv6_collisions(self):
        for family in ['udp', 'udp6']:
            with self.subTest(family=family):
                self.occupy(24443, family)
                self.run_install('--listen-port', '24443', success=False)
                self.assertFalse(self.instance().exists())
                (self.fs / f'proc/net/{family}').write_text(HEADER)

    def test_auto_skips_both_families_and_target(self):
        self.occupy(24000)
        self.occupy(24001, 'udp6')
        result = self.run_install('--dry-run', '--target', '127.0.0.1:24002')
        self.assertIn('0.0.0.0:24003', result.stdout)

    def test_missing_udp_table_fails_closed(self):
        (self.fs / 'proc/net/udp6').unlink()
        self.run_install('--dry-run', success=False)
        self.assertFalse(self.instance().exists())

    def test_existing_paths_and_vendor_units_refused(self):
        self.env['WGOT_LOAD_STATE'] = 'loaded'
        self.run_install(success=False)
        self.env.pop('WGOT_LOAD_STATE')
        service = self.fs / 'etc/systemd/system/wgot-main.service'
        service.write_text('existing unit')
        self.run_install(success=False)
        self.assertEqual(service.read_text(), 'existing unit')
        service.unlink()
        self.instance().mkdir(parents=True)
        self.run_install(success=False)

    def test_symlink_refused(self):
        self.instance().parent.mkdir(parents=True)
        self.instance().symlink_to(self.fs / 'opt/etc/other-vpn')
        self.run_install(success=False)

    def test_invalid_arguments(self):
        for args in [('--name', '../other'), ('--name', '123456789'), ('--name', 'bad-name'),
                     ('--listen-port', '0'), ('--listen-port', '024000'),
                     ('--listen-port', '65536'), ('--target', '::1:51820'),
                     ('--target', 'host:51820\nkey=bad'), ('--unknown',)]:
            with self.subTest(args=args):
                self.run_install(*args, success=False)
        self.assertFalse(self.instance().exists())

    def test_wrong_architecture(self):
        self.write_tool('uname', 'case "$1" in -m) echo mips;; -s) echo Linux;; esac')
        self.run_install(success=False)
        self.run_install(mode='keenetic', success=False)

    def test_tampered_binary_installs_nothing(self):
        (self.offline / 'prebuilt/linux-x86_64/wgot-server').write_bytes(b'corrupt')
        self.run_install(success=False)
        self.assertFalse(self.instance().exists())
        self.assertEqual(list(Path(self.env['TMPDIR']).iterdir()), [])

    def test_invalid_key_installs_nothing(self):
        self.key.write_text('x' * 32 + '\nsource-if=0.0.0.0\n')
        self.run_install(success=False)
        self.assertFalse(self.instance().exists())

    def test_disabled_install_and_second_instance(self):
        result = self.run_install('--no-start')
        self.assertNotIn(self.key.read_text().strip(), result.stdout + result.stderr)
        instance = self.instance()
        self.assertEqual(instance.stat().st_mode & 0o777, 0o700)
        for name in ['shared-key.txt', 'transport.conf']:
            self.assertEqual((instance / name).stat().st_mode & 0o777, 0o600)
        self.assertNotIn('enable', self.events.read_text())
        self.run_install('--no-start', '--name', 'second')
        self.assertTrue(self.instance(name='second').exists())
        before = (instance / 'transport.conf').read_bytes()
        self.run_install('--no-start', success=False)
        self.assertEqual((instance / 'transport.conf').read_bytes(), before)

    def test_vps_start_and_scoped_rollback(self):
        self.env['WGOT_FAIL_START'] = 'yes'
        self.run_install(success=False)
        self.assertFalse(self.instance().exists())
        self.assertFalse((self.fs / 'etc/systemd/system/wgot-main.service').exists())
        self.assertIn('disable --now wgot-main.service', self.events.read_text())
        self.env.pop('WGOT_FAIL_START')
        self.run_install()
        self.assertIn('enable --now wgot-main.service', self.events.read_text())

    def test_generated_key_is_private_and_not_printed(self):
        # Drop the test harness's --key-file option to exercise generation.
        self.script.write_text(self.script.read_text().replace('KEY_FILE=$2', 'KEY_FILE='))
        result = self.run_install('--no-start')
        secret = (self.instance() / 'shared-key.txt').read_text().strip()
        self.assertEqual(len(secret), 64)
        self.assertNotIn(secret, result.stdout + result.stderr)

    def test_keenetic_disabled_and_pid_reuse_safety(self):
        self.run_install('--no-start', mode='keenetic')
        instance = self.instance('keenetic')
        self.assertFalse((instance / 'enabled').exists())
        # An unrelated live process must never be signalled.
        proc = subprocess.Popen(['/bin/sleep', '60'])
        self.addCleanup(lambda: (proc.terminate(), proc.wait()) if proc.poll() is None else None)
        (instance / 'pid').write_text(str(proc.pid))
        result = subprocess.run(['sh', str(instance / 'control'), 'stop'], env=self.env,
                                capture_output=True, text=True, timeout=5)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('unowned PID', result.stderr)
        self.assertIsNone(proc.poll())

    def test_keenetic_native_start_stop_and_config_identity(self):
        self.run_install(mode='keenetic')
        instance = self.instance('keenetic')
        pid = int((instance / 'pid').read_text())
        self.pids.append(pid)
        self.assertEqual(Path(f'/proc/{pid}/exe').resolve(), instance / 'wgotc-main')
        result = subprocess.run(['sh', str(instance / 'control'), 'stop'], env=self.env,
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((instance / 'pid').exists())

    def test_keenetic_failed_start_cleans_enabled_flag(self):
        self.env['WGOT_FAIL_BINARY'] = 'yes'
        self.run_install(mode='keenetic', success=False)
        self.assertFalse(self.instance('keenetic').exists())
        self.assertFalse((self.fs / 'opt/etc/init.d/S97wgot-main').exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
