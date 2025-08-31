import os
import re
import json
import asyncio
import tempfile
from pathlib import Path
from typing import List, Dict

from dotenv import load_dotenv
from pypdf import PdfReader
import tiktoken

from telegram import Update, InputFile
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

from openai import OpenAI

import prompts

load_dotenv()

OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5")
MAX_QA_PER_SECTION = int(os.getenv("MAX_QA_PER_SECTION", "4"))

client = OpenAI(api_key=OPENAI_API_KEY)  # Responses API client (official SDK). 

# ---------- Utilities ----------

def extract_text_from_pdf(pdf_path: str) -> List[str]:
    """Return list of page texts."""
    reader = PdfReader(pdf_path)
    pages = []
    for page in reader.pages:
        text = page.extract_text() or ""
        # Normalize whitespace
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{2,}", "\n", text).strip()
        pages.append(text)
    return pages

def pages_to_sections(pages: List[str]) -> List[Dict]:
    """
    Split PDF into sections using simple heading heuristics; fallback by page blocks.
    Returns [{"title": "...", "text": "..."}]
    """
    raw = "\n\n".join(pages)
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]

    sections = []
    buf = []
    cur_title = "Introduction"

    def push(title, body_list):
        body = "\n".join(body_list).strip()
        if body:
            sections.append({"title": title[:120], "text": body})

    heading_re = re.compile(
        r"^(Chapter\s+\d+[:.\-\s].+|Section\s+\d+[:.\-\s].+|\d+\.\s+.+|[A-Z][A-Z0-9 \-:&]{6,})$"
    )

    for ln in lines:
        if heading_re.match(ln) and (len(buf) > 300 or not sections):
            # new section
            push(cur_title, buf)
            cur_title = re.sub(r"\s+", " ", ln).title()
            buf = []
        else:
            buf.append(ln)
    push(cur_title, buf)

    # If we somehow got too few sections, fallback: chunk every ~1400 tokens by character length.
    if len(sections) < 3:
        merged = "\n\n".join(pages)
        sections = []
        chunk_size = 8000  # chars ~ safe default; we’ll re-trim per request
        for i in range(0, len(merged), chunk_size):
            chunk = merged[i:i+chunk_size]
            if chunk.strip():
                sections.append({"title": f"Part {len(sections)+1}", "text": chunk})
    return sections

def clamp_for_model(text: str, max_tokens: int = 6000) -> str:
    """
    Roughly limit tokens for a single request using tiktoken; trim if needed.
    """
    enc = tiktoken.get_encoding("cl100k_base")
    toks = enc.encode(text)
    if len(toks) <= max_tokens:
        return text
    toks = toks[:max_tokens]
    return enc.decode(toks)

async def call_openai_section(section_title: str, section_text: str) -> Dict:
    """
    Use Responses API to get structured Q&A JSON for a section.
    """
    section_text = clamp_for_model(section_text, 6000)
    system = prompts.SYSTEM_PROMPT
    user = prompts.SECTION_USER_PROMPT + f"\n\nMAX_QA_PER_SECTION={MAX_QA_PER_SECTION}\n\nSECTION_TITLE: {section_title}\n\nSECTION_TEXT:\n{section_text}"
    resp = client.responses.create(
        model=OPENAI_MODEL,
        input=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        response_format={"type": "json_object"},
    )
    try:
        data = json.loads(resp.output_text)
        # normalize
        data.setdefault("section_title", section_title)
        data.setdefault("qa", [])
        data.setdefault("key_topics", [])
        return data
    except Exception:
        # Fallback minimal structure
        return {
            "section_title": section_title,
            "qa": [{"q": "Summary of this section?", "a": ["- " + section_text[:300] + "..."]}],
            "key_topics": []
        }

async def call_openai_extra(all_text: str) -> Dict:
    system = prompts.SYSTEM_PROMPT
    user = prompts.EXTRA_QA_PROMPT + f"\n\nCHAPTER_TEXT:\n{clamp_for_model(all_text, 12000)}"
    resp = client.responses.create(
        model=OPENAI_MODEL,
        input=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        response_format={"type": "json_object"},
    )
    try:
        return json.loads(resp.output_text)
    except Exception:
        return {"comprehension": [], "revision": []}

def render_markdown(chapter_title: str, per_section: List[Dict], extras: Dict) -> str:
    out = [f"# {chapter_title}\n"]
    for sec in per_section:
        out.append(f"## {sec.get('section_title','Section')}")
        for i, qa in enumerate(sec.get("qa", []), start=1):
            out.append(f"**Q{i}. {qa.get('q','')}**")
            bullets = qa.get("a", [])
            for b in bullets:
                out.append(f"- {b}")
            out.append("")  # blank line
        if sec.get("key_topics"):
            out.append("_Key topics_: " + ", ".join(sec["key_topics"]))
        out.append("")  # space between sections

    # Extras
    out.append("## Comprehension-Based Q&A (Whole Chapter)")
    for i, qa in enumerate(extras.get("comprehension", []), start=1):
        out.append(f"**Q{i}. {qa.get('q','')}**")
        for b in qa.get("a", []):
            out.append(f"- {b}")
        out.append("")

    out.append("## Extra Revision Q&A (Cross-Linking)")
    for i, qa in enumerate(extras.get("revision", []), start=1):
        out.append(f"**Q{i}. {qa.get('q','')}**")
        for b in qa.get("a", []):
            out.append(f"- {b}")
        out.append("")

    return "\n".join(out).strip()

# ---------- Telegram Handlers ----------

WELCOME = (
    "Hi! Send me a *chapter PDF*.\n"
    "I'll split it into sections and return short, bullet-point Q&A for each section,\n"
    "plus comprehension Q&A and extra revision questions. 🔍📘"
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(WELCOME, parse_mode="Markdown")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Just upload a PDF chapter. Optional: set MAX_QA_PER_SECTION via env.\n"
        "Outputs will be returned as a .md file to avoid message length limits."
    )

async def handle_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if not doc or not doc.mime_type or "pdf" not in doc.mime_type:
        await update.message.reply_text("Please send a PDF file.")
        return

    await update.message.reply_text("Got it! Processing your chapter… ⏳")

    with tempfile.TemporaryDirectory() as tmpd:
        file_path = Path(tmpd) / doc.file_name
        file = await doc.get_file()
        await file.download_to_drive(custom_path=str(file_path))

        pages = extract_text_from_pdf(str(file_path))
        if not any(pages):
            await update.message.reply_text("Couldn't extract text from this PDF. Is it scanned? Try a text-based PDF.")
            return

        sections = pages_to_sections(pages)
        chapter_title = sections[0]["title"] if sections else (doc.file_name or "Chapter")

        # Call OpenAI per section (in parallel)
        tasks = [call_openai_section(s["title"], s["text"]) for s in sections]
        per_section = await asyncio.gather(*tasks)

        # Extras from whole chapter text
        all_text = "\n\n".join([s["text"] for s in sections])
        extras = await call_openai_extra(all_text)

        # Render to Markdown and send as file
        md = render_markdown(chapter_title, per_section, extras)
        out_path = Path(tmpd) / f"{Path(doc.file_name).stem}_QA.md"
        out_path.write_text(md, encoding="utf-8")

        with out_path.open("rb") as f:
            await update.message.reply_document(
                document=InputFile(f, filename=out_path.name),
                caption="Here’s your Q&A pack. ✅"
            )

def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(MessageHandler(filters.Document.PDF, handle_pdf))
    app.add_handler(MessageHandler(filters.ATTACHMENT, handle_pdf))
    app.run_polling()

if __name__ == "__main__":
    main()
