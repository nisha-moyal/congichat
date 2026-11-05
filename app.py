"""
Cognichat - A RAG chatbot over your own notes.

Architecture:
  [ user ] --> app (FastAPI, this file) --> chroma (vector DB, separate container)
                     |
                     +--> OpenAI API (embeddings + chat completion)
"""

import os
import sys
import time

import chromadb
from chromadb.utils import embedding_functions
from fastapi import FastAPI, HTTPException
from groq import Groq
from pydantic import BaseModel

app = FastAPI(title="Cognichat", description="RAG over your notes")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()

if not GROQ_API_KEY:
    sys.exit("[Cognichat] GROQ_API_KEY is missing.")

llm = Groq(api_key=GROQ_API_KEY)

embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="all-MiniLM-L6-v2"
)

CHROMA_HOST = os.getenv("CHROMA_HOST", "localhost")
CHROMA_PORT = int(os.getenv("CHROMA_PORT", "8000"))

def connect_to_chroma(retries: int = 30, delay: int = 2):
    """
    Chroma's connection function with retry logic. Chroma's container takes a few seconds to boot. And `depends_on` only waits for the container to START , not to be READY - so we retry here instead of crashing on the first refused connection.
    """

    for attempt in range(1, retries + 1):
        try:
            client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
            client.heartbeat()
            print(f"[Cognichat] Connected to chroma at {CHROMA_HOST}:{CHROMA_PORT}")
            return client
        except Exception as e:
            print(
                f"[Cognichat] Waiting for chroma "
                f"({attempt}/{retries}): {type(e).__name__}",
                flush=True,
            )
            time.sleep(delay)
    sys.exit(f"\n[Cognichat] Could not reach chroma at {CHROMA_HOST}:{CHROMA_PORT}\n")

chroma = connect_to_chroma()
collection = chroma.get_or_create_collection(
    name="notes_minilm",
    embedding_function=embedding_function
)

class QueryReq(BaseModel):
    query: str
    n_results: int = 3

@app.get("/")
def health():
    return {
        "status": "Cognichat is running.",
        "docs_indexed": collection.count(),
        "chroma_host": CHROMA_HOST,
        "chroma_port": CHROMA_PORT,
        "embedding_model": "all-MiniLM-L6-v2",
        "llm_provider": "Groq"
    }

@app.post("/query")
def query(req: QueryReq):
    """
    Query the vector database for relevant notes and return them.
    """

    if collection.count() == 0:
        raise HTTPException(status_code=400, detail="No notes indexed yet. Run docker compose exec app python ingest.py first.")

    # 1. Retrieve - fins the most relevant notes from the vector database
    hits = collection.query(
        query_texts=[req.query],
        n_results=req.n_results,
    )

    documents = hits.get("documents", [[]])[0]
    context = "\n\n---\n\n".join(documents)

    # 2. Augment - send the query and context to OpenAI for a response

    system_prompt = (
        "You are a helpful assistant that answers questions based on the provided context.\n"
        "If the answer is not contained within the context, say 'I don't know.'\n"
        "Context:\n"
        f"{context}\n\n"
        "Question:\n"
        f"{req.query}\n\n"
        "Answer:"
    )

    # 3. Generate - let the LLM write the final answer
    resp = llm.chat.completions.create(
                model="openai/gpt-oss-120b",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": req.query},
                ],
            )

    answer = resp.choices[0].message.content

    return {
    "question": req.query,
    "answer": answer,
    "sources_used": len(documents),
    }