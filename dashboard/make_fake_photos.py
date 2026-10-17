"""Draws SYNTHETIC placeholder photos for the demo reports. Standard library only.

Flat shapes, no real people or places, and every image is stamped
"SYNTHETIC DEMO IMAGE". They are written to code/photos/synthetic/, which the
council site serves only behind its password (never from a public folder).

Run: python dashboard/make_fake_photos.py
"""
import struct
import zlib
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "code" / "photos" / "synthetic"
W, H = 640, 480

# 5x7 bitmap glyphs for the stamp text only.
FONT = {
    "S": ["01111", "10000", "10000", "01110", "00001", "00001", "11110"],
    "Y": ["10001", "10001", "01010", "00100", "00100", "00100", "00100"],
    "N": ["10001", "11001", "10101", "10011", "10001", "10001", "10001"],
    "T": ["11111", "00100", "00100", "00100", "00100", "00100", "00100"],
    "H": ["10001", "10001", "10001", "11111", "10001", "10001", "10001"],
    "E": ["11111", "10000", "10000", "11110", "10000", "10000", "11111"],
    "I": ["01110", "00100", "00100", "00100", "00100", "00100", "01110"],
    "C": ["01110", "10001", "10000", "10000", "10000", "10001", "01110"],
    "D": ["11110", "10001", "10001", "10001", "10001", "10001", "11110"],
    "M": ["10001", "11011", "10101", "10101", "10001", "10001", "10001"],
    "O": ["01110", "10001", "10001", "10001", "10001", "10001", "01110"],
    "A": ["01110", "10001", "10001", "11111", "10001", "10001", "10001"],
    "G": ["01110", "10001", "10000", "10111", "10001", "10001", "01111"],
    " ": ["00000"] * 7,
}


