from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_cors import CORS
import requests as http_requests
from groq import Groq
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.colors import HexColor
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER
import datetime, time, io, json, re, os

app = Flask(__name__, static_folder=".", static_url_path="")
CORS(app)

# Set your free Groq API key in the GROQ_API_KEY environment variable.
# Get one at: https://console.groq.com/keys
#   Windows:  setx GROQ_API_KEY "your_key_here"   (then reopen the terminal)
#   macOS/Linux:  export GROQ_API_KEY="your_key_here"
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
groq_client  = Groq(api_key=GROQ_API_KEY or "GROQ_KEY_NOT_SET")

MENTOR_PROMPT = """You are Scholar AI — a world-class Research Mentor and Academic Guide.

ABILITY 1 — RESEARCH MENTOR:
You are an expert professor covering: research types, full research process, literature reviews, hypothesis formulation, data collection & analysis, paper writing (abstract, intro, methodology, results, discussion, conclusion), citation styles (APA, MLA, IEEE, Chicago), research ethics, plagiarism, publishing in journals, PhD/Masters thesis guidance.

ABILITY 2 — PAPER SEARCHER:
When the user wants to find papers, embed this tag:
[PAPER_SEARCH:{"topic":"topic here","start_year":2022,"end_year":2026,"count":5}]
Detect: "search papers on X", "find papers about X", "show research on X", "papers on X from Y to Z", "latest research on X"

RULES:
- Warm, encouraging, mentor-like — like a caring senior professor
- Use **bold** for key terms, numbered lists for steps
- Practical and actionable with real examples
- Default: 2022-2026 year range, 5 papers unless specified
- Always respond in English"""


# ═══════════════════════════════════════════════════
# CORE HELPERS
# ═══════════════════════════════════════════════════

def _reconstruct_abstract(inv_index):
    """OpenAlex returns abstracts as an inverted index {word: [positions]}."""
    if not inv_index:
        return ""
    positions = []
    for word, idxs in inv_index.items():
        for i in idxs:
            positions.append((i, word))
    positions.sort()
    return " ".join(w for _, w in positions)


def fetch_openalex(topic, count, start_year, end_year):
    """Primary source: OpenAlex — 250M+ works, no API key, generous rate limits."""
    url = "https://api.openalex.org/works"
    params = {
        "search": topic,
        "filter": f"from_publication_date:{start_year}-01-01,to_publication_date:{end_year}-12-31",
        "per-page": min(count, 25),
        "sort": "relevance_score:desc",
        "mailto": "scholarai@example.com",  # polite pool → faster, more reliable
    }
    r = http_requests.get(url, params=params, timeout=20)
    if r.status_code != 200:
        return None  # signal failure → caller falls back
    papers = []
    for w in r.json().get("results", []):
        loc = w.get("primary_location") or {}
        src = loc.get("source") or {}
        link = loc.get("landing_page_url") or w.get("doi") or w.get("id") or "#"
        authors = [a.get("author", {}).get("display_name", "")
                   for a in (w.get("authorships") or [])[:4]]
        papers.append({
            "title":    w.get("title") or "No title",
            "abstract": _reconstruct_abstract(w.get("abstract_inverted_index")) or "No abstract available",
            "year":     w.get("publication_year") or "Unknown",
            "url":      link,
            "authors":  [a for a in authors if a],
            "venue":    src.get("display_name") or "",
        })
    return papers


def fetch_semantic_scholar(topic, count, start_year, end_year):
    """Fallback source: Semantic Scholar (keyless — heavily rate limited)."""
    url = "https://api.semanticscholar.org/graph/v1/paper/search"
    params = {
        "query": topic,
        "limit": min(count, 20),
        "fields": "title,abstract,year,url,authors,venue",
        "publicationDateOrYear": f"{start_year}:{end_year}"
    }
    for attempt in range(2):
        try:
            r = http_requests.get(url, params=params, timeout=15)
            if r.status_code == 200:
                papers = []
                for p in r.json().get("data", []):
                    authors = [a.get("name", "") for a in p.get("authors", [])[:4]]
                    papers.append({
                        "title":    p.get("title") or "No title",
                        "abstract": p.get("abstract") or "No abstract available",
                        "year":     p.get("year") or "Unknown",
                        "url":      p.get("url") or "#",
                        "authors":  authors,
                        "venue":    p.get("venue") or ""
                    })
                return papers
            elif r.status_code == 429:
                time.sleep(4 * (attempt + 1))
            else:
                return []
        except Exception as e:
            print(f"Semantic Scholar error: {e}")
            time.sleep(2)
    return []


