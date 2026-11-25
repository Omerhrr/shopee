"""Formatted Excel (.xlsx) export of Shopee listings: the nicer replacement for the plain CSV.

Sheet 1 "Shopee Upload": exactly the mass-upload columns (same order as the CSV), but styled:
  coloured frozen header, sensible column widths, wrapped descriptions, number formats,
  zebra rows, filters, clickable source links.
Sheet 2 "Preview": a human-friendly view with a photo thumbnail next to name and price.
Sheet 3 "Info": what the file contains and how to use it.
"""
import io
from datetime import date

from openpyxl import Workbook
from openpyxl.drawing.image import Image as XLImage
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

ORANGE = "EE4D2D"
HEAD_FILL = PatternFill("solid", fgColor=ORANGE)
HEAD_FONT = Font(bold=True, color="FFFFFF", size=11)
ZEBRA = PatternFill("solid", fgColor="FFF6F2")
THIN = Side(style="thin", color="E5E7EB")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
LINK_FONT = Font(color="2563EB", underline="single")

# width per column of CSV_HEADERS (same order)
WIDTHS = {
    "Category ID": 12, "Product Name": 44, "Description": 70, "Price": 13, "Stock": 8, "Item SKU": 14,
    "Logistics": 11, "Weight (g)": 11, "Package Length (cm)": 12, "Package Width (cm)": 12,
    "Package Height (cm)": 12, "Source Product URL": 42,
}


def _thumb(blob: bytes):
    try:
        from PIL import Image

        im = Image.open(io.BytesIO(blob))
        im = im.convert("RGB")
        im.thumbnail((110, 110))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=80)
        buf.seek(0)
        return buf
    except Exception:
        return None


def build_workbook(headers: list[str], rows: list[dict], meta: dict) -> bytes:
    """rows: dicts with keys cells(list matching headers), sku, title, price, cost, source_url, thumb(bytes|None)."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Shopee Upload"
    ws.append(headers)
    for c in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=c)
        cell.fill, cell.font, cell.border = HEAD_FILL, HEAD_FONT, BORDER
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        name = headers[c - 1]
        ws.column_dimensions[get_column_letter(c)].width = WIDTHS.get(name, 30 if "Image URL" in name else 14)
    ws.row_dimensions[1].height = 34

    price_col = headers.index("Price") + 1
    src_col = headers.index("Source Product URL") + 1
    desc_col = headers.index("Description") + 1
    title_col = headers.index("Product Name") + 1
    num_cols = {price_col: meta.get("price_fmt", "#,##0"), headers.index("Stock") + 1: "0",
                headers.index("Weight (g)") + 1: "#,##0"}
    img_cols = [i + 1 for i, h in enumerate(headers) if "Image URL" in h]

    for r, row in enumerate(rows, start=2):
        ws.append(row["cells"])
        ws.row_dimensions[r].height = 66
        for c in range(1, len(headers) + 1):
            cell = ws.cell(row=r, column=c)
            cell.border = BORDER
            cell.alignment = Alignment(vertical="top", wrap_text=(c in (title_col, desc_col)),
                                       horizontal="right" if c == price_col else ("center" if (c in num_cols or c > src_col - 5 and c < src_col) else "left"),
                                       indent=1 if c == price_col else 0)
            if c in num_cols:
                cell.number_format = num_cols[c]
            if r % 2 == 1:
                cell.fill = ZEBRA
        for c in img_cols + [src_col]:
            cell = ws.cell(row=r, column=c)
            if isinstance(cell.value, str) and cell.value.startswith("http"):
                cell.hyperlink = cell.value
                cell.font = LINK_FONT
        ws.cell(row=r, column=headers.index("Item SKU") + 1).font = Font(name="Consolas", size=10, bold=True)
    ws.freeze_panes = ws.cell(row=2, column=title_col + 1)
    ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{max(2, len(rows) + 1)}"
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True

    # ---- preview sheet with thumbnails
    pv = wb.create_sheet("Preview")
    pv_heads = ["Photo", "Item SKU", "Product Name", meta.get("price_label", "Price"), "Wholesale cost (KRW)", "Source Product URL"]
    pv.append(pv_heads)
    for c, w in enumerate([16, 14, 52, 14, 16, 46], start=1):
        pv.column_dimensions[get_column_letter(c)].width = w
        cell = pv.cell(row=1, column=c)
        cell.fill, cell.font, cell.border = HEAD_FILL, HEAD_FONT, BORDER
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    pv.row_dimensions[1].height = 30
    keep = []  # keep image buffers alive until save
    for r, row in enumerate(rows, start=2):
        pv.append(["", row["sku"], row["title"], row["price"], row["cost"], row["source_url"]])
        pv.row_dimensions[r].height = 88
        for c in range(1, 7):
            cell = pv.cell(row=r, column=c)
            cell.border = BORDER
            cell.alignment = Alignment(vertical="center", wrap_text=(c == 3), horizontal="right" if c in (4, 5) else "left")
            if r % 2 == 1:
                cell.fill = ZEBRA
        pv.cell(row=r, column=4).number_format = meta.get("price_fmt", "#,##0")
        pv.cell(row=r, column=5).number_format = "#,##0"
        if row["source_url"]:
            pv.cell(row=r, column=6).hyperlink = row["source_url"]
            pv.cell(row=r, column=6).font = LINK_FONT
        if row.get("thumb"):
            buf = _thumb(row["thumb"])
            if buf:
                keep.append(buf)
                img = XLImage(buf)
                ratio = img.width / max(1, img.height)
                img.height = 80
                img.width = max(30, int(80 * ratio))
                pv.add_image(img, f"A{r}")
    pv.freeze_panes = "A2"
    pv.page_setup.fitToWidth = 1
    pv.page_setup.fitToHeight = 0
    pv.sheet_properties.pageSetUpPr.fitToPage = True

    # ---- info sheet
    info = wb.create_sheet("Info")
    info.column_dimensions["A"].width = 24
    info.column_dimensions["B"].width = 90
    lines = [
        ("Generated", date.today().isoformat()),
        ("Listings", len(rows)),
        ("Language", meta.get("lang_label", "")),
        ("Price", meta.get("price_note", "")),
        ("", ""),
        ("How to use", "Sheet 'Shopee Upload' has the Shopee mass-upload columns: copy the rows into the official template"),
        ("", "(fill in Category ID) or copy the fields into Seller Center. Keep the Item SKU unchanged."),
        ("", "Image columns hold public image links; Shopee fetches the photos from them (first image = main image)."),
        ("", "Sheet 'Preview' is only for looking through the batch and is not needed for upload."),
    ]
    for k, v in lines:
        info.append([k, v])
    for r in range(1, len(lines) + 1):
        info.cell(row=r, column=1).font = Font(bold=True)
        info.cell(row=r, column=2).alignment = Alignment(wrap_text=True, vertical="top")

    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()
