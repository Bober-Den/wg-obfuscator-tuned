# Changes

## Unreleased

- Add a POSIX one-command installer for isolated VPS/systemd and Keenetic/Entware transport instances, including private-repository and offline downloads.
- Pin prebuilt binary revision and SHA256; refuse occupied ports, existing files and unit names; use per-instance process identity on Keenetic.
- Add dry-run, disabled installation, scoped failure cleanup and removal instructions. Do not modify WireGuard, routing policies, device assignments, firewall or sysctl.

## 0.1.0-tuned — 2026-10-24

- Package the transport variant previously exercised on ARM64 Keenetic and x86-64 VPS systems.
- Preserve the upstream code and wire format at commit7008e0ce1ea71a39ce4b50ec9c10d2ce50e9183f.
- Bound each ready-socket drain to32 packets and request1 MiB receive /512 KiB send UDP buffers per socket.
- Add separate deployment templates, recorded prebuilt hashes, codec/loopback checks and pinned GitHub Actions builds.
- Exclude all deployment credentials, live server addresses and client profiles.

The source keeps the historical `pca_udp_buffers` name and original patch comment to preserve the exact tested source hash. The buffer helper is used on both client and server sockets.