def fetch_papers(topic, count, start_year, end_year):
    """Try OpenAlex first; on any failure fall back to Semantic Scholar."""
    try:
        result = fetch_openalex(topic, count, start_year, end_year)
        if result:  # non-empty list
            return result
    except Exception as e:
        print(f"OpenAlex error: {e}")
    return fetch_semantic_scholar(topic, count, start_year, end_year)


def summarize_one(title, abstract, size="short"):
    if not abstract or abstract == "No abstract available":
        return "No abstract available to summarize."
    inst = (
        "Summarize this research paper in 5-6 detailed sentences. Cover the objective, methodology, key findings, and significance."
        if size == "detailed" else
        "Summarize this research paper in 2-3 clear sentences focusing on the core contribution and finding."
    )
    try:
        r = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": f"You are a research assistant. {inst}"},
                {"role": "user",   "content": f"Title: {title}\nAbstract: {abstract}"}
            ],
            max_tokens=400
        )
        return r.choices[0].message.content
    except Exception as e:
        return f"Summary unavailable: {e}"


def build_combined_summary(topic, papers):
    if not papers:
        return ""
    abstracts_text = "\n\n".join([
        f"Paper {i+1} — {p['title']} ({p.get('year','?')}):\n{p['abstract']}"
        for i, p in enumerate(papers[:8])
        if p.get('abstract') and p['abstract'] != 'No abstract available'
    ])
    if not abstracts_text:
        return ""
    try:
        r = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "You are a research synthesis expert. Given multiple paper abstracts, write a 5-7 sentence synthesized research overview covering: dominant themes, common methodologies, major findings, emerging trends, and identified gaps. Be specific."},
                {"role": "user", "content": f"Topic: {topic}\n\n{abstracts_text}\n\nWrite a synthesized research overview:"}
            ],
            max_tokens=600
        )
        return r.choices[0].message.content
    except Exception as e:
        return ""


