#!/bin/sh
# Install only the UDP transport. Never configure WireGuard, NDM or routing.
set -eu
umask 077
export LC_ALL=C

die() { printf 'wgot: %s\n' "$*" >&2; exit 1; }
usage() {
    cat <<'EOF'
Usage: sh install.sh vps|keenetic --target HOST:PORT [options]
  --name NAME          Independent instance, 1-8 lowercase letters/digits (main)
  --listen-port PORT   UDP port, 1024-65535, or auto (auto)
  --key-file FILE      Shared transport key; VPS generates one when omitted
  --source-dir DIR     Offline repository copy containing prebuilt/
  --no-start           Install disabled; do not enable or start the service
  --dry-run            Read-only plan, no download or key required
  --help               Show this help

VPS: Linux x86_64 + systemd. Keenetic: Entware aarch64/Cortex-A53.
Keenetic listens only on 127.0.0.1; VPS listens on 0.0.0.0.
No VPN interface, firewall, sysctl, policy or device assignment is changed.
For a private repository, export GITHUB_TOKEN with read access before download.
EOF
}

MODE='' NAME=main PORT=auto TARGET='' KEY_FILE='' SOURCE_DIR='' DRY=no START=yes
STAGE='' INSTANCE_CREATED=no SERVICE_CREATED=no COMMITTED=no ENABLE_ATTEMPTED=no
TTY_STATE=
cleanup() {
    code=$?
    trap - 0 HUP INT TERM
    if [ -n "$TTY_STATE" ]; then stty "$TTY_STATE" </dev/tty 2>/dev/null || :; fi
    if [ "$INSTANCE_CREATED" = yes ] && [ "$COMMITTED" != yes ]; then
        if [ "$MODE" = vps ] && [ "$SERVICE_CREATED" = yes ]; then
            if [ "$ENABLE_ATTEMPTED" = yes ]; then
                if ! systemctl disable --now "$UNIT" >/dev/null 2>&1; then
                    printf 'wgot: rollback could not stop its unit; retained %s and %s for inspection.\n' "$DIR" "$SERVICE" >&2
                    INSTANCE_CREATED=no
                fi
            fi
        elif [ "$MODE" = keenetic ] && [ -x "$DIR/control" ]; then
            if ! "$DIR/control" stop >/dev/null 2>&1; then
                printf 'wgot: rollback could not verify/stop its PID; retained %s and %s for inspection.\n' "$DIR" "$SERVICE" >&2
                INSTANCE_CREATED=no
            fi
        fi
        if [ "$INSTANCE_CREATED" = yes ]; then
            if [ "$SERVICE_CREATED" = yes ]; then rm -f "$SERVICE"; fi
            if [ "$MODE" = vps ] && [ "$SERVICE_CREATED" = yes ]; then systemctl daemon-reload >/dev/null 2>&1 || :; fi
            # Only our fixed filenames; never recursively remove a shared directory.
            rm -f "$DIR/$PROCESS" "$DIR/transport.conf" "$DIR/shared-key.txt" \
                "$DIR/control" "$DIR/install.info" "$DIR/runtime.log" "$DIR/pid" "$DIR/enabled"
            rmdir "$DIR" 2>/dev/null || :
            printf 'wgot: installation failed; removed this new instance only.\n' >&2
        fi
    fi
    if [ -n "$STAGE" ]; then
        rm -f "$STAGE/binary" "$STAGE/auth" "$STAGE/sockets" "$STAGE/config"
        rmdir "$STAGE" 2>/dev/null || :
    fi
    exit "$code"
}
trap cleanup 0
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

while [ "$#" -gt 0 ]; do
    case "$1" in
        vps|keenetic) [ -z "$MODE" ] || die 'Specify one platform'; MODE=$1; shift ;;
        --help|-h) usage; exit 0 ;;
        --no-start) START=no; shift ;;
        --dry-run) DRY=yes; shift ;;
        --name|--listen-port|--target|--key-file|--source-dir)
            [ "$#" -ge 2 ] || die "Missing value for $1"
            case "$1" in
                --name) NAME=$2 ;;
                --listen-port) PORT=$2 ;;
                --target) TARGET=$2 ;;
                --key-file) KEY_FILE=$2 ;;
                --source-dir) SOURCE_DIR=$2 ;;
            esac
            shift 2 ;;
        *) die "Unknown argument: $1" ;;
    esac
