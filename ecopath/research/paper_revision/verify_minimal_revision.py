"""Verify preservation of the supplied PDF and render every final page for QA."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import subprocess

from PIL import Image, ImageChops, ImageDraw
import pdfplumber
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'output/pdf'
TMP = ROOT / 'tmp/pdfs/verification'
PDF = OUT / 'EcoPath_Paper_Minimal_Revision.pdf'
SOURCE = Path('/home/saranshlulla/Downloads/Paper 2nd draft.pdf')
if not SOURCE.exists():
    SOURCE = ROOT / 'research/paper_revision/Paper 2nd draft.pdf'
DPI = 100


def main():
    manifest = json.loads((OUT/'minimal_revision_manifest.json').read_text())
    old = PdfReader(SOURCE)
    new = PdfReader(PDF)
    if len(old.pages) != 12 or len(new.pages) != 12 + manifest['appendix_pages']:
        raise ValueError('unexpected page count')
    TMP.mkdir(parents=True, exist_ok=True)
    for label, path in [('source', SOURCE), ('revised', PDF)]:
        with (TMP/f'{label}-render.log').open('w') as log:
            subprocess.run(['pdftoppm', '-r', str(DPI), '-png', str(path), str(TMP/label)],
                           stdout=log, stderr=subprocess.STDOUT, check=True)
    pages = []
    total_outside = 0
    for n in range(1, 13):
        p, q = old.pages[n-1], new.pages[n-1]
        if list(p.mediabox) != list(q.mediabox):
            raise ValueError(f'page geometry changed on original page {n}')
        images_old = sorted(hashlib.sha256(x.data).hexdigest() for x in p.images)
        images_new = sorted(hashlib.sha256(x.data).hexdigest() for x in q.images)
        if images_old != images_new:
            raise ValueError(f'an original image changed on page {n}')
        before = Image.open(TMP/f'source-{n:02d}.png').convert('RGB')
        after = Image.open(TMP/f'revised-{n:02d}.png').convert('RGB')
        if before.size != after.size:
            raise ValueError('raster page sizes differ')
        diff = ImageChops.difference(before, after).convert('L')
        mask = Image.new('L', before.size, 255)
        draw = ImageDraw.Draw(mask)
        page_edits = [x for x in manifest['edits'] if x['page'] == n]
        for edit in page_edits:
            x0,y0,x1,y1 = edit['rect_pdf']
            # Two points allow glyph antialiasing at each text-block edge.
            box = (math.floor((x0-2)*DPI/72), math.floor((float(p.mediabox.height)-y1-2)*DPI/72),
                   math.ceil((x1+2)*DPI/72), math.ceil((float(p.mediabox.height)-y0+2)*DPI/72))
            draw.rectangle(box, fill=0)
        outside = ImageChops.multiply(diff, mask)
        hist = outside.histogram()
        changed = sum(hist[1:])
        total_outside += changed
        if changed:
            outside.save(TMP/f'unexpected-difference-{n:02d}.png')
        pages.append({'page': n, 'original_images_preserved': True,
                      'edited_blocks': len(page_edits), 'changed_pixels_outside_edits': changed})
    with pdfplumber.open(PDF) as pdf:
        font_families = sorted({c['fontname'] for page in pdf.pages for c in page.chars})
        unexpected = [f for f in font_families if f not in {'Times-Roman','Times-Bold','Times-Italic','Times-BoldItalic'}]
        if unexpected:
            raise ValueError(f'unexpected visible font families: {unexpected}')
        for index, page in enumerate(pdf.pages):
            for char in page.chars:
                if char['x0'] < -0.1 or char['x1'] > page.width+0.1 or char['top'] < -0.1 or char['bottom'] > page.height+0.1:
                    raise ValueError(f'text outside page bounds on page {index+1}')
    # A contact sheet complements full-size images; inspect both before delivery.
    thumbnails = []
    for n in range(1, len(new.pages)+1):
        im = Image.open(TMP/f'revised-{n:02d}.png').convert('RGB')
        im.thumbnail((298, 421))
        tile = Image.new('RGB', (318, 451), 'white')
        tile.paste(im, ((318-im.width)//2, 8))
        ImageDraw.Draw(tile).text((12,432), f'Page {n}', fill='black')
        thumbnails.append(tile)
    sheet = Image.new('RGB', (318*4, 451*math.ceil(len(thumbnails)/4)), '#dddddd')
    for i,tile in enumerate(thumbnails):
        sheet.paste(tile, ((i%4)*318,(i//4)*451))
    sheet.save(TMP/'revised-contact-sheet.png')
    report = {'pages': pages, 'font_families': font_families,
              'total_changed_pixels_outside_edits': total_outside,
              'appendix_pages': manifest['appendix_pages'],
              'visual_inspection_required': True,
              'status': 'pass_awaiting_visual_inspection' if total_outside == 0 else 'unexpected_differences_need_inspection'}
    (OUT/'preservation_verification.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    if total_outside:
        raise SystemExit('Inspect unexpected differences before delivery')


if __name__ == '__main__':
    main()
