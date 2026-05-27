"""
read_imu.py — Affiche en temps réel pitch_deg + données brutes IMU
reçues via VCP (paquet VCP_TYPE_TELEMETRY_IMU = 0x11).

Usage:
    py -3 tools/read_imu.py COM4
    py -3 tools/read_imu.py COM4 --rate 20

Prérequis:
    pip install pyserial

Activation du stream depuis le robot (commande VCP à envoyer
une seule fois, automatiquement à la connexion si --auto-start) :
    STREAM_CTRL : AA 55 01 22 00 <seq> 03 00 01 <rate_L> <rate_H> <CRC_L> <CRC_H> 33
"""

import argparse
import struct
import sys
import time

import serial

# ── Framing constants ──────────────────────────────────────────────────────────
SOF1, SOF2, EOF_BYTE = 0xAA, 0x55, 0x33
VER                  = 0x01

TYPE_TELEMETRY_IMU   = 0x11
TYPE_ACK             = 0x30
TYPE_CMD_STREAM_CTRL = 0x22


def crc16(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def make_frame(pkt_type: int, payload: bytes, seq: int = 0) -> bytes:
    hdr = bytes([VER, pkt_type, 0, seq,
                 len(payload) & 0xFF, (len(payload) >> 8) & 0xFF])
    crc_data = hdr + payload
    crc = crc16(crc_data)
    return bytes([SOF1, SOF2]) + crc_data + struct.pack('<H', crc) + bytes([EOF_BYTE])


def send_stream_ctrl(port: serial.Serial, enable: bool, rate_hz: int, seq: int) -> None:
    payload = struct.pack('<BH', 1 if enable else 0, rate_hz)
    port.write(make_frame(TYPE_CMD_STREAM_CTRL, payload, seq))


def parse_frames(buf: bytearray):
    """Yield complete validated frames from buf, remove consumed bytes."""
    frames = []
    i = 0
    while i < len(buf):
        # Find SOF
        if buf[i] != SOF1:
            i += 1
            continue
        if i + 1 >= len(buf):
            break
        if buf[i + 1] != SOF2:
            i += 1
            continue
        # Need at least 8 bytes for header
        if i + 8 > len(buf):
            break
        plen = buf[i + 6] | (buf[i + 7] << 8)
        total = 11 + plen
        if i + total > len(buf):
            break
        frame = buf[i:i + total]
        # Validate CRC
        crc_calc = crc16(bytes(frame[2:8 + plen]))
        crc_got  = frame[8 + plen] | (frame[9 + plen] << 8)
        if crc_calc == crc_got and frame[10 + plen] == EOF_BYTE:
            frames.append(frame)
        i += total
    del buf[:i]
    return frames


def decode_imu(payload: bytes):
    if len(payload) < 12:
        return None
    ts, pitch_x100, accel_x_mg, accel_z_mg, gyro_y_x10 = struct.unpack_from('<Ihhhh', payload)
    return {
        'ts_ms':       ts,
        'pitch_deg':   pitch_x100 / 100.0,
        'accel_x_g':   accel_x_mg / 1000.0,
        'accel_z_g':   accel_z_mg / 1000.0,
        'gyro_y_dps':  gyro_y_x10 / 10.0,
    }


def main():
    ap = argparse.ArgumentParser(description='Affiche la télémétrie IMU du robot.')
    ap.add_argument('port',            help='Port série (ex: COM4)')
    ap.add_argument('--baud',  type=int, default=115200)
    ap.add_argument('--rate',  type=int, default=20, help='Fréquence stream Hz (1-100)')
    args = ap.parse_args()

    port = serial.Serial(args.port, args.baud, timeout=0.05)
    print(f'Connecté sur {args.port} @ {args.baud} baud')

    seq = 0
    send_stream_ctrl(port, True, args.rate, seq)
    seq += 1
    print(f'Stream activé @ {args.rate} Hz — Ctrl+C pour arrêter\n')
    print(f"{'temps(s)':>9}  {'pitch(°)':>9}  {'accel_x(g)':>10}  {'accel_z(g)':>10}  {'gyro_y(°/s)':>11}")
    print('─' * 60)

    buf = bytearray()
    t0  = time.monotonic()

    try:
        while True:
            chunk = port.read(256)
            if chunk:
                buf.extend(chunk)
                for frame in parse_frames(buf):
                    pkt_type = frame[3]
                    plen     = frame[6] | (frame[7] << 8)
                    payload  = bytes(frame[8:8 + plen])

                    if pkt_type == TYPE_TELEMETRY_IMU:
                        d = decode_imu(payload)
                        if d:
                            t = d['ts_ms'] / 1000.0
                            print(f"{t:9.3f}  {d['pitch_deg']:+9.2f}  "
                                  f"{d['accel_x_g']:+10.3f}  {d['accel_z_g']:+10.3f}  "
                                  f"{d['gyro_y_dps']:+11.2f}")
    except KeyboardInterrupt:
        send_stream_ctrl(port, False, args.rate, seq)
        port.close()
        print('\nStream arrêté.')


if __name__ == '__main__':
    main()