done
[ -n "$MODE" ] || { usage >&2; exit 1; }
case "$NAME" in ''|*[!a-z0-9]*) die 'Name must contain 1-8 lowercase letters/digits' ;; esac
[ "${#NAME}" -le 8 ] || die 'Name too long (maximum 8)'
valid_port() {
    case "$1" in ''|*[!0-9]*|0*) return 1 ;; esac
    [ "${#1}" -le 5 ] && [ "$1" -ge 1024 ] && [ "$1" -le 65535 ]
}
case "$TARGET" in ''|*[!a-zA-Z0-9.:-]*|*:*:*) die 'Target must be an IPv4 address or DNS name followed by :PORT' ;; esac
HOST=${TARGET%:*}; TARGET_PORT=${TARGET##*:}
if [ "$HOST" = "$TARGET" ] || [ -z "$HOST" ]; then die 'Target requires HOST:PORT'; fi
case "$HOST" in -*|.*|0.0.0.0) die 'Invalid target host' ;; esac
valid_port "$TARGET_PORT" || die 'Target port must be 1024-65535 (no leading zeros)'
if [ "$PORT" != auto ]; then valid_port "$PORT" || die 'Invalid listen port'; fi

ARCH=$(uname -m)
[ "$(uname -s)" = Linux ] || die 'Only Linux is supported'
if [ "$MODE" = vps ]; then
    [ "$ARCH" = x86_64 ] || die 'VPS prebuilt requires x86_64'
    command -v systemctl >/dev/null 2>&1 || die 'systemd is required'
    [ -d /run/systemd/system ] || die 'systemd must be running'
    BASE=/usr/local/lib/wgot
    PROCESS=wgots-$NAME
    UNIT=wgot-$NAME.service
    SERVICE=/etc/systemd/system/$UNIT
    BIND=0.0.0.0 MASK=AUTO
    ARTIFACT=prebuilt/linux-x86_64/wgot-server
    HASH=1e014cb01b9da9b5ffc7f51c6962bdabd6d5bf49e87190e6310f47b59f4c55cf
else
    [ "$ARCH" = aarch64 ] || die 'Keenetic prebuilt requires aarch64/Cortex-A53; MIPS and ARM32 are unsupported'
    if [ ! -x /opt/bin/sh ] || [ ! -d /opt/etc/init.d ]; then die 'Entware must already be installed'; fi
    # Entware tools take precedence; keep system tools available.
    PATH=/opt/bin:/opt/sbin:$PATH; export PATH
    BASE=/opt/etc/wgot
    PROCESS=wgotc-$NAME
    SERVICE=/opt/etc/init.d/S97wgot-$NAME
    BIND=127.0.0.1 MASK=STUN
    ARTIFACT=prebuilt/keenetic-arm64/wgot-client
    HASH=6f71fae6dd8437e0e9c707495d49d0d8cb2a6fb992bea7e29d18a9076f4c70d1
fi
DIR=$BASE/$NAME
[ ! -L "$BASE" ] || die "Refusing symlink: $BASE"
for path in "$DIR" "$SERVICE"; do
    if [ -e "$path" ] || [ -L "$path" ]; then die "Already exists; nothing overwritten: $path"; fi
done
if [ "$MODE" = vps ]; then
    # Includes units supplied outside /etc, aliases, and transient units.
    LOAD=$(systemctl show "$UNIT" --property=LoadState --value) || die 'Cannot inspect systemd unit'
    [ "$LOAD" = not-found ] || die "Unit name is already reserved: $UNIT"
fi

# Inspect both families, including wildcard/IPv6 dual-stack listeners. Fail closed
# if either table is unavailable; do not rely on netstat output formats.
if [ ! -r /proc/net/udp ] || [ ! -r /proc/net/udp6 ]; then die 'Cannot inspect UDP sockets in /proc/net'; fi
command -v awk >/dev/null 2>&1 || die 'awk is required to inspect UDP ports'
port_busy() {
    hex=$(printf '%04X' "$1")
    if awk -v wanted="$hex" '
        FNR > 1 { split($2, a, ":"); if (toupper(a[2]) == wanted) busy=1 }
        END { exit !busy }
    ' /proc/net/udp /proc/net/udp6; then
        return 0
    else
        result=$?
        [ "$result" = 1 ] || die 'UDP socket inspection failed'
        return 1
    fi
}
if [ "$PORT" = auto ]; then
    PORT=24000
    while port_busy "$PORT" || [ "$PORT" = "$TARGET_PORT" ]; do
        PORT=$((PORT + 1))
        [ "$PORT" -le 24999 ] || die 'No free UDP port in 24000-24999; specify another --listen-port'
    done
else
    port_busy "$PORT" && die "UDP port $PORT is occupied; nothing changed"