class Canvas:
    def __init__(self, colour):
        self.px = [list(colour) * W for _ in range(H)]

    def dot(self, x, y, c):
        if 0 <= x < W and 0 <= y < H:
            self.px[y][3 * x:3 * x + 3] = c

    def rect(self, x0, y0, x1, y1, c):
        for y in range(max(0, y0), min(H, y1)):
            for x in range(max(0, x0), min(W, x1)):
                self.px[y][3 * x:3 * x + 3] = c

    def ellipse(self, cx, cy, rx, ry, c):
        for y in range(cy - ry, cy + ry + 1):
            for x in range(cx - rx, cx + rx + 1):
                if ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2 <= 1:
                    self.dot(x, y, c)

    def triangle(self, a, b, c, colour):
        (x0, y0), (x1, y1), (x2, y2) = a, b, c
        area = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)
        if not area:
            return
        for y in range(min(y0, y1, y2), max(y0, y1, y2) + 1):
            for x in range(min(x0, x1, x2), max(x0, x1, x2) + 1):
                w0 = (x1 - x) * (y2 - y) - (x2 - x) * (y1 - y)
                w1 = (x2 - x) * (y0 - y) - (x0 - x) * (y2 - y)
                w2 = (x0 - x) * (y1 - y) - (x1 - x) * (y0 - y)
                if (w0 >= 0 and w1 >= 0 and w2 >= 0) or (w0 <= 0 and w1 <= 0 and w2 <= 0):
                    self.dot(x, y, colour)

    def text(self, x, y, words, scale, c):
        for ch in words:
            for row, bits in enumerate(FONT[ch]):
                for col, bit in enumerate(bits):
                    if bit == "1":
                        self.rect(x + col * scale, y + row * scale, x + (col + 1) * scale, y + (row + 1) * scale, c)
            x += 6 * scale

    def stamp(self):
        self.rect(0, H - 56, W, H, (20, 24, 28))
        label = "SYNTHETIC DEMO IMAGE"
        scale = 4
        self.text((W - len(label) * 6 * scale) // 2, H - 44, label, scale, (255, 255, 255))

    def png(self):
        raw = b"".join(b"\x00" + bytes(row) for row in self.px)

        def chunk(kind, data):
            return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
        return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


ROAD, PAVE, GRASS, DARK, WHITE = (88, 92, 96), (170, 170, 165), (96, 150, 80), (40, 40, 42), (235, 235, 230)


def pothole():
    c = Canvas(ROAD)
    for x in range(0, W, 120):
        c.rect(x, 200, x + 70, 212, WHITE)
    c.ellipse(330, 330, 120, 55, DARK)
    c.ellipse(330, 322, 100, 40, (25, 25, 27))
    return c


def fly_tipping():
    c = Canvas(PAVE)
    c.rect(0, 0, W, 170, GRASS)
    c.rect(150, 210, 420, 330, (120, 80, 50))      # sofa
    c.rect(150, 180, 420, 225, (135, 92, 60))
    for x, y in ((470, 330), (520, 300), (560, 345)):
        c.ellipse(x, y, 42, 38, (25, 25, 25))       # bin bags
    return c


def litter():
    c = Canvas(PAVE)
    colours = [(200, 40, 40), (40, 90, 200), (230, 200, 40), (240, 240, 240), (60, 160, 70)]
    for i in range(30):
        x, y = (i * 97) % (W - 40), 60 + (i * 53) % 330
        c.rect(x, y, x + 26, y + 14, colours[i % len(colours)])
    return c


def graffiti():
    c = Canvas((150, 70, 55))
    for y in range(0, H, 30):
        c.rect(0, y, W, y + 3, (200, 190, 180))
    for i, colour in enumerate(((240, 60, 160), (40, 200, 220), (250, 220, 40))):
        for x in range(80, 560):
            y = 150 + i * 60 + int(30 * ((x // 40) % 2))
            c.rect(x, y, x + 2, y + 18, colour)
    return c


def glass():
    c = Canvas(PAVE)
    for i in range(24):
        x, y = 60 + (i * 83) % 520, 70 + (i * 61) % 320
        c.triangle((x, y), (x + 34, y + 10), (x + 12, y + 30), (170, 220, 235))
    return c


def vehicle():
    c = Canvas(ROAD)
    c.rect(0, 360, W, 424, PAVE)
    c.rect(140, 230, 500, 330, (60, 90, 140))
    c.rect(210, 170, 420, 235, (70, 105, 160))
    c.rect(225, 180, 405, 225, (180, 210, 230))
    c.ellipse(220, 335, 40, 40, DARK)
    c.ellipse(420, 335, 40, 40, DARK)
    return c


def bin_():
    c = Canvas(PAVE)
    c.rect(0, 0, W, 200, GRASS)
    c.rect(250, 150, 390, 360, (40, 110, 60))
    c.rect(240, 135, 400, 160, (30, 90, 50))
    c.ellipse(270, 365, 18, 18, DARK)
    c.ellipse(370, 365, 18, 18, DARK)
    return c


def generic():
    c = Canvas(PAVE)
    c.triangle((320, 120), (250, 360), (390, 360), (240, 120, 40))
    c.rect(270, 230, 370, 250, WHITE)
    c.rect(230, 360, 410, 380, (40, 40, 40))
    return c


DRAWINGS = {"pothole": pothole, "fly_tipping": fly_tipping, "litter": litter, "graffiti": graffiti,
            "glass": glass, "vehicle": vehicle, "bin": bin_, "generic": generic}

# Which placeholder each category's synthetic photo uses.
FOR_CATEGORY = {
    "pothole": "pothole", "fly_tipping": "fly_tipping", "litter_street_cleaning": "litter",
    "graffiti_flyposting": "graffiti", "glass_spillage_hazard": "glass", "abandoned_vehicle": "vehicle",
    "illegal_parking": "vehicle", "missed_bin": "bin", "lost_damaged_bin": "bin",
}


def photo_for(category_id):
    return f"synthetic/{FOR_CATEGORY.get(category_id, 'generic')}.png"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for name, draw in DRAWINGS.items():
        canvas = draw()
        canvas.stamp()
        (OUT / f"{name}.png").write_bytes(canvas.png())
    print(f"{len(DRAWINGS)} synthetic photos in {OUT}")


if __name__ == "__main__":
    main()
