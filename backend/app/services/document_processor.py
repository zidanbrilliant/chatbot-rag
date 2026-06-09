from pathlib import Path


def parse_pdf(file_path: str) -> list[dict]:
    import pdfplumber

    parts = []
    with pdfplumber.open(file_path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text()
            if text:
                parts.append({"text": text, "page_number": i + 1})
    return parts


def parse_docx(file_path: str) -> list[dict]:
    from docx import Document

    doc = Document(file_path)
    text_parts = []
    for p in doc.paragraphs:
        if p.text.strip():
            text_parts.append(p.text.strip())
    for table in doc.tables:
        for row in table.rows:
            row_text = " | ".join(cell.text.strip() for cell in row.cells if cell.text.strip())
            if row_text:
                text_parts.append(row_text)
    return [{"text": "\n".join(text_parts), "page_number": None}]


def _parse_tabular(
    file_path: str,
    file_name: str,
    sheet_name: str | None,
    columns: list[str],
    rows: list[list[str]],
) -> str:
    lines = [
        f"Konteks dokumen: {file_name}",
    ]
    if sheet_name:
        lines.append(f"Sheet: {sheet_name}")

    col_labels = [c.strip() for c in columns]

    for i, row in enumerate(rows):
        cells = []
        for j, val in enumerate(row):
            label = col_labels[j] if j < len(col_labels) else f"Kolom{j}"
            cells.append(f"{label}: {val}")
        lines.append(f"  [{i + 1}] {' | '.join(cells)}")

        if (i + 1) % 5 == 0 and (i + 1) < len(rows):
            lines.append("---")

    return "\n".join(lines)


def parse_csv(file_path: str) -> list[dict]:
    import pandas as pd

    file_name = Path(file_path).name
    try:
        df = pd.read_csv(file_path, encoding="utf-8")
    except UnicodeDecodeError:
        df = pd.read_csv(file_path, encoding="latin1")
    df = df.fillna("")
    columns = df.columns.tolist()
    rows = [[str(v) for v in row.values] for _, row in df.iterrows()]
    return [{"text": _parse_tabular(file_path, file_name, None, columns, rows), "page_number": None}]


def parse_excel(file_path: str) -> list[dict]:
    import pandas as pd

    file_name = Path(file_path).name
    xls = pd.ExcelFile(file_path)
    all_sheets = []
    for sheet in xls.sheet_names:
        df = pd.read_excel(file_path, sheet_name=sheet)
        df = df.fillna("")
        columns = df.columns.tolist()
        rows = [[str(v) for v in row.values] for _, row in df.iterrows()]
        sheet_text = _parse_tabular(file_path, file_name, sheet, columns, rows)
        all_sheets.append(sheet_text)
    return [{"text": "\n\n".join(all_sheets), "page_number": None}]


def parse_document(file_path: str) -> list[dict]:
    ext = Path(file_path).suffix.lower()
    if ext == ".pdf":
        return parse_pdf(file_path)
    elif ext == ".docx":
        return parse_docx(file_path)
    elif ext == ".csv":
        return parse_csv(file_path)
    elif ext == ".xlsx":
        return parse_excel(file_path)
    else:
        raise ValueError(f"Unsupported file type: {ext}")
