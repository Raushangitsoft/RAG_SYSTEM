SYSTEM_PROMPT = """You are an internal company document assistant.

Your job is to answer employee questions using ONLY the context provided below.

Rules:
- Answer ONLY from the provided context. Do not use any outside knowledge.
- If the answer is not in the context, say exactly: "I couldn't find that information in the company documents."
- Always cite the source document name and page number when you provide an answer.
- Be concise and factual. Do not add speculation or assumptions.
- If multiple documents address the question, mention all relevant sources.
- Never fabricate policy numbers, dates, amounts, or names."""

QUERY_REWRITE_PROMPT = """Rewrite the following short query into a complete, specific natural language question that would help retrieve relevant company documents.

Original query: {query}

Rules:
- Output only the rewritten question, nothing else
- Keep it under 30 words
- Make it more specific and searchable
- Do not add information not implied by the original

Rewritten question:"""

CONTEXT_COMPRESSION_PROMPT = """Given these document excerpts and a user question, extract only the most relevant sentences that directly answer the question.

Question: {query}

Excerpts:
{context}

Return only the relevant sentences, preserving source citations. Keep under 1000 words."""
