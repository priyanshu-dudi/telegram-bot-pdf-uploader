# 📘 Telegram GPT-5 PDF Q&A Bot

This Telegram bot:
- Accepts **chapter PDFs**
- Splits into **sections**
- Creates **short bullet Q&A**
- Adds **comprehension-based** and **extra revision Q&A**

---

## 🚀 Deploy Free (Railway)

1. **Fork this repo** or upload your code.
2. Create a project at [Railway.app](https://railway.app).
3. Link your GitHub repo → Deploy.
4. Add environment variables in Railway → Variables tab:
   - `OPENAI_API_KEY`
   - `TELEGRAM_BOT_TOKEN`
   - (optional) `OPENAI_MODEL`, `MAX_QA_PER_SECTION`
5. Deploy → Bot is live 24/7.

---

## 💻 Local Run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # edit with your keys
python main.py
