from __future__ import annotations
import json, math, os, sys, types, asyncio
from pathlib import Path
from datetime import datetime

_PROJECT_ROOT = Path(__file__).resolve().parents[2]   # phase3_hard -> phases -> RAG
REPORT_DIR = Path(os.getenv("RAGAS_REPORT_DIR", str(_PROJECT_ROOT / "data" / "reports")))


def _shim_missing_vertexai() -> None:
    # ragas.llms.base unconditionally imports ChatVertexAI from this submodule,
    # which newer langchain-community releases dropped in favor of the standalone
    # langchain-google-vertexai package. We never use VertexAI, so a stub satisfies
    # the import without pulling in that dependency.
    mod_name = "langchain_community.chat_models.vertexai"
    if mod_name in sys.modules:
        return
    try:
        import langchain_community.chat_models  # noqa: F401  (ensure parent package exists)
    except ImportError:
        return
    shim = types.ModuleType(mod_name)

    class ChatVertexAI:
        pass

    shim.ChatVertexAI = ChatVertexAI
    sys.modules[mod_name] = shim


def run_ragas_evaluation(test_set: list[dict], report_name: str | None = None) -> dict:
    if not test_set:
        return {"error": "Empty test set", "scores": {}}

    try:
        _shim_missing_vertexai()
        from ragas import evaluate
        from ragas.metrics import faithfulness, answer_relevancy, context_precision, context_recall
        from ragas.llms import LangchainLLMWrapper
        from ragas.embeddings import LangchainEmbeddingsWrapper
        from langchain_openai import ChatOpenAI, OpenAIEmbeddings
        from datasets import Dataset, Sequence, Value, Features
        import ragas.validation as rv

        # Newer ragas versions dropped validate_column_dtypes; only patch it if present.
        original_validate = getattr(rv, "validate_column_dtypes", None)
        if original_validate is not None:
            rv.validate_column_dtypes = lambda ds: None

        llm = LangchainLLMWrapper(ChatOpenAI(
            model="gpt-4o-mini",
            openai_api_key=os.getenv("OPENAI_API_KEY"),
        ))

        emb = LangchainEmbeddingsWrapper(OpenAIEmbeddings(
            model="text-embedding-3-small",
            openai_api_key=os.getenv("OPENAI_API_KEY"),
        ))

        for metric in [faithfulness, answer_relevancy, context_precision, context_recall]:
            metric.llm = llm
            if hasattr(metric, "embeddings"):
                metric.embeddings = emb

        features = Features({
            "question": Value("string"),
            "answer": Value("string"),
            "contexts": Sequence(Value("string")),
            "ground_truth": Value("string"),
        })

        dataset = Dataset.from_dict({
                "question": [i["question"] for i in test_set],
                "answer": [i["answer"] for i in test_set],
                "contexts": [
                    list(i["contexts"]) if isinstance(i["contexts"], (list, tuple))
                    else [str(i["contexts"])]
                    for i in test_set
                ],
                "ground_truth": [i["ground_truth"] for i in test_set],
        }, features= features)

        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                raise RuntimeError
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        scores = evaluate(
            dataset,
            metrics=[faithfulness, answer_relevancy, context_precision, context_recall],
        ).to_pandas()

        if original_validate is not None:
            rv.validate_column_dtypes = original_validate

        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        name = report_name or f"ragas_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        csv_path = REPORT_DIR / f"{name}.csv"
        scores.to_csv(csv_path, index=False)

        summary = {
            "faithfulness": round(float(scores["faithfulness"].mean()), 3),
            "answer_relevancy": round(float(scores["answer_relevancy"].mean()), 3),
            "context_precision": round(float(scores["context_precision"].mean()), 3),
            "context_recall": round(float(scores["context_recall"].mean()), 3),
            "n_questions": len(test_set),
            "report_path": str(csv_path),
        }
        if all(math.isnan(summary[k]) for k in
               ("faithfulness", "answer_relevancy", "context_precision", "context_recall")):
            return {
                "error": "RAGAS scoring returned no results for any question - check your "
                         "OpenAI API key's quota/billing (this is usually a rate-limit or "
                         "insufficient_quota error from OpenAI, not a bug in the app).",
                "scores": {},
            }
        (REPORT_DIR / f"{name}_summary.json").write_text(json.dumps(summary, indent=2))
        return {"scores": summary, "report_path": str(csv_path)}

    except Exception as e:
        import traceback
        return {"error": f"{e}\n{traceback.format_exc()}", "scores": {}}


def build_test_set_from_pipeline(questions_and_truths: list[dict], top_k: int = 5) -> list[dict]:
    from core.pipeline import query_document
    test_set = []
    for item in questions_and_truths:
        try:
            result = query_document(question=item["question"], top_k=top_k, stream=False)
            test_set.append({
                "question": item["question"],
                "ground_truth": item["ground_truth"],
                "answer": result.answer,
                "contexts": [c["text"] for c in result.sources],
            })
        except Exception as e:
            print(f"Skipped '{item['question']}': {e}")
    return test_set

def load_test_set_from_json(path: str) -> list[dict]:
    with open(path) as f:
        return json.load(f)


def generate_test_set_from_pdf(pdf_path: str, n_questions: int = 5) -> list[dict]:
    from core.ingestion import extract_text_from_pdf
    from openai import OpenAI

    pages = extract_text_from_pdf(pdf_path)
    full_text = "\n\n".join(text for _, text in pages)[:8000]
    if not full_text.strip():
        raise ValueError("No extractable text found in this PDF.")

    # The local Ollama model doesn't reliably produce well-formed JSON for this;
    # gpt-4o-mini's JSON mode is much more reliable, and RAGAS scoring already
    # requires OpenAI anyway, so this doesn't add a new dependency.
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You generate RAG evaluation test sets. Output valid JSON only."},
            {"role": "user", "content": (
                f"Based on the document content below, write {n_questions} question-and-answer "
                "pairs that test factual understanding of the document. Respond with a JSON object "
                'of the form {"pairs": [{"question": "...", "ground_truth": "..."}, ...]}.\n\n'
                f"Document content:\n{full_text}"
            )},
        ],
        response_format={"type": "json_object"},
        temperature=0.3,
    )
    data = json.loads(response.choices[0].message.content)
    return data["pairs"]