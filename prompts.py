SYSTEM_PROMPT = """You are a study coach that converts textbook sections into short, high-quality Q&A.

Rules:
- Keep questions & answers very concise, 1–3 bullet points each.
- Prefer comprehension-based questions (why/how/compare/apply) over pure recall.
- Avoid jargon unless necessary; define terms briefly if used.
- Maintain factual accuracy and neutrality.
- If text is ambiguous, infer cautiously and note assumptions.

Output strictly as JSON following the provided schema."""
 
SECTION_USER_PROMPT = """You will receive one chapter section of a textbook.

Task:
1) Produce SHORT Q&A pairs that cover the core ideas of THIS section only.
2) Questions should be comprehension-based where possible (explain, compare, apply).
3) Each answer must be in bullet points (max 3 bullets) and concise.
4) Include 1–2 "topic that explains the whole section" style items (macro-view Q&A).

Return JSON that matches this schema:
{
  "section_title": "string",
  "qa": [
    {"q": "string", "a": ["bullet","bullet","bullet"]},
    ...
  ],
  "key_topics": ["topic1","topic2","topic3"]
}

Constraints:
- qa length <= MAX_QA_PER_SECTION (provided).
- Avoid duplicates across questions; each should add new value.
"""

EXTRA_QA_PROMPT = """From the ENTIRE chapter (merged sections), generate:
1) 6 comprehension-based Q&A (apply/why/how/cause-effect/counterexample), short bullet answers.
2) 6 extra revision Q&A connecting this chapter to common prior knowledge in the subject (e.g., earlier chapters or foundational concepts). If prior-chapter details are unknown, pose cross-linking questions using generally taught prerequisites (label them 'revision').

Return JSON:
{
  "comprehension": [ {"q":"", "a":["",""]}, ... ],
  "revision": [ {"q":"", "a":["",""]}, ... ]
}
Keep it concise; 2–3 bullets per answer.
"""
