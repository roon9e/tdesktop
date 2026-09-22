#!/usr/bin/env python3
"""Generate the Telegram Desktop app icons from a logo.png.

Reads Telegram/Resources/art/logo.png (or a path given via --logo) and
regenerates the icon*.png files, logo_256.png, logo_256_no_margin.png,
icon_round512@2x.png and icon256.ico in the art directory, mirroring the
original Telegram/build/gen_icons.ps1 behavior.

If no logo.png is present the stock upstream icons are kept and the script
does nothing.

Usage:
    python build-system/generate_icons.py [--root /path/to/tdesktop] [--logo path.png]
"""

import argparse
import io
import os
import struct

from PIL import Image, ImageDraw

PNG_SIZES = {
    'icon16.png': 16,
    'icon16@2x.png': 32,
    'icon32.png': 32,
    'icon32@2x.png': 64,
    'icon48.png': 48,
    'icon48@2x.png': 96,
    'icon64.png': 64,
    'icon64@2x.png': 128,
    'icon128.png': 128,
    'icon128@2x.png': 256,
    'icon256.png': 256,
    'icon256@2x.png': 512,
    'icon512.png': 512,
    'icon512@2x.png': 1024,
}


def repo_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def scaled(image, size):
    return image.resize((size, size), Image.BICUBIC)


def save_png(image, path):
    image.save(path, 'PNG')


def trim_bounds(image):
    bbox = image.getchannel('A').getbbox()
    if not bbox:
        return (0, 0, image.width, image.height)
    return (bbox[0], bbox[1], bbox[2] - bbox[0], bbox[3] - bbox[1])


def rounded(image, size, radius):
    result = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(result)
    draw.rounded_rectangle(
        (0, 0, size - 1, size - 1),
        radius=radius,
        fill=(255, 255, 255, 255))
    result.paste(scaled(image, size), (0, 0), result)
    return result


def write_ico(image, sizes, path):
    frames = []
    total = 0
    for size in sizes:
        frame = scaled(image, size)
        buf = io.BytesIO()
        frame.save(buf, 'PNG')
        png = buf.getvalue()
        buf.close()
        frame.close()
        frames.append((size, png))
        total += len(png)
    count = len(frames)
    header = bytearray(6 + 16 * count)
    struct.pack_into('<HHH', header, 0, 0, 1, count)
    data = bytearray(total)
    pos = 0
    for index, (size, png) in enumerate(frames):
        entry = 6 + 16 * index
        pixel = 0 if size >= 256 else size
        header[entry] = pixel
        header[entry + 1] = pixel
        header[entry + 2] = 0
        header[entry + 3] = 0
        struct.pack_into(
            '<HHII',
            header,
            entry + 4,
            1,
            32,
            len(png),
            6 + 16 * count + pos)
        data[pos:pos + len(png)] = png
        pos += len(png)
    with open(path, 'wb') as f:
        f.write(bytes(header))
        f.write(bytes(data))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--root',
        help='repository root (default: parent of build-system/)')
    parser.add_argument('--logo', help='path to the logo image')
    args = parser.parse_args()

    root = os.path.abspath(args.root) if args.root else repo_root()
    art = os.path.join(root, 'Telegram', 'Resources', 'art')
    logo = args.logo or os.path.join(art, 'logo.png')
    if not os.path.isfile(logo):
        print('no logo: keeping stock icons')
        return

    source = Image.open(logo).convert('RGBA')
    for name, size in PNG_SIZES.items():
        save_png(scaled(source, size), os.path.join(art, name))
        print('wrote ' + name)

    save_png(scaled(source, 256), os.path.join(art, 'logo_256.png'))
    print('wrote logo_256.png')

    bounds = trim_bounds(source)
    print('trim bounds: %dx%d+%d+%d' % (bounds[2], bounds[3], bounds[0], bounds[1]))
    if bounds[2] < source.width or bounds[3] < source.height:
        cropped = source.crop((
            bounds[0],
            bounds[1],
            bounds[0] + bounds[2],
            bounds[1] + bounds[3]))
    else:
        cropped = source
    save_png(scaled(cropped, 256), os.path.join(art, 'logo_256_no_margin.png'))
    print('wrote logo_256_no_margin.png')

    save_png(rounded(source, 1024, 230), os.path.join(art, 'icon_round512@2x.png'))
    print('wrote icon_round512@2x.png')

    write_ico(source, [16, 24, 32, 48, 64, 128, 256], os.path.join(art, 'icon256.ico'))
    print('wrote icon256.ico')

    source.close()
    print('DONE')


if __name__ == '__main__':
    main()