/* Experimental Linux UDP batches. A batch never waits for more packets. */
#ifndef WGOT_MMSG_IO_H
#define WGOT_MMSG_IO_H
#include <sys/socket.h>
#include <sys/uio.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>

#define WGOT_BATCH 32
/* Separate stable slots retain prebuffer space and avoid copying payloads. */
static unsigned char wgot_rx_data[WGOT_BATCH][BUFFER_SIZE + PREBUFFER_SIZE];
static struct sockaddr_in wgot_rx_addr[WGOT_BATCH];
static struct iovec wgot_rx_iov[WGOT_BATCH];
static struct mmsghdr wgot_rx_msg[WGOT_BATCH];
static struct mmsghdr wgot_tx_msg[WGOT_BATCH];
static struct iovec wgot_tx_iov[WGOT_BATCH];
static struct sockaddr_in wgot_tx_addr[WGOT_BATCH];
static client_entry_t *wgot_tx_client[WGOT_BATCH];
static long wgot_tx_time[WGOT_BATCH];
static unsigned char wgot_tx_incoming[WGOT_BATCH];
static int wgot_tx_fd = -1;
static unsigned wgot_tx_count;
static unsigned long long wgot_rx_calls, wgot_rx_packets, wgot_tx_calls;
static unsigned long long wgot_tx_packets, wgot_tx_fallbacks, wgot_tx_errors;

#ifndef WGOT_SENDMMSG
#define WGOT_SENDMMSG sendmmsg
#endif
#ifndef WGOT_SENDMSG
#define WGOT_SENDMSG sendmsg
#endif

static void wgot_sent(unsigned index) {
    client_entry_t *client = wgot_tx_client[index];
    if (client) {
        client->last_activity_time = wgot_tx_time[index];
        if (wgot_tx_incoming[index]) client->last_incoming_time = wgot_tx_time[index];
    }
    ++wgot_tx_packets;
}

/* Also called by immediate masking callbacks, before they send control data. */
void wgot_batch_flush(void) {
    unsigned done = 0;
    while (done < wgot_tx_count) {
        ++wgot_tx_calls;
        int n = WGOT_SENDMMSG(wgot_tx_fd, wgot_tx_msg + done, wgot_tx_count - done, 0);
        if (n > 0) {
            for (int i = 0; i < n; ++i) wgot_sent(done + (unsigned)i);
            done += (unsigned)n;
            continue;
        }
        if (n < 0 && errno == EINTR) continue;
        /* No messages were sent by this call. Retry remaining datagrams singly
           to isolate one destination's error, without resending a sent prefix. */
        while (done < wgot_tx_count) {
            ++wgot_tx_fallbacks;
            ssize_t sent;
            do { sent = WGOT_SENDMSG(wgot_tx_fd, &wgot_tx_msg[done].msg_hdr, 0); }
            while (sent < 0 && errno == EINTR);
            if (sent == (ssize_t)wgot_tx_iov[done].iov_len) wgot_sent(done);
            else ++wgot_tx_errors;
            ++done;
        }
    }
    wgot_tx_count = 0;
    wgot_tx_fd = -1;
}

static int wgot_batch_receive(int fd) {
    /* The preceding event must be flushed before any receive slot is reused. */
    wgot_batch_flush();
    memset(wgot_rx_msg, 0, sizeof(wgot_rx_msg));
    memset(wgot_rx_addr, 0, sizeof(wgot_rx_addr));
    for (unsigned i = 0; i < WGOT_BATCH; ++i) {
        wgot_rx_iov[i].iov_base = wgot_rx_data[i] + PREBUFFER_SIZE;
        wgot_rx_iov[i].iov_len = BUFFER_SIZE;
        wgot_rx_msg[i].msg_hdr.msg_name = &wgot_rx_addr[i];
        wgot_rx_msg[i].msg_hdr.msg_namelen = sizeof(wgot_rx_addr[i]);
        wgot_rx_msg[i].msg_hdr.msg_iov = &wgot_rx_iov[i];
        wgot_rx_msg[i].msg_hdr.msg_iovlen = 1;
    }
    ++wgot_rx_calls;
    int n = recvmmsg(fd, wgot_rx_msg, WGOT_BATCH, MSG_DONTWAIT | MSG_TRUNC, NULL);
    if (n > 0) wgot_rx_packets += (unsigned)n;
    return n;
}

static int wgot_batch_queue(int fd, unsigned char *buffer, int length,
                            const struct sockaddr_in *address,
                            client_entry_t *client, long now, int incoming) {
    if (wgot_tx_count && (fd != wgot_tx_fd || wgot_tx_count == WGOT_BATCH)) wgot_batch_flush();
    unsigned i = wgot_tx_count++;
    wgot_tx_fd = fd;
    memset(&wgot_tx_msg[i], 0, sizeof(wgot_tx_msg[i]));
    wgot_tx_iov[i].iov_base = buffer;
    wgot_tx_iov[i].iov_len = (size_t)length;
    wgot_tx_msg[i].msg_hdr.msg_iov = &wgot_tx_iov[i];
    wgot_tx_msg[i].msg_hdr.msg_iovlen = 1;
    if (address) {
        wgot_tx_addr[i] = *address;
        wgot_tx_msg[i].msg_hdr.msg_name = &wgot_tx_addr[i];
        wgot_tx_msg[i].msg_hdr.msg_namelen = sizeof(wgot_tx_addr[i]);
    }
    wgot_tx_client[i] = client;
    wgot_tx_time[i] = now;
    wgot_tx_incoming[i] = (unsigned char)incoming;
    return length;
}

static void wgot_batch_stats(void) {
    fprintf(stderr, "WGOT_MMSG_STATS rx_calls=%llu rx_packets=%llu tx_calls=%llu tx_packets=%llu fallback_calls=%llu tx_errors=%llu\n",
        wgot_rx_calls, wgot_rx_packets, wgot_tx_calls, wgot_tx_packets, wgot_tx_fallbacks, wgot_tx_errors);
}
#endif
