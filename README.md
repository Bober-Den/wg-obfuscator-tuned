# wg-obfuscator-tuned

����������� ������� UDP-���������� [ClusterM/wg-obfuscator](https://github.com/ClusterM/wg-obfuscator) ��� **Keenetic ARM64 Cortex-A53** � **Linux VPS x86-64**. ������� �� commit `7008e0ce1ea71a39ce4b50ec9c10d2ce50e9183f`, upstream version1.6. ������ �������� ����� �������: **0.1.0-tuned**.

���������� � ��������� ������ ���������� ���� �������� ��� � ������� �������� ������������� � ��������������. WireGuard, ���-������, �����, �������� � ���������� ��������� ������������� ��������.

## ��������� ����� ��������

���������� ��������� **������ ��������� UDP-���������** � ��� ������������ WireGuard. �������������� VPS Linux x86-64 � systemd � Keenetic � Entware aarch64/Cortex-A53. ��������� �� root � SSH ���������������� ����������. ������ ����������� ����������� �� ���������.

������ ��������� �������� ��� ���, ��������, ������ � ������. ������� UDP-���� � ������������ ����� �������� � ������ ��� ����������. ���������� �� �������� NDM, �� ������ � �� �������� VPN-����������, ��������, ���������� ���������, ��������, firewall/NAT, DNS � sysctl.

**VPS** � `127.0.0.1:51820` �������� �� endpoint ������� ������������� WireGuard. ����� ������ ������� UDP-���� `24443`:

```sh
(umask 077; f=$(mktemp) && trap 'rm -f "$f"' 0 && curl -fsSL --proto '=https' --proto-redir '=https' https://raw.githubusercontent.com/Bober-Den/wg-obfuscator-tuned/main/install.sh -o "$f" && sh "$f" vps --name main --target 127.0.0.1:51820 --listen-port 24443)
```

���� ���������� ������������ �� VPS � ����������� � `/usr/local/lib/wgot/main/shared-key.txt` � ������� `600`; � ����� �� �� ��������. ���� �� ���� ����� �� Keenetic. �������� ��� �������� ���������� ��������; ��� �� ��������� ���� WireGuard.

**Keenetic, Entware SSH** � ���������������� ����� `198.51.100.10` �������� �� IPv4 ������ VPS. ���������� ������ �������� ��� �� ����; ��� ��������������� ������� ����� �������� `--key-file /opt/etc/wgot-shared.key` � ������� ���������� ������:

```sh
(umask 077; f=$(mktemp) && trap 'rm -f "$f"' 0 && curl -fsSL --proto '=https' --proto-redir '=https' https://raw.githubusercontent.com/Bober-Den/wg-obfuscator-tuned/main/install.sh -o "$f" && sh "$f" keenetic --name main --target 198.51.100.10:24443 --listen-port 13365)
```

Keenetic ������� ������ `127.0.0.1:13365`. ����������� WireGuard � ����� endpoint ����������� �������� �������: ���������� �� ����������� ����������� VPN. ��� �������� ������ ����������� �������� ��� ��� ���������� ���������. �� VPS ������ � ���������� UDP-����� ����� ��������� �������� � ������������ firewall, ���� �� ������.

### ��������� �����������

��������� ������� ���� �������� ������ � ��������� ������������. ��� ���������� ����������� ��������� ������� ���������������� `GITHUB_TOKEN` � ������ ������ Contents ����� �����������. ����� �� ��������� � ������� ��� URL; ��������� ������� �������� ��� curl ����� stdin, � ���������� � ����� ��������� ���� � ������� `600`.

VPS:

```sh
(umask 077; f=$(mktemp) && trap 'rm -f "$f"' 0 && printf 'header = "Authorization: Bearer %s"\n' "${GITHUB_TOKEN:?Export a read-only GITHUB_TOKEN first}" | curl --config - -fsSL --proto '=https' --proto-redir '=https' -H 'Accept: application/vnd.github.raw+json' 'https://api.github.com/repos/Bober-Den/wg-obfuscator-tuned/contents/install.sh?ref=main' -o "$f" && sh "$f" vps --name main --target 127.0.0.1:51820 --listen-port 24443)
```

Keenetic:

```sh
(umask 077; f=$(mktemp) && trap 'rm -f "$f"' 0 && printf 'header = "Authorization: Bearer %s"\n' "${GITHUB_TOKEN:?Export a read-only GITHUB_TOKEN first}" | curl --config - -fsSL --proto '=https' --proto-redir '=https' -H 'Accept: application/vnd.github.raw+json' 'https://api.github.com/repos/Bober-Den/wg-obfuscator-tuned/contents/install.sh?ref=main' -o "$f" && sh "$f" keenetic --name main --target 198.51.100.10:24443 --listen-port 13365)
```

�� ��� ��������� ����� ����������� �������� � GitHub-����� �� �����:

```sh
sh install.sh vps --source-dir . --target 127.0.0.1:51820 --listen-port 24443
sh install.sh keenetic --source-dir . --target 198.51.100.10:24443 --listen-port 13365 --key-file /opt/etc/wgot-shared.key
```

��� ������� ��� ������ ���������. ��������� `--dry-run` (���� ��� ������ � ��������), `--no-start` (��������� ��� ������� � �����������), `--listen-port auto` (��������� ���� �� `24000�24999`) � `--name second` ������� � [���������� �� ��������� � ������](docs/INSTALL.md). ��������� ����������� �� ���������� SHA256 � ����������� � ������������ commit, � �� �� ����������� `main`. ��� ����������� ������ ����������� �������� `main` � URL �� ����������� commit.

## ���������

- ��32 ������� �������������� �� ������� ���������� ������, ����� ���� ����������� ������ �������/�������.
- ��� UDP-������� �������� ������������� receive buffer1 ��� � send buffer512 ���. ����������� ������ ������� �� ��������� ��������; � ����������� Linux-������������ �����������2 ���/1 ���.
- ARM64-������: `-O3 -mcpu=cortex-a53`; ���������: `-O3 -mtune=generic`. ��� �����������.
- ������ ����������, ����� � ���������� WireGuard �� ��������. ����������� AUTO/STUN � �������� �������� HTTPS/iperf � �������� ������������.

��� ��������������� ������� ����������, � ����������� ��������� upstream. PCA/Phobos-������ � ���������� Phobos MEDIA/TLS/SOCKS5 � ���� ����������� �� ������; ��� ����� ���������� ����� ����������� ������ ���������������� �������.

## ������� ����������� ������

| ���������� | ���� |
| --- | --- |
| Keenetic Entware, aarch64/Cortex-A53 | [prebuilt/keenetic-arm64/wgot-client](prebuilt/keenetic-arm64/wgot-client) |
| Linux VPS, x86-64 | [prebuilt/linux-x86_64/wgot-server](prebuilt/linux-x86_64/wgot-server) |

��� ����������� ���������, ��������� ������� ���������� ��������, � �� ����� ��������� CI. ������ ��������������� �������� ��� ������� � `src/`. ����������� ����� ��������� ����� `uname -m` �� �������. ��� ������ Keenetic CPU ��� ARM64-������ �� �������� �������������.

�� ����� ����������� �� Linux:

```sh
sha256sum -c prebuilt/SHA256SUMS
chmod +x prebuilt/linux-x86_64/wgot-server
prebuilt/linux-x86_64/wgot-server --help
```

�� Keenetic ����������� ��������������� ARM64-����. ���������� �������� �������� ��� ��������� ������ ��� ������� ����������: `wgotc-���` / `wgots-���`, ����� ��������� ��� � ������� �������������.

## ������ � �����

Linux x86-64, GCC/make/Python3; ��� ARM64 ������������� ����� `gcc-aarch64-linux-gnu` � `libc6-dev-arm64-cross`.

```sh
bash scripts/build.sh all
bash scripts/test.sh
python3 tests/udp_roundtrip.py --binary dist/linux-x86_64/wgot-server
```

� GitHub Actions ����������� ��� ������, �������� CRC-������ � ASan/UBSan, loopback-����� AUTO/STUN � ARM64 smoke-���� ��� QEMU. ����������� ���������� ���������� � Actions artifacts. Workflow ����������� ��� push/PR � �������; ������� � ������ � ������� �������� ��� �� �����. ������������ � CI ���� ����� ���������� �� ����������� prebuilt ��-�� ������ ����������� � ��� ��������� ������, ��������� �������� ����� ������� �� ����������.

## ������������

- [������������ � ���������� �����](docs/DEPLOYMENT.md).
- [��������� �����������, �������� � �������� ���������� ����������](docs/INSTALL.md).
- [���������� ������� � �����������](docs/VALIDATION.md).
- [������������� ���������� � ������](SOURCE-PROVENANCE.json).
- [���������](CHANGELOG.md), [��������� � ��������� ����������](THIRD-PARTY-NOTICES.md).

� ����������� ������ ���������, ������� � ���������. ������� ������, ���������������� �������, �����, ������ � ������ �� ��������.
