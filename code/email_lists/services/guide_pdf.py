"""One-page-or-more guide PDF for the email lists screen. Built-in Helvetica, no extra library."""

from __future__ import annotations

PAGE_WIDTH = 595
PAGE_HEIGHT = 842
MARGIN_X = 48
TOP = 800
BOTTOM = 56


def build_guide_pdf() -> bytes:
    pages = _paginate(_blocks())
    return _document(pages)


def _blocks() -> list[tuple[str, str]]:
    return [
        ("title", "Guia da página Listas de e-mail"),
        ("meta", "Claro RF Check"),
        (
            "body",
            "Este guia descreve somente a página Listas de e-mail. Ela cadastra listas e inclui endereços digitados ou vindos de um CSV exportado do Outlook.",
        ),
        ("heading", "1. Adicionar endereços"),
        (
            "body",
            "Bloco do topo. Cria uma lista nova ou acrescenta endereços em uma lista que já existe. Dá para digitar os e-mails, enviar um CSV, ou fazer os dois juntos.",
        ),
        ("heading", "2. Guide"),
        (
            "body",
            "Botão no canto direito do bloco Adicionar endereços. Baixa este PDF.",
        ),
        ("heading", "3. Nova lista"),
        (
            "body",
            "Opção da esquerda. Ao selecionar, aparece o campo Nome da lista. O menu de listas existentes fica escondido.",
        ),
        ("heading", "4. Lista existente"),
        (
            "body",
            "Opção da direita. Ao selecionar, aparece o menu Lista. O campo de nome fica escondido. Os endereços entram na lista escolhida.",
        ),
        ("heading", "5. Nome da lista"),
        (
            "body",
            "Nome da lista que será criada. Não pode repetir um nome já usado, mesmo que a diferença seja só de maiúsculas.",
        ),
        ("heading", "6. Lista"),
        (
            "body",
            "Menu usado apenas em Lista existente. Escolha qual lista recebe os endereços.",
        ),
        ("heading", "7. Endereços"),
        (
            "body",
            "Campo de texto. Separe os e-mails por vírgula, ponto e vírgula ou linha. Cada endereço precisa ter @. Texto sem @ é rejeitado e a mensagem mostra o valor. Endereço repetido na mesma lista entra uma vez só.",
        ),
        ("heading", "8. CSV do Outlook"),
        (
            "body",
            "Área tracejada abaixo dos endereços. Clique para escolher um arquivo .csv de até 5 MB. O arquivo precisa ter a coluna E-mail Address. Pode estar em UTF-8 ou Windows-1252. Se a coluna faltar, nada é gravado.",
        ),
        ("heading", "9. Incluir endereços"),
        (
            "body",
            "Botão azul no fim do formulário. Grava os e-mails digitados e os do CSV. Se houver erro, a página não recarrega: o que foi digitado permanece e a mensagem aparece acima do formulário.",
        ),
        ("heading", "10. Mensagens"),
        (
            "body",
            "Faixa acima do formulário. Verde quando a inclusão funciona. Vermelha quando algo é rejeitado: endereço sem @, nome vazio, nome repetido, arquivo que não é CSV ou CSV sem a coluna E-mail Address.",
        ),
        ("heading", "11. Listas salvas"),
        (
            "body",
            "Bloco de baixo. Mostra cada lista e quantos endereços ela tem. Clicar em uma lista troca só esse bloco. A página não recarrega e não volta ao topo.",
        ),
        ("heading", "12. Endereços da lista selecionada"),
        (
            "body",
            "Tabela com os e-mails da lista aberta. Remover tira um endereço sem recarregar a página.",
        ),
        ("heading", "13. Exportar CSV"),
        (
            "body",
            "Botão ao lado de Excluir lista, visível quando uma lista está selecionada. Baixa essa lista em CSV, com a coluna E-mail Address, no mesmo formato aceito pela inclusão.",
        ),
        ("heading", "14. Excluir lista"),
        (
            "body",
            "Apaga a lista selecionada e todos os endereços dela.",
        ),
        ("heading", "Regras"),
        ("body", "Endereço sem @ não é salvo."),
        ("body", "Se todos os endereços forem inválidos, a lista nova não é criada."),
        ("body", "Endereços válidos enviados junto com inválidos são salvos. Os inválidos aparecem na mensagem."),
        ("body", "Duplicados são ignorados e informados na mensagem de sucesso."),
        ("body", "O CSV exportado pode ser incluído de novo nesta página."),
    ]


def _paginate(blocks: list[tuple[str, str]]) -> list[bytes]:
    pages: list[list[tuple[int, str, int]]] = [[]]
    y = TOP
    for kind, text in blocks:
        size, gap = _style(kind)
        for line in _wrap(text, 92 if kind == "body" else 78):
            if y - gap < BOTTOM:
                pages.append([])
                y = TOP
            pages[-1].append((size, line if kind != "body" else line, gap))
            y -= gap
        y -= 4
    return [_paint(page) for page in pages if page]


def _style(kind: str) -> tuple[int, int]:
    if kind == "title":
        return 18, 28
    if kind == "heading":
        return 13, 22
    if kind == "meta":
        return 11, 20
    return 11, 16


def _paint(lines: list[tuple[int, str, int]]) -> bytes:
    y = TOP
    commands = ["BT"]
    for size, text, gap in lines:
        font = "F2" if size >= 13 else "F1"
        commands.append(f"/{font} {size} Tf")
        commands.append(f"1 0 0 1 {MARGIN_X} {y} Tm")
        commands.append(f"({_escape(text)}) Tj")
        y -= gap
    commands.append("ET")
    return "\n".join(commands).encode("latin-1")


def _wrap(text: str, width: int) -> list[str]:
    words = text.split()
    if not words:
        return [""]
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if len(candidate) <= width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _escape(text: str) -> str:
    encoded = text.encode("latin-1", errors="replace").decode("latin-1")
    return encoded.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _document(page_streams: list[bytes]) -> bytes:
    count = len(page_streams)
    font = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"
    font_bold = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>"
    contents = []
    for stream in page_streams:
        contents.append(b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream")

    content_start = 5
    page_start = content_start + count
    content_ids = list(range(content_start, content_start + count))
    page_ids = list(range(page_start, page_start + count))

    kids = " ".join(f"{number} 0 R" for number in page_ids)
    pages = f"<< /Type /Pages /Count {count} /Kids [{kids}] >>".encode("ascii")
    catalog = b"<< /Type /Catalog /Pages 2 0 R >>"

    page_objects = []
    for content_id in content_ids:
        page_objects.append(
            (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_WIDTH} {PAGE_HEIGHT}] "
                f"/Contents {content_id} 0 R /Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> >>"
            ).encode("ascii")
        )

    objects = [catalog, pages, font, font_bold, *contents, *page_objects]
    return _serialize(objects)


def _serialize(objects: list[bytes]) -> bytes:
    header = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"
    chunks = [header]
    offsets = [0]
    for number, obj in enumerate(objects, start=1):
        offsets.append(sum(len(part) for part in chunks))
        chunks.append(f"{number} 0 obj\n".encode("ascii"))
        chunks.append(obj)
        chunks.append(b"\nendobj\n")
    xref_at = sum(len(part) for part in chunks)
    size = len(objects) + 1
    xref = [f"xref\n0 {size}\n".encode("ascii"), b"0000000000 65535 f \n"]
    for offset in offsets[1:]:
        xref.append(f"{offset:010d} 00000 n \n".encode("ascii"))
    trailer = f"trailer\n<< /Size {size} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF\n".encode("ascii")
    return b"".join(chunks + xref + [trailer])
