"""Write plain text as a text-based PDF (Helvetica, A4), standard library only.

    python eval/make_pdf.py input.txt output.pdf

The app reads selectable PDF text (pypdf), so these are what the synthetic CVs are made of.
shortcut: Latin-1 text only and no wrapping, keep lines under 95 characters; use a PDF library if a CV needs more.
"""
import sys

LINES_PER_PAGE = 52


def _escape(line):
    return line.encode("latin-1").decode("latin-1").replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def make_pdf(text):
    """Return the bytes of a PDF holding text, one line of text per line."""
    lines = text.splitlines()
    pages = [lines[i:i + LINES_PER_PAGE] for i in range(0, len(lines), LINES_PER_PAGE)] or [[]]
    objects = ["<< /Type /Catalog /Pages 2 0 R >>", None, "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    kids = []
    for page in pages:
        stream = "BT /F1 10 Tf 13 TL 50 800 Td\n" + "".join(f"({_escape(line)}) '\n" for line in page) + "ET"
        objects.append(f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream")
        objects.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents {len(objects)} 0 R "
                       "/Resources << /Font << /F1 3 0 R >> >> >>")
        kids.append(f"{len(objects)} 0 R")
    objects[1] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(kids)} >>"
    out = b"%PDF-1.4\n"
    offsets = []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n{body}\nendobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets)
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return out


if __name__ == "__main__":
    with open(sys.argv[1], encoding="utf-8") as source, open(sys.argv[2], "wb") as target:
        target.write(make_pdf(source.read()))
