"""从 app_icon.png 母版生成多尺寸 app_icon.ico（所有图标位置统一）。"""
import os

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PNG = os.path.join(ROOT, "app_icon.png")
ICO = os.path.join(ROOT, "build", "app_icon.ico")

SIZES = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (24, 24), (16, 16)]


def main():
    image = Image.open(PNG).convert("RGBA")
    image.save(ICO, format="ICO", sizes=SIZES, bitmap_format="png")
    saved = Image.open(ICO)
    print("source", image.size, "->", ICO)
    print("frames", sorted(saved.info.get("sizes", set())))
    print("bytes", os.path.getsize(ICO))


if __name__ == "__main__":
    main()
