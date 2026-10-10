"""Small deterministic UI textures, gradients and focus borders (no movie artwork)."""
from pathlib import Path
import math
import struct
import zlib

OUT = Path(__file__).resolve().parents[1] / "roku/images"

def png(name, width, height, pixel):
    raw = bytearray()
    for y in range(height):
        raw.append(0)
        for x in range(width):
            raw.extend(max(0, min(255, round(v))) for v in pixel(x, y, width, height))
    def chunk(kind, data):
        return struct.pack("!I", len(data)) + kind + data + struct.pack("!I", zlib.crc32(kind + data) & 0xffffffff)
    (OUT / name).write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack("!2I5B", width, height, 8, 6, 0, 0, 0))
                            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))

def atmosphere(x, y, w, h):
    u, v = x / w, y / h
    glow = math.exp(-((u-.70)**2/.1 + (v-.36)**2/.13))
    ribbon = math.exp(-((v - (.60 - .19*math.sin(u*3.8)))**2)/.0009) * .22
    return (10+18*glow+12*ribbon, 18+38*glow+34*ribbon, 29+67*glow+62*ribbon, 255)

def hero_shade(x,y,w,h):
    u,v=x/w,y/h
    left=.96*(1-min(1,u/.82))**1.1
    bottom=max(0,(v-.57)/.43)**1.5
    top=max(0,(.2-v)/.2)*.42
    alpha=1-(1-left)*(1-bottom)*(1-top)
    return (8,13,20,255*alpha)

def ring(x,y,w,h):
    d=min(x,y,w-1-x,h-1-y)
    alpha={0:8,1:22,2:52,3:120,4:255,5:255}.get(d,0)
    return (135,192,255,alpha)

png("hero-fallback.png",960,432,atmosphere)
png("hero-shade.png",1280,432,hero_shade)
png("card-fallback.png",208,118,atmosphere)
png("card-shade.png",208,118,lambda x,y,w,h:(5,9,15,230*max(0,(y/h-.24)/.76)**1.15))
png("card-focus.png",218,128,ring)
print("Generated five compact Roku UI textures")
