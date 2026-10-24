"""Exercise both obfuscators over loopback with synthetic WireGuard-shaped packets.

This validates UDP transport framing and routing, not WireGuard cryptography.
No public interface, production key or VPN route is used.
"""
import argparse
import os
from pathlib import Path
import socket
import struct
import subprocess
import tempfile
import time

def packet(kind, size):
    return struct.pack('<I', kind) + os.urandom(size - 4)

def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]

def exercise(binary, runner, mask):
    with tempfile.TemporaryDirectory() as tmp, socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as backend, socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as peer:
        backend.bind(('127.0.0.1', 0)); backend.settimeout(.2)
        peer.bind(('127.0.0.1', 0)); peer.settimeout(3)
        server_port, client_port = free_port(), free_port()
        while client_port == server_port:
            client_port = free_port()
        base = Path(tmp)
        configurations = [
            ('server', server_port, backend.getsockname()[1], 'AUTO'),
            ('client', client_port, server_port, mask),
        ]
        processes = []
        logs = []
        try:
            for name, listen, target, masking in configurations:
                config = base / (name + '.conf')
                config.write_text(f'[{name}]\nsource-if = 127.0.0.1\nsource-lport = {listen}\ntarget = 127.0.0.1:{target}\nkey = loopback-test-only-key\nmasking = {masking}\nmax-dummy = 4\nverbose = WARN\n', encoding='utf-8')
                logfile = open(base / (name + '.log'), 'wb')
                logs.append(logfile)
                processes.append(subprocess.Popen([*runner, str(binary), '-c', str(config)], stdout=logfile, stderr=subprocess.STDOUT))
            request = packet(1, 148)
            deadline = time.monotonic() + 8
            while True:
                assert all(p.poll() is None for p in processes), 'Obfuscator exited'
                peer.sendto(request, ('127.0.0.1', client_port))
                try:
                    received, remote = backend.recvfrom(65535)
                    assert received == request
                    break
                except socket.timeout:
                    if time.monotonic() >= deadline:
                        raise RuntimeError('Handshake-shaped packet was not delivered')
            reply = packet(2, 92)
            backend.sendto(reply, remote)
            assert peer.recvfrom(65535)[0] == reply
            backend.settimeout(3)
            checked = 0
            for size in [32, 64, 256, 1024, 1380]:
                payload = packet(4, size)
                peer.sendto(payload, ('127.0.0.1', client_port))
                received, remote = backend.recvfrom(65535)
                assert received == payload
                reverse = packet(4, size)
                backend.sendto(reverse, remote)
                assert peer.recvfrom(65535)[0] == reverse
                checked += 2
            assert all(p.poll() is None for p in processes)
            print(f'UDP_LOOPBACK_OK masking={mask} data_packets={checked}')
        except Exception:
            for logfile in logs:
                logfile.flush()
                print(Path(logfile.name).read_text(encoding='utf-8', errors='replace')[-4000:])
            raise
        finally:
            for proc in processes:
                proc.terminate()
            for proc in processes:
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill(); proc.wait(timeout=3)
            for logfile in logs:
                logfile.close()

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--runner', nargs='*', default=[])
    args = parser.parse_args()
    for mode in ['AUTO', 'STUN']:
        exercise(args.binary.resolve(), args.runner, mode)
