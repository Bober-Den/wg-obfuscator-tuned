"""Mixed-version, two-client UDP bursts over loopback; no VPN keys or routes."""
import argparse
import os
from pathlib import Path
import socket
import struct
import subprocess
import tempfile
import time


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def exercise(args, masking):
    procs, logs, peers = [], [], []
    with tempfile.TemporaryDirectory() as temp, socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as backend:
        backend.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 * 1024 * 1024)
        backend.bind(('127.0.0.1', 0))
        backend.settimeout(4)
        client_port, server_port = free_port(), free_port()
        while client_port == server_port:
            server_port = free_port()
        try:
            configurations = [
                ('server', args.server, args.server_runner, server_port, backend.getsockname()[1], 'AUTO'),
                ('client', args.client, args.client_runner, client_port, server_port, masking),
            ]
            for name, binary, runner, listen, target, mask in configurations:
                conf = Path(temp) / (name + '.conf')
                conf.write_text(f'[{name}]\nsource-if=127.0.0.1\nsource-lport={listen}\ntarget=127.0.0.1:{target}\nkey=synthetic-loopback-burst-key\nmasking={mask}\nmax-dummy=4\nverbose=1\n')
                log = open(Path(temp) / (name + '.log'), 'wb')
                logs.append(log)
                procs.append(subprocess.Popen([*runner, str(Path(binary).resolve()), '-c', str(conf)], stdout=log, stderr=log))
            for index in range(2):
                peer = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                peer.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 * 1024 * 1024)
                peer.bind(('127.0.0.1', 0)); peer.settimeout(4); peers.append(peer)
                request = struct.pack('<II', 1, index) + os.urandom(140)
                deadline = time.monotonic() + 8
                backend.settimeout(0.2)
                while True:
                    assert all(p.poll() is None for p in procs), 'Transport exited'
                    peer.sendto(request, ('127.0.0.1', client_port))
                    try:
                        received, remote = backend.recvfrom(65535)
                        assert received == request
                        break
                    except socket.timeout:
                        if time.monotonic() >= deadline:
                            raise RuntimeError('Handshake-shaped packet not delivered')
                reply = struct.pack('<II', 2, index) + os.urandom(84)
                backend.sendto(reply, remote)
                assert peer.recvfrom(65535)[0] == reply
            backend.settimeout(4)
            checked = 0
            for size in [32, 1380, 4096]:
                expected = {}
                for index, peer in enumerate(peers):
                    # Invalid/empty datagrams must not stall a batch.
                    for malformed in [b'', b'\x04', b'\x00\x01\x02']:
                        peer.sendto(malformed, ('127.0.0.1', client_port))
                    for seq in range(32):
                        payload = struct.pack('<III', 4, index, seq) + os.urandom(size - 12)
                        expected[index, seq] = payload
                        peer.sendto(payload, ('127.0.0.1', client_port))
                seen = []
                for _ in range(64):
                    payload, remote = backend.recvfrom(65535)
                    kind, index, seq = struct.unpack_from('<III', payload)
                    assert kind == 4 and payload == expected[index, seq]
                    seen.append((index, seq))
                    backend.sendto(payload, remote)
                assert len(set(seen)) == 64
                for index, peer in enumerate(peers):
                    for seq in range(32):
                        assert peer.recvfrom(65535)[0] == expected[index, seq]
                        checked += 2
                for index in range(2):
                    assert [seq for client, seq in seen if client == index] == list(range(32)), 'Per-client order changed'
            assert all(p.poll() is None for p in procs)
            print(f'MMSG_BURST_OK mask={masking} clients=2 checked_datagrams={checked}')
        except Exception:
            for log in logs:
                log.flush()
                print(Path(log.name).read_text(errors='replace')[-3000:])
            raise
        finally:
            for p in procs:
                p.terminate()
            for p in procs:
                try: p.wait(timeout=5)
                except subprocess.TimeoutExpired: p.kill(); p.wait()
            for peer in peers: peer.close()
            for log in logs: log.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--client', required=True)
    parser.add_argument('--server', required=True)
    parser.add_argument('--client-runner', nargs='*', default=[])
    parser.add_argument('--server-runner', nargs='*', default=[])
    args = parser.parse_args()
    for masking in ['AUTO', 'STUN', 'NONE']:
        exercise(args, masking)
