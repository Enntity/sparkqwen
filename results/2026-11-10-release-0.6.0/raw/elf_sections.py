#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""elf_sections.py A B : hash every ELF section of two binaries and say which differ.

Exit 1 if a section the loader maps (SHF_ALLOC) differs.
"""
import hashlib, struct, sys

def sections(path):
    b = open(path, "rb").read()
    assert b[:4] == b"\x7fELF" and b[4] == 2 and b[5] == 1, "ELF64 little-endian expected"
    shoff, = struct.unpack_from("<Q", b, 0x28)
    shentsize, shnum, shstrndx = struct.unpack_from("<HHH", b, 0x3A)
    hdr = [struct.unpack_from("<IIQQQQIIQQ", b, shoff + i * shentsize) for i in range(shnum)]
    names = hdr[shstrndx]
    strtab = b[names[4]:names[4] + names[5]]
    out = {}
    for name, typ, flags, addr, off, size, *_ in hdr:
        n = strtab[name:strtab.index(b"\0", name)].decode() or "(null)"
        data = b"" if typ == 8 else b[off:off + size]  # SHT_NOBITS has no file bytes
        out[n] = (typ, flags, size, hashlib.sha256(data).hexdigest())
    return out, hashlib.sha256(b).hexdigest(), len(b)

(a, ha, la), (b, hb, lb) = sections(sys.argv[1]), sections(sys.argv[2])
print(f"A {sys.argv[1]} {la} bytes sha256 {ha}")
print(f"B {sys.argv[2]} {lb} bytes sha256 {hb}")
assert list(a) == list(b), "different section lists"
differ = []
for n in a:
    same = a[n] == b[n]
    kind = "loaded" if a[n][1] & 2 else "not loaded"
    verdict = "same" if same else "DIFFERENT"
    print(f"{n:22} {a[n][2]:>10} bytes  {kind:10}  {verdict:9}  {a[n][3][:16]} {b[n][3][:16]}")
    if not same:
        differ.append((n, kind))
print("differing sections:", differ or "none")
sys.exit(1 if any(k == "loaded" for _, k in differ) else 0)
