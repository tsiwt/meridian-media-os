"""Small, dependency-free QR Code encoder (byte mode, EC level L, v1–v6).

Used for the promo claim code.  Implemented from the ISO/IEC 18004 algorithm:
byte-mode data, Reed–Solomon over GF(256), masking with penalty scoring and
SVG rendering.  No network call and no third-party package is involved.
"""

from __future__ import annotations

VERSIONS = {
    1: {"total": 26, "data": 19, "blocks": 1, "data_per_block": 19, "ec_per_block": 7},
    2: {"total": 44, "data": 34, "blocks": 1, "data_per_block": 34, "ec_per_block": 10},
    3: {"total": 70, "data": 55, "blocks": 1, "data_per_block": 55, "ec_per_block": 15},
    4: {"total": 100, "data": 80, "blocks": 1, "data_per_block": 80, "ec_per_block": 20},
    5: {"total": 134, "data": 108, "blocks": 1, "data_per_block": 108, "ec_per_block": 26},
    6: {"total": 172, "data": 136, "blocks": 2, "data_per_block": 68, "ec_per_block": 18},
}
ALIGNMENT = {1: [], 2: [6, 18], 3: [6, 22], 4: [6, 26], 5: [6, 30], 6: [6, 34]}
FORMAT_L = 0b01


def encode_svg(data: str, module_px: int = 8, quiet: int = 4) -> str:
    matrix = encode(data)
    size = len(matrix)
    total = size + quiet * 2
    dark = []
    for row in range(size):
        for col in range(size):
            if matrix[row][col]:
                dark.append(f"M{(col + quiet) * module_px} {(row + quiet) * module_px}h{module_px}v{module_px}h-{module_px}z")
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{total * module_px}" height="{total * module_px}" '
        f'viewBox="0 0 {total * module_px} {total * module_px}" role="img" aria-label="Promo QR code" '
        f'shape-rendering="crispEdges"><rect width="100%" height="100%" fill="#fff"/>'
        f'<path d="{"".join(dark)}" fill="#05080f"/></svg>'
    )


def encode(data: str) -> list[list[bool]]:
    payload = data.encode("utf-8")
    version = _pick_version(len(payload))
    spec = VERSIONS[version]
    bits = _data_bits(payload, spec["data"])
    codewords = _interleave(bits, spec)
    size = 17 + version * 4
    modules = [[False] * size for _ in range(size)]
    function = [[False] * size for _ in range(size)]
    _place_function_patterns(modules, function, version, size)
    _reserve_format(modules, function, size)
    _place_data(modules, function, codewords, size)
    best = None
    best_penalty = None
    for mask in range(8):
        candidate = [row[:] for row in modules]
        _apply_mask(candidate, function, mask)
        _write_format(candidate, mask, size)
        penalty = _penalty(candidate, size)
        if best_penalty is None or penalty < best_penalty:
            best, best_penalty = candidate, penalty
    return best


def _pick_version(length: int) -> int:
    for version, spec in VERSIONS.items():
        if length <= spec["data"] - 2:
            return version
    raise ValueError("QR payload too long for the built-in encoder (max 134 bytes)")


def _data_bits(payload: bytes, capacity: int) -> list[int]:
    bits: list[int] = []
    _append(bits, 0b0100, 4)
    _append(bits, len(payload), 8)
    for byte in payload:
        _append(bits, byte, 8)
    remaining = capacity * 8 - len(bits)
    _append(bits, 0, min(4, remaining))
    while len(bits) % 8:
        bits.append(0)
    pads = [0xEC, 0x11]
    index = 0
    while len(bits) < capacity * 8:
        _append(bits, pads[index % 2], 8)
        index += 1
    return bits


def _append(bits: list[int], value: int, length: int) -> None:
    for shift in range(length - 1, -1, -1):
        bits.append((value >> shift) & 1)


def _interleave(bits: list[int], spec: dict) -> list[int]:
    data_codewords = [int("".join(str(bit) for bit in bits[index:index + 8]), 2) for index in range(0, len(bits), 8)]
    blocks = []
    offset = 0
    for _ in range(spec["blocks"]):
        data = data_codewords[offset:offset + spec["data_per_block"]]
        offset += spec["data_per_block"]
        blocks.append((data, _rs(data, spec["ec_per_block"])))
    output = []
    for index in range(spec["data_per_block"]):
        for data, _ in blocks:
            output.append(data[index])
    for index in range(spec["ec_per_block"]):
        for _, ec in blocks:
            output.append(ec[index])
    return output


# -- GF(256) / Reed–Solomon ------------------------------------------------
_EXP = [0] * 512
_LOG = [0] * 256


def _init_tables() -> None:
    value = 1
    for index in range(255):
        _EXP[index] = value
        _LOG[value] = index
        value <<= 1
        if value & 0x100:
            value ^= 0x11D
    for index in range(255, 512):
        _EXP[index] = _EXP[index - 255]


_init_tables()


def _mul(a: int, b: int) -> int:
    if a == 0 or b == 0:
        return 0
    return _EXP[_LOG[a] + _LOG[b]]


def _rs(data: list[int], ec_count: int) -> list[int]:
    generator = [1]
    for index in range(ec_count):
        generator = _poly_mul(generator, [1, _EXP[index]])
    message = data + [0] * ec_count
    for index in range(len(data)):
        coefficient = message[index]
        if coefficient:
            for offset, value in enumerate(generator):
                message[index + offset] ^= _mul(value, coefficient)
    return message[-ec_count:]


