from __future__ import annotations
import os
from typing import Generator
from openai import OpenAI

SYSTEM_PROMPT = """You are DocuMind, an enterprise document assistant.
Your job is to answer questions using ONLY the context passages provided.

Rules:
1. Base your answer strictly on the provided context. Do not use prior knowledge.
2. Cite your sources: after each claim, add (Source: <doc_name>, p.<page_num>).
3. If the context does not contain enough information, say:
   "I couldn't find a clear answer in the uploaded documents."
4. Be concise and factual. No filler phrases.
5. If multiple passages are relevant, synthesize them into one coherent answer."""

USER_TEMPLATE = """Context passages:
{context_block}

Question: {question}

Answer (with citations):"""


def _build_context_block(retrieved_chunks: list[dict]) -> str:
    lines = []
    for i, chunk in enumerate(retrieved_chunks, start=1):
        lines.append(
            f"[{i}] (doc: {chunk['doc_name']}, page {chunk['page_num']})\n{chunk['text']}"
        )
    return "\n\n".join(lines)


LLM_MODEL = os.getenv("LLM_MODEL", "llama3.2")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://localhost:11434/v1")


def generate_answer(
    question: str,
    retrieved_chunks: list[dict],
    stream: bool = True,
    model: str = LLM_MODEL,
) -> str | Generator[str, None, None]:
    client = OpenAI(base_url=LLM_BASE_URL, api_key="ollama")

    if not retrieved_chunks:
        msg = "I could not find relevant passages."
        if stream:
            def _empty():
                yield msg
            return _empty()
        return msg

    context_block = _build_context_block(retrieved_chunks)
    user_message = USER_TEMPLATE.format(  # building user prompt
        context_block=context_block,
        question=question,
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]

    if stream:
        return _stream_response(client, messages, model)
    else:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.1,
        )
        return response.choices[0].message.content


def _stream_response(
    client: OpenAI,
    messages: list[dict],
    model: str,
) -> Generator[str, None, None]:
    stream = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.1,
        stream=True,
    )
    for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta