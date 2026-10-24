#define _GNU_SOURCE
#include <assert.h>
#include <errno.h>
#include <stdlib.h>
#include <stdio.h>
#include <unistd.h>
#include <sys/socket.h>
#include "wg-obfuscator.h"

static int mock_mode, call_count, single_count, seen[64];
static int fake_many(int fd, struct mmsghdr *m, unsigned n, int flags) {
    (void)fd; (void)flags;
    ++call_count;
    if (mock_mode == 1 && call_count == 1) { errno = EINTR; return -1; }
    if (mock_mode == 2 && call_count == 2) { errno = EAGAIN; return -1; }
    if (mock_mode == 3) return 0;
    if (mock_mode == 4) { errno = EMSGSIZE; return -1; }
    unsigned count = n > 1 ? n - 1 : n;
    for (unsigned i = 0; i < count; ++i) {
        unsigned id = *(unsigned char *)m[i].msg_hdr.msg_iov[0].iov_base;
        assert(id < sizeof(seen) / sizeof(seen[0]));
        ++seen[id];
        m[i].msg_len = (unsigned)m[i].msg_hdr.msg_iov[0].iov_len;
    }
    return (int)count;
}
static ssize_t fake_one(int fd, const struct msghdr *m, int flags) {
    (void)fd; (void)flags; ++single_count;
    unsigned id = *(unsigned char *)m->msg_iov[0].iov_base;
    if (mock_mode == 4 && id == 2) { errno = EMSGSIZE; return -1; }
    ++seen[id]; return (ssize_t)m->msg_iov[0].iov_len;
}
#define WGOT_SENDMMSG fake_many
#define WGOT_SENDMSG fake_one
#include "mmsg_io.h"

int main(void) {
    for (mock_mode = 0; mock_mode <= 4; ++mock_mode) {
        call_count = single_count = 0;
        memset(seen, 0, sizeof(seen));
        unsigned char data[4] = {1, 2, 3, 4};
        client_entry_t clients[4] = {0};
        for (unsigned i = 0; i < 4; ++i) wgot_batch_queue(7, &data[i], 1, NULL, &clients[i], 123, 1);
        wgot_batch_flush();
        for (unsigned id = 1; id <= 4; ++id) assert(seen[id] == ((mock_mode == 4 && id == 2) ? 0 : 1));
        for (unsigned i = 0; i < 4; ++i) {
            long expected = (mock_mode == 4 && i == 1) ? 0 : 123;
            assert(clients[i].last_activity_time == expected && clients[i].last_incoming_time == expected);
        }
        assert(wgot_tx_count == 0);
    }
    /* Changing the destination FD must flush the previous group. */
    mock_mode = 0; memset(seen, 0, sizeof(seen));
    unsigned char a = 5, b = 6;
    wgot_batch_queue(8, &a, 1, NULL, NULL, 0, 0);
    wgot_batch_queue(9, &b, 1, NULL, NULL, 0, 0);
    assert(seen[5] == 1 && seen[6] == 0);
    wgot_batch_flush(); assert(seen[6] == 1);
    /* Real recvmmsg: available datagrams only, zero-length included. */
    int rx = socket(AF_INET, SOCK_DGRAM, 0), tx = socket(AF_INET, SOCK_DGRAM, 0);
    assert(rx >= 0 && tx >= 0);
    struct sockaddr_in address = {.sin_family = AF_INET, .sin_addr.s_addr = htonl(INADDR_LOOPBACK)};
    assert(bind(rx, (struct sockaddr *)&address, sizeof(address)) == 0);
    socklen_t len = sizeof(address); assert(getsockname(rx, (struct sockaddr *)&address, &len) == 0);
    assert(wgot_batch_receive(rx) < 0 && (errno == EAGAIN || errno == EWOULDBLOCK));
    for (unsigned char i = 0; i < 8; ++i) assert(sendto(tx, &i, 1, 0, (struct sockaddr *)&address, sizeof(address)) == 1);
    assert(sendto(tx, "", 0, 0, (struct sockaddr *)&address, sizeof(address)) == 0);
    int n = wgot_batch_receive(rx); assert(n == 9);
    for (int i = 0; i < 8; ++i) { assert(wgot_rx_msg[i].msg_len == 1); assert(wgot_rx_data[i][PREBUFFER_SIZE] == i); }
    assert(wgot_rx_msg[8].msg_len == 0);
    /* Both RX metadata and iov capacities must be reset between batches. */
    assert(sendto(tx, "abcdef", 6, 0, (struct sockaddr *)&address, sizeof(address)) == 6);
    assert(wgot_batch_receive(rx) == 1 && wgot_rx_msg[0].msg_len == 6);
    assert(memcmp(wgot_rx_data[0] + PREBUFFER_SIZE, "abcdef", 6) == 0);
    close(tx); close(rx);
    wgot_batch_stats();
    puts("MMSG_IO_OK partial-send EINTR fallback zero-send per-datagram-error fd-change receive-reset");
    return 0;
}
