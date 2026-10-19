"""Inspecao local restrita aos campos TTF, sem nomes ou identificadores."""
import json
import sqlite3
import struct
import sys


def read_value(blob, offset, depth=0):
    if depth > 8 or offset >= len(blob):
        raise ValueError('Formato invalido')
    kind = blob[offset]
    offset += 1
    if kind == 0:
        size = struct.unpack_from('>H', blob, offset)[0]
        offset += 2
        return blob[offset:offset + size].decode('utf-8'), offset + size
    if kind == 1:
        return struct.unpack_from('>d', blob, offset)[0], offset + 8
    if kind == 2:
        count = struct.unpack_from('>i', blob, offset)[0]
        offset += 4
        if not 0 <= count <= 200:
            raise ValueError('Tabela fora do limite')
        result = {}
        for _ in range(count):
            key, offset = read_value(blob, offset, depth + 1)
            value, offset = read_value(blob, offset, depth + 1)
            result[key] = value
        return result, offset
    if kind == 3:
        return bool(blob[offset]), offset + 1
    raise ValueError(f'Tipo nao suportado: {kind}')


def anchored_value(blob, key):
    raw = key.encode('utf-8')
    marker = b'\x00' + struct.pack('>H', len(raw)) + raw
    if blob.count(marker) != 1:
        raise ValueError('Campo ausente ou ambiguo')
    return read_value(blob, blob.index(marker) + len(marker))[0]


if __name__ == '__main__':
    connection = sqlite3.connect('file:' + sys.argv[1].replace('\\', '/') + '?mode=ro', uri=True)
    for index, (blob,) in enumerate(connection.execute('select data from networkPlayers')):
        output = {'sample': index}
        for key in ('TTF_KillStats', 'TTFStatsGameTimeSeconds'):
            try:
                output[key] = anchored_value(blob, key)
            except (ValueError, struct.error, UnicodeError) as error:
                output[key] = {'unavailable': type(error).__name__}
        print(json.dumps(output, ensure_ascii=True))