fi
case "$HOST" in 127.*|localhost) [ "$PORT" != "$TARGET_PORT" ] || die 'Target loops back to this listener' ;; esac
printf 'Platform: %s; instance: %s; listen: %s:%s; target: %s\n' "$MODE" "$NAME" "$BIND" "$PORT" "$TARGET"
printf 'Private directory: %s\nService: %s\n' "$DIR" "$SERVICE"
[ "$DRY" != yes ] || { printf 'Dry run: nothing changed.\n'; exit 0; }
[ "$(id -u)" = 0 ] || die 'Run as root'
for tool in sha256sum mktemp awk od tr; do command -v "$tool" >/dev/null 2>&1 || die "Required tool: $tool"; done
STAGE=$(mktemp -d "${TMPDIR:-/tmp}/wgot.XXXXXXXX")

# Immutable binary revision + embedded SHA256, independent of a mutable manifest.
REV=fa31239cd80dad3a44516fecc25a438e8299e0ce
if [ -n "$SOURCE_DIR" ]; then
    cp "$SOURCE_DIR/$ARTIFACT" "$STAGE/binary"
else
    command -v curl >/dev/null 2>&1 || die 'Install curl with TLS certificates, or use --source-dir'
    if [ -n "${GITHUB_TOKEN:-}" ]; then
        case "$GITHUB_TOKEN" in *[!a-zA-Z0-9_]*) die 'Invalid GITHUB_TOKEN format' ;; esac
        # Keep the token out of process arguments and installed files.
        printf 'header = "Authorization: Bearer %s"\n' "$GITHUB_TOKEN" >"$STAGE/auth"
        curl --config "$STAGE/auth" --fail --silent --show-error --location \
            --proto '=https' --proto-redir '=https' --connect-timeout 15 --max-time 180 \
            -H 'Accept: application/vnd.github.raw+json' \
            "https://api.github.com/repos/Bober-Den/wg-obfuscator-tuned/contents/$ARTIFACT?ref=$REV" -o "$STAGE/binary"
    else
        curl --fail --silent --show-error --location --proto '=https' --proto-redir '=https' \
            --connect-timeout 15 --max-time 180 \
            "https://raw.githubusercontent.com/Bober-Den/wg-obfuscator-tuned/$REV/$ARTIFACT" -o "$STAGE/binary" \
            || die 'Download failed. Private repository: use GITHUB_TOKEN or --source-dir'
    fi
fi
ACTUAL=$(sha256sum "$STAGE/binary"); ACTUAL=${ACTUAL%% *}
[ "$ACTUAL" = "$HASH" ] || die 'Binary SHA256 mismatch; nothing installed'
chmod 700 "$STAGE/binary"
"$STAGE/binary" --help >/dev/null || die 'Binary cannot run on this CPU/OS'

if [ -n "$KEY_FILE" ]; then
    if [ ! -f "$KEY_FILE" ] || [ ! -r "$KEY_FILE" ]; then die 'Key file is not readable'; fi
    [ "$(wc -c <"$KEY_FILE")" -le 130 ] || die 'Key file is too large'
    KEY=$(cat "$KEY_FILE")
elif [ "$MODE" = vps ]; then
    KEY=$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n')
else
    [ -r /dev/tty ] || die 'Keenetic requires --key-file (same key as VPS)'
    printf 'Shared transport key (hidden): ' >/dev/tty
    TTY_STATE=$(stty -g </dev/tty) || die 'Use --key-file without a terminal'
    stty -echo </dev/tty
    IFS= read -r KEY </dev/tty || die 'Could not read key'
    stty "$TTY_STATE" </dev/tty; TTY_STATE=
    printf '\n' >/dev/tty
fi
case "$KEY" in ''|*[!a-zA-Z0-9_+=./-]*) die 'Key must use letters/digits or _+=./- without spaces or newlines' ;; esac
if [ "${#KEY}" -lt 32 ] || [ "${#KEY}" -gt 128 ]; then die 'Key must be 32-128 characters'; fi

# Create a new instance atomically. Existing instances are never upgraded in place.
mkdir -p "$BASE"
mkdir "$DIR" || die 'Instance was created concurrently; nothing overwritten'
INSTANCE_CREATED=yes
chmod 700 "$DIR"
cp "$STAGE/binary" "$DIR/$PROCESS"
chmod 700 "$DIR/$PROCESS"
printf '%s\n' "$KEY" >"$DIR/shared-key.txt"
cat >"$DIR/transport.conf" <<EOF
[wgot-$NAME]
source-if = $BIND
source-lport = $PORT
target = $TARGET
key = $KEY
masking = $MASK
allow-clean = false
max-dummy = 4
in-timeout = 120
verbose = WARN
EOF
unset KEY
cat >"$DIR/install.info" <<EOF
platform=$MODE
name=$NAME
listen=$BIND:$PORT
target=$TARGET
binary_sha256=$HASH
binary_revision=$REV
EOF