def build_pdf(papers, topics, start_year, end_year, output_type, topic_summaries=None):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
        rightMargin=0.75*inch, leftMargin=0.75*inch,
        topMargin=0.9*inch, bottomMargin=0.9*inch)

    styles = getSampleStyleSheet()
    gold   = HexColor('#F0B429')
    dark   = HexColor('#111827')
    muted  = HexColor('#6B7280')
    amber  = HexColor('#FFFBEB')

    title_s = ParagraphStyle("T", parent=styles["Title"],
        fontSize=20, spaceAfter=5, textColor=dark, alignment=TA_CENTER)
    sub_s = ParagraphStyle("ST", parent=styles["Normal"],
        fontSize=10, spaceAfter=3, textColor=muted, alignment=TA_CENTER)
    topic_s = ParagraphStyle("TH", parent=styles["Heading1"],
        fontSize=14, spaceAfter=6, spaceBefore=14, textColor=dark)
    overview_s = ParagraphStyle("OV", parent=styles["Normal"],
        fontSize=9.5, spaceAfter=10, textColor=HexColor('#374151'),
        backColor=amber, borderPadding=8, leading=15)
    head_s = ParagraphStyle("H", parent=styles["Heading2"],
        fontSize=11, spaceAfter=3, spaceBefore=9, textColor=dark)
    body_s = ParagraphStyle("B", parent=styles["Normal"],
        fontSize=9.5, spaceAfter=4, textColor=HexColor('#374151'), leading=14)
    meta_s = ParagraphStyle("M", parent=styles["Normal"],
        fontSize=8.5, textColor=muted, spaceAfter=2)
    link_s = ParagraphStyle("L", parent=styles["Normal"],
        fontSize=9, textColor=HexColor('#2563EB'), spaceAfter=4)

    def c(t):
        return str(t).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")

    content = []
    content.append(Spacer(1, 0.15*inch))
    content.append(Paragraph("Scholar AI — Research Report", title_s))
    content.append(Paragraph(
        f"Topics: {', '.join(topics)} &nbsp;·&nbsp; {start_year}–{end_year} &nbsp;·&nbsp; {len(papers)} Papers",
        sub_s))
    content.append(Paragraph(
        f"Generated: {datetime.datetime.now().strftime('%B %d, %Y at %H:%M')}",
        sub_s))
    content.append(HRFlowable(width="100%", thickness=1.5, color=gold, spaceAfter=12))

    for topic in topics:
        tp = [p for p in papers if p.get("topic") == topic]
        if not tp:
            continue
        content.append(Paragraph(f"📌 {topic.title()}", topic_s))
        content.append(HRFlowable(width="100%", thickness=0.5, color=HexColor('#E5E7EB'), spaceAfter=8))

        if topic_summaries and topic_summaries.get(topic):
            content.append(Paragraph(
                f"<b>Research Overview:</b> {c(topic_summaries[topic])}", overview_s))
            content.append(Spacer(1, 0.08*inch))

        for i, p in enumerate(tp):
            content.append(Paragraph(f"{i+1}. {c(p['title'])} ({p.get('year','?')})", head_s))
            if p.get('authors'):
                au = ", ".join(p['authors'][:3])
                if len(p.get('authors', [])) > 3: au += " et al."
                content.append(Paragraph(f"Authors: {c(au)}", meta_s))
            if p.get('venue'):
                content.append(Paragraph(f"Published in: {c(p['venue'])}", meta_s))
            content.append(Paragraph(
                f"<link href='{p.get('url','#')}' color='#2563EB'>{c(p.get('url','N/A'))}</link>", link_s))

            if output_type in ('abstract', 'both'):
                content.append(Paragraph(f"<b>Abstract:</b> {c(p.get('abstract',''))}", body_s))
            if output_type in ('summary', 'both'):
                s = p.get('summary') or p.get('output') or ''
                if s:
                    content.append(Paragraph(f"<b>AI Summary:</b> {c(s)}", body_s))
            content.append(Spacer(1, 0.1*inch))

    doc.build(content)
    buf.seek(0)
    return buf


# ═══════════════════════════════════════════════════
# ROUTES
# ═══════════════════════════════════════════════════

@app.route("/")
def index():
    return send_from_directory(".", "index.html")

@app.route("/api/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/api/search", methods=["POST"])
def api_search():
    data         = request.json or {}
    topics       = data.get("topics", [])
    count        = int(data.get("count", 5))
    start_year   = int(data.get("start_year", 2022))
    end_year     = int(data.get("end_year", 2026))
    output_type  = data.get("output_type", "abstract")
    summary_size = data.get("summary_size", "short")

    if not topics:
        return jsonify({"error": "No topics"}), 400

    all_papers, topic_summaries = [], {}

    for i, topic in enumerate(topics):
        papers = fetch_papers(topic, count, start_year, end_year)
        for p in papers:
            p["topic"] = topic
            if output_type in ("summary", "both"):
                p["summary"] = summarize_one(p["title"], p["abstract"], summary_size)
            p["output"] = p.get("summary") if output_type == "summary" else p["abstract"]

        all_papers.extend(papers)

        if output_type in ("summary", "both") and papers:
            topic_summaries[topic] = build_combined_summary(topic, papers)

        if i < len(topics) - 1:
            time.sleep(2)

    return jsonify({
        "papers": all_papers,
        "total": len(all_papers),
        "topics": topics,
        "topic_summaries": topic_summaries
    })


@app.route("/api/export", methods=["POST"])
def api_export():
    data            = request.json or {}
    papers          = data.get("papers", [])
    topics          = data.get("topics", [])
    start_year      = data.get("start_year", 2022)
    end_year        = data.get("end_year", 2026)
    output_type     = data.get("output_type", "abstract")
    topic_summaries = data.get("topic_summaries", {})

    if not papers:
        return jsonify({"error": "No papers"}), 400

    buf = build_pdf(papers, topics, start_year, end_year, output_type, topic_summaries)
    ts  = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    return send_file(buf, mimetype="application/pdf", as_attachment=True,
                     download_name=f"scholar_ai_{ts}.pdf")


