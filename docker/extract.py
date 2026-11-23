"""Text aus PDF- und Word-Anhängen auslesen – als eigener, eng begrenzter Prozess.

Der Server startet dieses Skript pro Datei und gibt ihm KEINE Zugangsdaten mit (leere Umgebung).
Präparierte Dateien können hier höchstens diesen Prozess lahmlegen – er wird nach Zeit- und
Speicherlimit hart beendet; der Server und seine Keys bleiben unberührt.

Aufruf:  python extract.py <pdf|docx> <max_zeichen>   (Datei kommt über stdin, Ergebnis als JSON über stdout)
"""
import html
import io
import json
import re
import resource
import sys
import zipfile

CPU_SECONDS = 20
MEMORY_BYTES = 768 * 1024 * 1024
MAX_PAGES = 300
MAX_XML = 50 * 1024 * 1024


def _limits() -> None:
    resource.setrlimit(resource.RLIMIT_CPU, (CPU_SECONDS, CPU_SECONDS))
    resource.setrlimit(resource.RLIMIT_AS, (MEMORY_BYTES, MEMORY_BYTES))
    resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))
    resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))          # darf keine Dateien schreiben


class Fail(Exception):
    pass


def docx(raw: bytes) -> dict:
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            info = z.getinfo("word/document.xml")
            if info.file_size > MAX_XML:
                raise Fail("Dokument zu groß")
            with z.open(info) as fh:
                data = fh.read(MAX_XML + 1)            # nie mehr lesen als erlaubt – auch bei gefälschter Größenangabe
            if len(data) > MAX_XML:
                raise Fail("Dokument zu groß")
    except (zipfile.BadZipFile, KeyError, EOFError, OSError):
        raise Fail("kein gültiges Word-Dokument (.docx)")
    xml = data.decode("utf-8", errors="replace")
    xml = re.sub(r"<w:tab/>", "\t", xml)
    xml = re.sub(r"</w:p>|<w:br/>", "\n", xml)
    return {"text": html.unescape(re.sub(r"<[^>]+>", "", xml)), "kind": "Word"}


def pdf(raw: bytes) -> dict:
    try:
        from pypdf import PdfReader
    except ImportError:
        raise Fail("PDF wird nicht unterstützt (pypdf fehlt)")
    try:
        reader = PdfReader(io.BytesIO(raw))
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception:
                raise Fail("PDF ist passwortgeschützt")
        n = len(reader.pages)
        pages = [(reader.pages[i].extract_text() or "") for i in range(min(n, MAX_PAGES))]
    except Fail:
        raise
    except Exception as e:
        raise Fail(f"PDF lässt sich nicht lesen ({e.__class__.__name__})")
    text = "\n\n".join(f"--- Seite {i + 1} ---\n{t.strip()}" for i, t in enumerate(pages) if t.strip())
    if not text:
        raise Fail("PDF enthält keinen lesbaren Text (eingescannt?) – als Foto/Bild schicken")
    note = f", nur die ersten {MAX_PAGES}" if n > MAX_PAGES else ""
    return {"text": text, "kind": f"PDF, {n} Seite{'n' if n != 1 else ''}{note}"}


def main() -> None:
    _limits()
    kind, max_chars = sys.argv[1], int(sys.argv[2])
    raw = sys.stdin.buffer.read()
    try:
        res = {"pdf": pdf, "docx": docx}[kind](raw)
        text = res["text"].strip()
        res.update(text=text[:max_chars], cut=len(text) > max_chars)
    except Fail as e:
        res = {"error": str(e)}
    sys.stdout.write(json.dumps(res, ensure_ascii=False))


if __name__ == "__main__":
    main()
