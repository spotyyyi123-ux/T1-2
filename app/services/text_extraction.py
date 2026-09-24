"""Extract the text layer with locations; no OCR or document rendering."""

import docx
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph
from pypdf import PdfReader


def extract_text(file_path: str) -> str:
    blocks = []
    if file_path.lower().endswith('.pdf'):
        with open(file_path, 'rb') as stream:
            for number, page in enumerate(PdfReader(stream).pages, 1):
                text = page.extract_text() or ''
                if text.strip():
                    blocks.append(f'[Страница {number}]\n{text}')
    elif file_path.lower().endswith('.docx'):
        document = docx.Document(file_path)
        counts = {'paragraph': 0, 'table': 0}

        def walk(element, parent):
            for child in element.iterchildren():
                if child.tag == qn('w:p'):
                    counts['paragraph'] += 1
                    text = Paragraph(child, parent).text
                    if text.strip():
                        yield f"[Абзац {counts['paragraph']}]\n{text}"
                elif child.tag == qn('w:tbl'):
                    counts['table'] += 1
                    table_number = counts['table']
                    table_blocks = []
                    seen_cells = set()
                    for row_number, row in enumerate(Table(child, parent).rows, 1):
                        row_blocks = []
                        for cell in row.cells:
                            # Merged cells repeat in the python-docx row API.
                            if cell._tc not in seen_cells:
                                seen_cells.add(cell._tc)
                                row_blocks.extend(walk(cell._tc, cell))
                        if row_blocks:
                            table_blocks.append(f'[Строка таблицы {table_number}: {row_number}]\n' + '\n'.join(row_blocks))
                    if table_blocks:
                        yield f"[Таблица {table_number}]\n" + '\n'.join(table_blocks)
                elif child.tag in {qn('w:sdt'), qn('w:sdtContent')}:
                    yield from walk(child, parent)

        blocks.extend(walk(document.element.body, document))
        seen_headers = set()
        for number, section in enumerate(document.sections, 1):
            for kind in ('header', 'footer', 'first_page_header', 'first_page_footer',
                         'even_page_header', 'even_page_footer'):
                container = getattr(section, kind)
                if container.is_linked_to_previous or container._element in seen_headers:
                    continue
                seen_headers.add(container._element)
                content = list(walk(container._element, container))
                if content:
                    blocks.append(f'[Колонтитул {number}, {kind}]\n' + '\n'.join(content))
    return '\n\n'.join(blocks)