@app.route("/api/chat", methods=["POST"])
def api_chat():
    data    = request.json or {}
    history = data.get("history", [])
    if not history:
        return jsonify({"error": "No messages"}), 400

    try:
        r = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "system", "content": MENTOR_PROMPT}] + history,
            max_tokens=1024
        )
        ai_text = r.choices[0].message.content
        papers  = []

        match = re.search(r'\[PAPER_SEARCH:(\{.*?\})\]', ai_text)
        if match:
            try:
                params = json.loads(match.group(1))
                papers = fetch_papers(
                    params.get("topic", ""),
                    params.get("count", 5),
                    params.get("start_year", 2022),
                    params.get("end_year", 2026)
                )
                for p in papers:
                    p["output"] = summarize_one(p["title"], p["abstract"], "short")
            except Exception as e:
                print(f"Search parse error: {e}")
            ai_text = re.sub(r'\[PAPER_SEARCH:\{.*?\}\]', '', ai_text).strip()

        return jsonify({"message": ai_text, "papers": papers})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/ai-check", methods=["POST"])
def api_ai_check():
    data       = request.json or {}
    text       = data.get("text", "").strip()
    check_type = data.get("type", "ai")

    if not text:
        return jsonify({"error": "No text provided"}), 400
    if len(text) < 50:
        return jsonify({"error": "Text too short (minimum 50 characters)"}), 400

    if check_type == "ai":
        try:
            r = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": """You are an expert AI text detector. Analyze text for AI-generation patterns.

AI indicators: uniform sentence lengths, excessive transitional phrases ("furthermore", "in conclusion", "it is worth noting"), lack of personal voice, overly formal tone, generic examples, perfect paragraph structure, hedging language, no emotional depth, repetitive phrasing.

Human indicators: personal voice, colloquialisms, varied structure, specific anecdotes, emotional language, unique metaphors, imperfections.

Respond ONLY with this JSON (no other text):
{"is_ai": true, "confidence": 85, "ai_score": 85, "human_score": 15, "verdict": "one clear sentence", "patterns": ["pattern 1", "pattern 2", "pattern 3"]}"""},
                    {"role": "user", "content": f"Analyze this text:\n\n{text[:3000]}"}
                ],
                max_tokens=300,
                temperature=0.1
            )
            result_text = r.choices[0].message.content.strip()
            m = re.search(r'\{[^{}]+\}', result_text, re.DOTALL)
            if m:
                return jsonify(json.loads(m.group()))
            return jsonify({"error": "Could not parse analysis"}), 500
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    elif check_type == "plagiarism":
        try:
            r = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": 'Extract 3 distinct searchable academic phrases or key claims from this text. Return ONLY a JSON array: ["phrase 1", "phrase 2", "phrase 3"]'},
                    {"role": "user", "content": text[:2000]}
                ],
                max_tokens=200,
                temperature=0.1
            )
            phrases_text = r.choices[0].message.content.strip()
            m = re.search(r'\[.*?\]', phrases_text, re.DOTALL)
            phrases = json.loads(m.group()) if m else [text[:80]]

            matched_papers = []
            for phrase in phrases[:3]:
                found = fetch_papers(phrase, 3, 1990, 2026)
                for p in found:
                    p["matched_phrase"] = phrase
                matched_papers.extend(found)
                time.sleep(1)

            return jsonify({
                "matched_papers": matched_papers[:9],
                "phrases_checked": phrases,
                "match_count": len(matched_papers)
            })
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    return jsonify({"error": "Invalid type"}), 400


if __name__ == "__main__":
    print()
    print("  * Scholar AI Backend - All Systems Online")
    print("  * Open: http://localhost:5000")
    print("  * Press Ctrl+C to stop")
    print()
    app.run(debug=True, port=5000)
