import asyncio
import glob
import json
import os
import re
import sys

from dotenv import load_dotenv
from graphrag_sdk import (Attribute, ConnectionConfig, Embedder, Entity, FalkorDBConnection, GraphExtraction, GraphRAG,
                          GraphStore, LLMExtractor, LLMInterface, Ontology, Relation, VectorStore)
from graphrag_sdk.core.models import LLMResponse
from graphrag_sdk.retrieval.strategies.local import LocalRetrieval
from openai import OpenAI

import graph

ROOT = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(ROOT, ".env"))

DOCS_GRAPH = "paynova_docs"
ANSWERS_GRAPH = "paynova_answers"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
LLM_MODEL = os.getenv("GRAPHRAG_LLM", "gemini-flash-lite-latest")
EMBED_MODEL = os.getenv("GRAPHRAG_EMBEDDER", "gemini-embedding-001")
DIMENSIONS = int(os.getenv("GRAPHRAG_DIMENSIONS", "768"))

ONTOLOGY = Ontology(
    entities=[
        Entity(label="Policy", description="A PayNova compliance policy document",
               properties=[Attribute(name="version")]),
        Entity(label="Obligation", description="A rule a policy sets, such as a deadline, a retention period or a required check",
               properties=[Attribute(name="deadline", description="Time limit, e.g. 45 days or 6 hours")]),
        Entity(label="Process", description="An operational process or control that carries out an obligation"),
        Entity(label="Team", description="A team or role at PayNova responsible for a process or policy"),
        Entity(label="System", description="A software system or data store, such as the user database"),
        Entity(label="Regulator", description="An external law, rule set or authority, such as RBI, DPDP, PML Rules or CERT-In"),
    ],
    relations=[
        Relation(label="SETS", description="The policy sets this obligation", patterns=[("Policy", "Obligation")]),
        Relation(label="CARRIED_OUT_BY", description="The obligation is carried out by this process",
                 patterns=[("Obligation", "Process")]),
        Relation(label="RESPONSIBLE_FOR", description="The team is responsible for this",
                 patterns=[("Team", "Process"), ("Team", "Policy"), ("Team", "Obligation")]),
        Relation(label="RUNS_ON", description="The process runs on this system", patterns=[("Process", "System")]),
        Relation(label="REQUIRED_BY", description="The obligation exists because of this regulator or law",
                 patterns=[("Obligation", "Regulator")]),
    ],
)


def gemini():
    return OpenAI(api_key=os.getenv("GEMINI_API_KEY"), base_url=GEMINI_URL, max_retries=2)


class GeminiLLM(LLMInterface):
    def __init__(self, model):
        super().__init__(model_name=model)
        self.client = gemini()

    def invoke(self, prompt, **kwargs):
        options = {k: v for k, v in kwargs.items() if k in ("temperature", "max_tokens", "response_format")}
        response = self.client.chat.completions.create(
            model=self.model_name, messages=[{"role": "user", "content": prompt}], **options)
        return LLMResponse(content=response.choices[0].message.content or "")


class GeminiEmbedder(Embedder):
    def __init__(self, model, dimensions):
        self.model = model
        self.dimensions = dimensions
        self.client = gemini()

    @property
    def model_name(self):
        return self.model

    def embed_query(self, text, **kwargs):
        return self.embed_documents([text])[0]

    def embed_documents(self, texts, **kwargs):
        response = self.client.embeddings.create(model=self.model, input=texts, dimensions=self.dimensions)
        return [item.embedding for item in response.data]


def ready():
    return bool(os.getenv("GEMINI_API_KEY"))


def rag(llm=None, local=False):
    connection = FalkorDBConnection(ConnectionConfig(
        host=os.getenv("FALKORDB_HOST") or "localhost",
        port=int(os.getenv("FALKORDB_PORT") or "6379"),
        username=os.getenv("FALKORDB_USERNAME") or None,
        password=os.getenv("FALKORDB_PASSWORD") or None,
        graph_name=DOCS_GRAPH,
    ))
    embedder = GeminiEmbedder(EMBED_MODEL, DIMENSIONS)
    strategy = None
    if local:
        vectors = VectorStore(connection, embedder=embedder, embedding_dimension=DIMENSIONS)
        strategy = LocalRetrieval(GraphStore(connection), vectors, embedder, top_k=5)
    return GraphRAG(
        connection=connection,
        llm=llm or GeminiLLM(LLM_MODEL),
        embedder=embedder,
        ontology=ONTOLOGY,
        retrieval_strategy=strategy,
        embedding_dimension=DIMENSIONS,
    )


async def build():
    llm = GeminiLLM(LLM_MODEL)
    extractor = GraphExtraction(llm=llm, entity_extractor=LLMExtractor(llm),
                                entity_types=[e.label for e in ONTOLOGY.entities])
    async with rag(llm) as r:
        for path in sorted(glob.glob(os.path.join(ROOT, "data", "policies", "*.md"))):
            with open(path) as f:
                result = await r.ingest(text=f.read(), document_id=os.path.basename(path), extractor=extractor)
            print(f"{os.path.basename(path)}: {result.nodes_created} nodes, {result.relationships_created} relationships")
        await r.finalize()


async def answer(question):
    async with rag(local=True) as r:
        result = await r.completion(question, return_context=True)
    items = result.retriever_result.items if result.retriever_result else []
    return {
        "answer": result.answer,
        "sources": [{"text": item.content[:400], "score": item.score} for item in items[:6]],
        "model": LLM_MODEL,
    }


def cache_key(question):
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", question.lower()).split())


def ask(question):
    answers = graph.client().select_graph(ANSWERS_GRAPH)
    key = cache_key(question)
    hit = answers.query("MATCH (a:Answer {key: $k}) RETURN a.payload", {"k": key}).result_set
    if hit:
        return {**json.loads(hit[0][0]), "cached": True}
    result = asyncio.run(answer(question))
    answers.query("MERGE (a:Answer {key: $k}) SET a.question = $q, a.payload = $p, a.at = timestamp()",
                  {"k": key, "q": question, "p": json.dumps(result)})
    return {**result, "cached": False}


if __name__ == "__main__":
    if sys.argv[1:2] == ["build"]:
        asyncio.run(build())
    else:
        print(ask(" ".join(sys.argv[1:]) or "What is our deadline for erasure requests?"))
