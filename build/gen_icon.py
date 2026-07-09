"""Genera build/icon.ico para AutoEscritorio (engranaje + rayo sobre navy)."""

from pathlib import Path
from PIL import Image, ImageDraw

NAVY = (30, 58, 95, 255)
NAVY2 = (21, 48, 77, 255)
TERRA = (206, 110, 97, 255)
WHITE = (255, 255, 255, 255)


def make(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    r = int(size * 0.22)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=r, fill=NAVY)
    d.rounded_rectangle([0, int(size * 0.5), size - 1, size - 1], radius=r, fill=NAVY2)
    # engranaje (anillo con dientes)
    cx, cy = int(size * 0.40), int(size * 0.50)
    rad = int(size * 0.22)
    import math
    for k in range(8):
        a = k * math.pi / 4
        x = cx + int((rad + size * 0.05) * math.cos(a))
        y = cy + int((rad + size * 0.05) * math.sin(a))
        s = int(size * 0.05)
        d.rectangle([x - s, y - s, x + s, y + s], fill=WHITE)
    d.ellipse([cx - rad, cy - rad, cx + rad, cy + rad], fill=WHITE)
    d.ellipse([cx - rad // 2, cy - rad // 2, cx + rad // 2, cy + rad // 2], fill=NAVY)
    # rayo terracota
    p = [(int(size * 0.62), int(size * 0.20)), (int(size * 0.50), int(size * 0.52)),
         (int(size * 0.60), int(size * 0.52)), (int(size * 0.52), int(size * 0.82)),
         (int(size * 0.78), int(size * 0.44)), (int(size * 0.66), int(size * 0.44)),
         (int(size * 0.74), int(size * 0.20))]
    d.polygon(p, fill=TERRA)
    return img


def main() -> None:
    out = Path(__file__).resolve().parent / "icon.ico"
    sizes = [16, 24, 32, 48, 64, 128, 256]
    imgs = [make(s) for s in sizes]
    imgs[-1].save(out, format="ICO", sizes=[(s, s) for s in sizes])
    make(256).save(out.with_name("icon_preview.png"))
    print("icono ->", out)


if __name__ == "__main__":
    main()
