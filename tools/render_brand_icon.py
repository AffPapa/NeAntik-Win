"""Render the NeVision Windows icon from the brand geometry.

This development helper intentionally has no runtime dependency: the packaged app
uses the generated ``assets/nevision.ico``.  Pillow is already present in the local
build environment; install it only when regenerating the asset on a fresh machine.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "assets" / "nevision.ico"
PREVIEW = ROOT / "assets" / "nevision-icon-preview.png"


def scale(value: float, size: int) -> int:
    return round(value * size / 1024)


def render(size: int) -> Image.Image:
    image = Image.new("RGBA", (size, size), "#0B1020")
    shadow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    shadow_draw.rounded_rectangle(
        (scale(112, size), scale(132, size), scale(912, size), scale(948, size)),
        radius=scale(230, size),
        fill="#050814AA",
    )
    image.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(max(1, scale(26, size)))))

    draw = ImageDraw.Draw(image)
    bounds = (scale(112, size), scale(104, size), scale(912, size), scale(920, size))
    draw.rounded_rectangle(bounds, radius=scale(230, size), fill="#8B6DFF")
    # Subtle diagonal highlight gives the tile depth without a heavy gradient.
    draw.rounded_rectangle(
        (scale(129, size), scale(121, size), scale(895, size), scale(903, size)),
        radius=scale(213, size),
        outline="#D7CCFF6A",
        width=max(1, scale(22, size)),
    )
    n_points = [
        (scale(330, size), scale(704, size)),
        (scale(330, size), scale(328, size)),
        (scale(672, size), scale(704, size)),
        (scale(672, size), scale(328, size)),
    ]
    draw.line(n_points, fill="#11182A", width=max(2, scale(92, size)), joint="curve")
    radius = scale(80, size)
    center = (scale(725, size), scale(292, size))
    draw.ellipse(
        (center[0] - radius, center[1] - radius, center[0] + radius, center[1] + radius),
        fill="#C7F83A",
        outline="#F1FFCE",
        width=max(1, scale(28, size)),
    )
    return image


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    # Windows selects the closest variant, so include the taskbar and high-DPI sizes.
    primary = render(256)
    primary.save(OUTPUT, format="ICO", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    primary.save(PREVIEW, format="PNG", optimize=True)
    print(f"Rendered {OUTPUT}")


if __name__ == "__main__":
    main()
