#include "vcp_protocol.h"
#include <string.h>

uint16_t VcpProtocol_Crc16(const uint8_t *data, size_t len)
{
    uint16_t crc = 0xFFFFu;
    for (size_t i = 0; i < len; i++) {
        crc ^= (uint16_t)data[i] << 8;
        for (int b = 0; b < 8; b++)
            crc = (crc & 0x8000u) ? (crc << 1) ^ 0x1021u : (crc << 1);
    }
    return crc;
}

int VcpProtocol_Frame(const VcpPacket_t *pkt, uint8_t *buf, size_t buf_size)
{
    /* SOF1 SOF2 VER TYPE FLAGS SEQ LEN_L LEN_H PAYLOAD CRC_L CRC_H EOF */
    size_t total = 9 + pkt->len + 1;
    if (buf_size < total) return -1;

    buf[0] = VCP_SOF1; buf[1] = VCP_SOF2; buf[2] = VCP_VER;
    buf[3] = pkt->type; buf[4] = pkt->flags; buf[5] = pkt->seq;
    buf[6] = (uint8_t)(pkt->len & 0xFFu);
    buf[7] = (uint8_t)(pkt->len >> 8);
    memcpy(&buf[8], pkt->payload, pkt->len);

    uint16_t crc = VcpProtocol_Crc16(&buf[2], 6 + pkt->len);
    buf[8 + pkt->len] = (uint8_t)(crc & 0xFFu);
    buf[9 + pkt->len] = (uint8_t)(crc >> 8);
    buf[10 + pkt->len] = VCP_EOF;
    return (int)total;
}

int VcpProtocol_Parse(const uint8_t *buf, size_t len, VcpPacket_t *pkt_out)
{
    if (len < 11) return -1;
    if (buf[0] != VCP_SOF1 || buf[1] != VCP_SOF2) return -1;
    pkt_out->type  = buf[3];
    pkt_out->flags = buf[4];
    pkt_out->seq   = buf[5];
    pkt_out->len   = (uint16_t)buf[6] | ((uint16_t)buf[7] << 8);
    pkt_out->payload = (uint8_t *)&buf[8];
    uint16_t crc_got  = (uint16_t)buf[8 + pkt_out->len] | ((uint16_t)buf[9 + pkt_out->len] << 8);
    uint16_t crc_calc = VcpProtocol_Crc16(&buf[2], 6 + pkt_out->len);
    if (crc_got != crc_calc) return -1;
    if (buf[10 + pkt_out->len] != VCP_EOF) return -1;
    return 0;
}
