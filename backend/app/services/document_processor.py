from pathlib import Path


def parse_pdf(file_path: str) -> str:
    import pdfplumber
    text_parts = []
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                text_parts.append(text)
    return "\n".join(text_parts)


def parse_docx(file_path: str) -> str:
    from docx import Document
    doc = Document(file_path)
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    return "\n".join(paragraphs)


def parse_csv(file_path: str) -> str:
    import pandas as pd
    df = pd.read_csv(file_path)
    lines = []
    for _, row in df.iterrows():
        line = " | ".join(str(v) for v in row.values)
        lines.append(line)
    header = " | ".join(df.columns)
    return header + "\n" + "\n".join(lines)


def parse_excel(file_path: str) -> str:
    import pandas as pd
    df = pd.read_excel(file_path)
    lines = []
    for _, row in df.iterrows():
        line = " | ".join(str(v) for v in row.values)
        lines.append(line)
    header = " | ".join(df.columns)
    return header + "\n" + "\n".join(lines)


def parse_document(file_path: str) -> str:
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
