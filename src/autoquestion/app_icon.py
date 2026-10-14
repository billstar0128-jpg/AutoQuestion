"""Generate the A-dot app icon from geometry; no external images or fonts."""
from pathlib import Path
from PIL import Image, ImageDraw


def write_icon(directory):
    path = Path(directory) / 'AutoQuestion.ico'
    with Image.new('RGBA', (256, 256)) as image:
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((8, 8, 248, 248), radius=62, fill='#805bd3')
        draw.line([(48, 188), (110, 65), (171, 188)], fill='white', width=18)
        draw.line([(72, 145), (147, 145)], fill='white', width=16)
        draw.ellipse((187, 171, 207, 191), fill='white')
        image.save(path, format='ICO', sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    return path