if [ "$MODE" = vps ]; then
    # noclobber also refuses a path created after the preflight check.
    (set -C; cat >"$SERVICE" <<EOF
[Unit]
Description=Isolated wg-obfuscator-tuned ($NAME)
After=network-online.target
Wants=network-online.target
[Service]
Type=simple
ExecStart=$DIR/$PROCESS --config $DIR/transport.conf
Restart=on-failure
RestartSec=3
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=strict
RestrictAddressFamilies=AF_INET AF_UNIX
[Install]
WantedBy=multi-user.target
EOF
    )
    SERVICE_CREATED=yes
    chmod 644 "$SERVICE"
    systemctl daemon-reload
    if [ "$START" = yes ]; then
        port_busy "$PORT" && die "UDP port $PORT became occupied"
        ENABLE_ATTEMPTED=yes
        systemctl enable --now "$UNIT"
        sleep 2
        systemctl is-active --quiet "$UNIT" || die 'New service failed to start'
        port_busy "$PORT" || die 'New service did not bind its UDP port'
    fi
else
    # Exact executable + config identity, no killall/pidof/shared rc.func names.
    cat >"$DIR/control" <<EOF
#!/opt/bin/sh
set -eu
PATH=/opt/bin:/opt/sbin:/sbin:/bin:/usr/sbin:/usr/bin
DIR=$DIR
BIN=$DIR/$PROCESS
EOF
    cat >>"$DIR/control" <<'EOF'
owned() {
    [ -f "$DIR/pid" ] && [ ! -L "$DIR/pid" ] || return 1
    PID=$(cat "$DIR/pid")
    case "$PID" in ''|*[!0-9]*) return 1 ;; esac
    [ "$PID" -gt 1 ] || return 1
    [ "$(readlink "/proc/$PID/exe" 2>/dev/null)" = "$(readlink -f "$BIN")" ] || return 1
    [ "$(tr '\000' '\n' <"/proc/$PID/cmdline" 2>/dev/null | sed -n '3p')" = "$DIR/transport.conf" ]
}
case "${1:-status}" in
    start)
        owned && exit 0
        [ ! -e "$DIR/pid" ] || { echo 'Stale/unowned PID file; inspect it before removing' >&2; exit 1; }
        # noclobber claims the instance before forking another process.
        (set -C; : >"$DIR/pid") || exit 1
        "$BIN" -c "$DIR/transport.conf" >>"$DIR/runtime.log" 2>&1 &
        child=$!
        printf '%s\n' "$child" >"$DIR/pid"
        sleep 1
        if ! owned || ! kill -0 "$child" 2>/dev/null; then
            wait "$child" 2>/dev/null || :
            rm -f "$DIR/pid"
            echo 'Transport failed; inspect runtime.log' >&2; exit 1
        fi ;;
    stop)
        [ -e "$DIR/pid" ] || exit 0
        owned || { echo 'Refusing to signal an unowned PID' >&2; exit 1; }
        kill -TERM "$PID"
        attempts=0
        while owned; do
            attempts=$((attempts + 1))
            [ "$attempts" -lt 10 ] || { echo 'Still running; PID file retained' >&2; exit 1; }
            sleep 1
        done
        rm -f "$DIR/pid" ;;
    status) owned && kill -0 "$PID" 2>/dev/null ;;
    restart) "$0" stop; "$0" start ;;
    *) echo 'Usage: control start|stop|status|restart' >&2; exit 1 ;;
esac
EOF
    chmod 700 "$DIR/control"
    (set -C; cat >"$SERVICE" <<EOF
#!/opt/bin/sh
# Only this instance; does not use Entware's shared process-name matching.
case "\${1:-}" in
    start) [ -f $DIR/enabled ] || exit 0 ;;
esac
exec $DIR/control "\$@"
EOF
    )
    SERVICE_CREATED=yes
    chmod 700 "$SERVICE"
    if [ "$START" = yes ]; then
        port_busy "$PORT" && die "UDP port $PORT became occupied"
        : >"$DIR/enabled"
        "$SERVICE" start
        "$DIR/control" status || die 'New transport failed to start'
        port_busy "$PORT" || die 'New transport did not bind its UDP port'
    fi
fi
COMMITTED=yes
printf '\nInstalled: %s\nKey file (private, not printed): %s/shared-key.txt\n' "$NAME" "$DIR"
if [ "$MODE" = vps ]; then
    printf 'Status: systemctl status %s\nStop: systemctl disable --now %s\n' "$UNIT" "$UNIT"
else
    printf 'Status: %s/control status\nStop: %s/control stop\n' "$DIR" "$DIR"
    printf 'Autostart flag: %s/enabled\nWireGuard local endpoint (set manually): 127.0.0.1:%s\n' "$DIR" "$PORT"
fi
printf 'Start requested: %s. WireGuard payload connectivity has not been tested.\n' "$START"