def _poly_mul(a: list[int], b: list[int]) -> list[int]:
    output = [0] * (len(a) + len(b) - 1)
    for i, left in enumerate(a):
        for j, right in enumerate(b):
            output[i + j] ^= _mul(left, right)
    return output


# -- matrix ----------------------------------------------------------------
def _place_function_patterns(modules, function, version, size) -> None:
    for row, col in ((0, 0), (0, size - 7), (size - 7, 0)):
        for dr in range(-1, 8):
            for dc in range(-1, 8):
                r, c = row + dr, col + dc
                if not (0 <= r < size and 0 <= c < size):
                    continue
                dark = 0 <= dr <= 6 and 0 <= dc <= 6 and (
                    dr in (0, 6) or dc in (0, 6) or (2 <= dr <= 4 and 2 <= dc <= 4)
                )
                modules[r][c] = dark
                function[r][c] = True
    for index in range(8, size - 8):
        dark = index % 2 == 0
        modules[6][index] = dark
        function[6][index] = True
        modules[index][6] = dark
        function[index][6] = True
    positions = ALIGNMENT[version]
    last = positions[-1] if positions else -1
    for row in positions:
        for col in positions:
            if (row == 6 and col == 6) or (row == 6 and col == last) or (row == last and col == 6):
                continue
            for dr in range(-2, 3):
                for dc in range(-2, 3):
                    r, c = row + dr, col + dc
                    if not (0 <= r < size and 0 <= c < size):
                        continue
                    dark = max(abs(dr), abs(dc)) != 1
                    modules[r][c] = dark
                    function[r][c] = True


def _reserve_format(modules, function, size) -> None:
    for index in range(9):
        if not function[8][index]:
            function[8][index] = True
            modules[8][index] = False
        if not function[index][8]:
            function[index][8] = True
            modules[index][8] = False
    for index in range(8):
        function[8][size - 1 - index] = True
        modules[8][size - 1 - index] = False
        function[size - 1 - index][8] = True
        modules[size - 1 - index][8] = False
    modules[size - 8][8] = True
    function[size - 8][8] = True


def _place_data(modules, function, codewords, size) -> None:
    bits = []
    for value in codewords:
        _append(bits, value, 8)
    index = 0
    col = size - 1
    upward = True
    while col > 0:
        if col == 6:
            col -= 1
        for step in range(size):
            row = size - 1 - step if upward else step
            for current in (col, col - 1):
                if function[row][current]:
                    continue
                modules[row][current] = bool(bits[index]) if index < len(bits) else False
                index += 1
        col -= 2
        upward = not upward


def _apply_mask(modules, function, mask) -> None:
    size = len(modules)
    for row in range(size):
        for col in range(size):
            if function[row][col]:
                continue
            if _mask_bit(mask, row, col):
                modules[row][col] = not modules[row][col]


def _mask_bit(mask: int, row: int, col: int) -> bool:
    if mask == 0:
        return (row + col) % 2 == 0
    if mask == 1:
        return row % 2 == 0
    if mask == 2:
        return col % 3 == 0
    if mask == 3:
        return (row + col) % 3 == 0
    if mask == 4:
        return (row // 2 + col // 3) % 2 == 0
    if mask == 5:
        return (row * col) % 2 + (row * col) % 3 == 0
    if mask == 6:
        return ((row * col) % 2 + (row * col) % 3) % 2 == 0
    return ((row + col) % 2 + (row * col) % 3) % 2 == 0


def _write_format(modules, mask, size) -> None:
    data = (FORMAT_L << 3) | mask
    remainder = data
    for _ in range(10):
        remainder = (remainder << 1) ^ ((remainder >> 9) * 0x537)
    bits = ((data << 10) | remainder) ^ 0x5412
    for index in range(15):
        bit = ((bits >> (14 - index)) & 1) == 1
        if index < 6:
            modules[8][index] = bit
        elif index == 6:
            modules[8][7] = bit
        elif index == 7:
            modules[8][8] = bit
        elif index == 8:
            modules[7][8] = bit
        else:
            modules[14 - index][8] = bit
        if index < 8:
            modules[size - 1 - index][8] = bit
        else:
            modules[8][size - 15 + index] = bit


def _penalty(modules, size) -> int:
    score = 0
    for row in range(size):
        run = 1
        for col in range(1, size):
            if modules[row][col] == modules[row][col - 1]:
                run += 1
            else:
                if run >= 5:
                    score += 3 + run - 5
                run = 1
        if run >= 5:
            score += 3 + run - 5
    for col in range(size):
        run = 1
        for row in range(1, size):
            if modules[row][col] == modules[row - 1][col]:
                run += 1
            else:
                if run >= 5:
                    score += 3 + run - 5
                run = 1
        if run >= 5:
            score += 3 + run - 5
    for row in range(size - 1):
        for col in range(size - 1):
            value = modules[row][col]
            if value == modules[row + 1][col] == modules[row][col + 1] == modules[row + 1][col + 1]:
                score += 3
    patterns = ([True, False, True, True, True, False, True, False, False, False, False], [False, False, False, False, True, False, True, True, True, False, True])
    for row in range(size):
        line = modules[row]
        for start in range(size - 10):
            for pattern in patterns:
                if line[start:start + 11] == pattern:
                    score += 40
    for col in range(size):
        line = [modules[row][col] for row in range(size)]
        for start in range(size - 10):
            for pattern in patterns:
                if line[start:start + 11] == pattern:
                    score += 40
    dark = sum(1 for row in modules for value in row if value)
    percent = dark * 100 / (size * size)
    score += 10 * int(abs(percent - 50) / 5)
    return score