"""UUIDv7 generation (docs/05 section 1).

Why v7: the first 48 bits are a millisecond timestamp, so new IDs sort roughly by creation
time. B-tree indexes then append at the end instead of splitting random pages, which keeps
inserts fast and indexes small. Python adds uuid.uuid7 only in 3.14, so we implement RFC 9562.
"""

import os
import threading
import time
import uuid

_lock = threading.Lock()
_last_ms = 0
_counter = 0


def uuid7() -> uuid.UUID:
    """RFC 9562 UUIDv7 with a 12-bit counter in rand_a, so IDs from one process are strictly
    increasing even within the same millisecond."""
    global _last_ms, _counter
    with _lock:
        ms = time.time_ns() // 1_000_000
        if ms > _last_ms:
            _last_ms, _counter = ms, int.from_bytes(os.urandom(2)) & 0x3FF  # leave headroom
        else:
            _counter += 1
            if _counter > 0xFFF:  # counter exhausted: borrow the next millisecond
                _last_ms, _counter = _last_ms + 1, 0
        ms, counter = _last_ms, _counter

    rand_b = int.from_bytes(os.urandom(8)) & ((1 << 62) - 1)
    value = (ms & ((1 << 48) - 1)) << 80
    value |= 0x7 << 76  # version
    value |= counter << 64
    value |= 0b10 << 62  # RFC 4122/9562 variant
    value |= rand_b
    return uuid.UUID(int=value)
