#ifndef VCP_PROTOCOL_H
#define VCP_PROTOCOL_H

#include <stdint.h>
#include <stddef.h>

#define VCP_SOF1   0xAAu
#define VCP_SOF2   0x55u
#define VCP_EOF    0x33u
#define VCP_VER    0x01u

typedef struct {
    uint8_t  type;
    uint8_t  flags;
    uint8_t  seq;
    uint16_t len;
    uint8_t *payload;
} VcpPacket_t;

uint16_t VcpProtocol_Crc16(const uint8_t *data, size_t len);
int      VcpProtocol_Frame(const VcpPacket_t *pkt, uint8_t *buf, size_t buf_size);
int      VcpProtocol_Parse(const uint8_t *buf, size_t len, VcpPacket_t *pkt_out);

#endif /* VCP_PROTOCOL_H */
