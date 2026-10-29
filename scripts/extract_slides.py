"""Extract slide text and page images from a PDF/PPT-exported handout.

Text gives you the numbers and terms; images are for tables, diagrams and
anything pymupdf scrambles. Read the images of pages that matter with the
image tool instead of trusting the text layer.

Usage:
  python extract_slides.py --pdf talk.pdf --out-text work/pdf_text.txt --out-img work/pdf_pages
"""
import argparse
import os

import pymupdf


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--out-text", required=True)
    ap.add_argument("--out-img", required=True)
    ap.add_argument("--dpi", type=int, default=130)
    args = ap.parse_args()

    os.makedirs(os.path.dirname(os.path.abspath(args.out_text)), exist_ok=True)
    os.makedirs(args.out_img, exist_ok=True)

    doc = pymupdf.open(args.pdf)
    parts = []
    low = []
    for i, page in enumerate(doc):
        text = page.get_text("text").strip()
        parts.append(f"===== PAGE {i+1} =====\n{text}\n")
        if len(text) < 30:
            low.append(i + 1)
        pix = page.get_pixmap(dpi=args.dpi)
        pix.save(os.path.join(args.out_img, f"page{i+1:02d}.png"))

    with open(args.out_text, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))

    chars = sum(len(x) for x in parts)
    print(f"pages={len(doc)} chars={chars} avg={chars/max(1,len(doc)):.0f} "
          f"images={len(doc)} -> {args.out_img}")
    print(f"text -> {args.out_text}")
    if low:
        print(f"[warn] pages with little/no text (scanned or image-only): {low}")


if __name__ == "__main__":
    main()
