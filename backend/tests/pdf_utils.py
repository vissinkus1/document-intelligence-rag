"""Builds tiny valid PDFs by hand so tests need no extra libraries."""
import textwrap


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def make_pdf(pages: list[str]) -> bytes:
    n = len(pages)
    page_ids = [4 + 2 * i for i in range(n)]
    objs: dict[int, bytes] = {
        1: b"<</Type/Catalog/Pages 2 0 R>>",
        2: ("<</Type/Pages/Kids[" + " ".join(f"{i} 0 R" for i in page_ids) + f"]/Count {n}>>").encode(),
        3: b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>",
    }
    for i, text in enumerate(pages):
        pid, cid = 4 + 2 * i, 5 + 2 * i
        lines = textwrap.wrap(text, 90) if text else []
        body = "BT /F1 11 Tf 40 750 Td 14 TL " + " ".join(f"({_esc(l)}) Tj T*" for l in lines) + " ET"
        stream = body.encode("latin-1")
        objs[pid] = (
            f"<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]"
            f"/Resources<</Font<</F1 3 0 R>>>>/Contents {cid} 0 R>>"
        ).encode()
        objs[cid] = b"<</Length " + str(len(stream)).encode() + b">>\nstream\n" + stream + b"\nendstream"

    out = b"%PDF-1.4\n"
    offsets = {}
    for num in sorted(objs):
        offsets[num] = len(out)
        out += f"{num} 0 obj\n".encode() + objs[num] + b"\nendobj\n"
    xref = len(out)
    size = max(objs) + 1
    out += f"xref\n0 {size}\n".encode() + b"0000000000 65535 f \n"
    for num in range(1, size):
        out += f"{offsets[num]:010d} 00000 n \n".encode()
    out += f"trailer\n<</Size {size}/Root 1 0 R>>\nstartxref\n{xref}\n%%EOF\n".encode()
    return out
