<h1 align="center">⬡ Scholar AI</h1>
<p align="center"><b>An intelligent research agent that searches millions of academic papers, synthesizes AI summaries, verifies originality, and exports professional reports guided by voice.</b></p>

<p align="center">
  <img alt="Python" src="https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white">
  <img alt="Flask" src="https://img.shields.io/badge/Flask-backend-000000?logo=flask&logoColor=white">
  <img alt="LLaMA 3.3" src="https://img.shields.io/badge/LLaMA_3.3_70B-Groq-F0B429">
  <img alt="OpenAlex" src="https://img.shields.io/badge/OpenAlex-250M+_papers-38BDF8">
  <img alt="License" src="https://img.shields.io/badge/License-MIT-34D399">
</p>

---

## ✨ Features

- **🔍 Multi-topic search** research many topics at once, filtered by year range and paper count.
- **🧬 Combined + individual summaries** a synthesized AI overview per topic, plus each paper's own abstract and AI summary, with direct source links.
- **🛡️ AI & plagiarism check** detect AI-generated writing with a confidence score and scan passages against published literature.
- **🎙️ Advanced voice assistant** speak your searches, dictate to the chatbot, run voice commands ("search papers on…", "export PDF"), and hear summaries read aloud.
- **🤖 Research Mentor chatbot** a research specialist for methodology, literature reviews, writing, citations, and live paper search.
- **📄 Professional PDF export** formatted reports with overviews, authors, venues, and clickable links.
- **📑 Instant citations** one-click APA, MLA, IEEE & BibTeX, copied to clipboard.
- **⭐ Library & history** save papers and revisit past searches (stored locally in the browser).
- **⚡ Reliable by design** primary search via **OpenAlex** (no API key, 250M+ works) with **Semantic Scholar** fallback, plus graceful offline mode.

## 🧰 Tech Stack

| Layer | Technology |
|------|------------|
| Frontend | Single-file HTML/CSS/JS (no build step), Web Speech API for voice |
| Backend | Python + Flask + Flask-CORS |
| AI | LLaMA 3.3 70B via Groq |
| Papers | OpenAlex API (primary) · Semantic Scholar (fallback) |
| Export | ReportLab (PDF) |

## 🚀 Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set your free Groq API key  (https://console.groq.com/keys)
#    Windows:
setx GROQ_API_KEY "your_key_here"      # then reopen the terminal
#    macOS / Linux:
export GROQ_API_KEY="your_key_here"

# 3. Run
python server.py
```

Then open **http://localhost:5000** and choose **"Continue as Demo User."**

> Paper search, PDF export, citations, library, history, and voice work without a key.
> The Groq key enables AI summaries, combined overviews, the chatbot, and AI/plagiarism detection.

## 🗺️ How It Works

1. **Enter topics** (type or speak) → 2. **Set filters** (years, count, output format) → 3. **AI analysis** (LLaMA summarizes & synthesizes each topic) → 4. **Export & verify** (PDF, citations, or AI/plagiarism check).

## 📁 Project Structure

```
├── index.html      # Full single-page app (landing, auth, dashboard, chat, voice)
├── server.py       # Flask API: search, summarize, export, chat, AI/plagiarism check
├── requirements.txt
└── README.md
```

## ⚠️ Notes

- AI detection is probabilistic guidance, not proof — no detector is 100% accurate.
- The plagiarism scan is a similarity indicator across published abstracts, not a definitive originality report.

## 📜 License

MIT © Hamza Maqsood
