from __future__ import annotations

import logging
from pathlib import Path

import fitz  # PyMuPDF

from minpaku_video.models.project import PageInfo

logger = logging.getLogger(__name__)

# PDF rendering DPI (higher = better quality, larger files)
RENDER_DPI = 200


def import_pdf(pdf_path: Path, output_dir: Path) -> list[PageInfo]:
    """PDFを読み込み、各ページをPNG画像として出力する。"""
    output_dir.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(pdf_path)
    pages: list[PageInfo] = []

    for i in range(len(doc)):
        page = doc[i]
        page_num = i + 1
        image_file = f"page_{page_num:02d}.png"
        output_path = output_dir / image_file

        # ページをPNG画像としてレンダリング
        mat = fitz.Matrix(RENDER_DPI / 72, RENDER_DPI / 72)
        pix = page.get_pixmap(matrix=mat)
        pix.save(str(output_path))

        pages.append(PageInfo(
            number=page_num,
            image_file=image_file,
        ))

        logger.info(f"ページ {page_num}/{len(doc)} をPNGに変換: {image_file}")

    doc.close()
    return pages
