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
    text_parts = []
    for p in doc.paragraphs:
        if p.text.strip():
            text_parts.append(p.text.strip())
            
    for table in doc.tables:
        for row in table.rows:
            row_text = " | ".join(cell.text.strip() for cell in row.cells if cell.text.strip())
            if row_text:
                text_parts.append(row_text)
                
    return "\n".join(text_parts)


def parse_csv(file_path: str) -> str:
    import pandas as pd
    try:
        df = pd.read_csv(file_path, encoding='utf-8')
    except UnicodeDecodeError:
        df = pd.read_csv(file_path, encoding='latin1')
    
    df = df.fillna("")
    columns = df.columns.tolist()
    lines = []
    for _, row in df.iterrows():
        row_str = ", ".join(f"{col}: {val}" for col, val in zip(columns, row.values))
        lines.append(row_str)
    return "\n".join(lines)


def parse_excel(file_path: str) -> str:
    import pandas as pd
    df = pd.read_excel(file_path)
    df = df.fillna("")
    columns = df.columns.tolist()
    lines = []
    for _, row in df.iterrows():
        row_str = ", ".join(f"{col}: {val}" for col, val in zip(columns, row.values))
        lines.append(row_str)
    return "\n".join(lines)


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
