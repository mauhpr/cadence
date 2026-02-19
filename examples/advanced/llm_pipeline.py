"""
LLM Pipeline Orchestration Example

This example demonstrates how Cadence naturally maps to LLM pipeline patterns:
- RAG (Retrieval-Augmented Generation) with parallel retrieval
- Intent classification and conditional routing
- Model fallback chains with retry/timeout
- Sub-agent orchestration via child cadences
- Observability with TimingHooks and Mermaid diagrams

All services are mocked — zero external dependencies required.
"""

import asyncio
import random
from dataclasses import dataclass, field
from typing import Any

from cadence import (
    Cadence,
    Score,
    TimingHooks,
    fallback,
    note,
    retry,
    timeout,
    to_mermaid,
)


# ---------------------------------------------------------------------------
# Score definitions
# ---------------------------------------------------------------------------


@dataclass
class LLMPipelineScore(Score):
    """Main score for the RAG pipeline."""

    user_query: str

    # Retrieval stage
    vector_results: list[dict[str, Any]] = field(default_factory=list)
    web_results: list[dict[str, Any]] = field(default_factory=list)

    # Classification
    intent: str = ""
    confidence: float = 0.0

    # Generation
    answer: str = ""
    model_used: str = ""
    tokens_used: int = 0

    # Sub-agent outputs
    code_output: str = ""
    citations: list[str] = field(default_factory=list)


@dataclass
class CodeAgentScore(Score):
    """Child score for the code generation sub-agent."""

    query: str
    language: str = "python"
    code: str = ""
    passed_validation: bool = False


@dataclass
class CitationScore(Score):
    """Child score for citation extraction."""

    answer_text: str
    sources: list[dict[str, Any]] = field(default_factory=list)
    citations: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Mock services
# ---------------------------------------------------------------------------


class MockLLM:
    """Simulates an LLM API with configurable latency and failure rate."""

    def __init__(self, name: str, latency: float = 0.05, failure_rate: float = 0.0):
        self.name = name
        self.latency = latency
        self.failure_rate = failure_rate
        self.call_count = 0

    async def generate(self, prompt: str, max_tokens: int = 256) -> dict[str, Any]:
        self.call_count += 1
        await asyncio.sleep(self.latency)

        if random.random() < self.failure_rate:
            raise ConnectionError(f"{self.name} API temporarily unavailable")

        # Deterministic mock responses based on keywords
        if "code" in prompt.lower():
            text = 'def solution():\n    return "Hello from Cadence!"'
        elif "cite" in prompt.lower():
            text = "According to [1] and [2], the answer is clear."
        else:
            text = f"Based on the provided context, here is the answer to: {prompt[:60]}"

        tokens = len(text.split()) * 2
        return {"text": text, "tokens": min(tokens, max_tokens), "model": self.name}


class MockVectorDB:
    """Simulates a vector database search."""

    async def search(self, query: str, top_k: int = 3) -> list[dict[str, Any]]:
        await asyncio.sleep(0.03)
        return [
            {"chunk": f"Relevant passage {i+1} for: {query[:30]}…", "score": 0.95 - i * 0.1}
            for i in range(top_k)
        ]


class MockWebSearch:
    """Simulates a web search API."""

    async def search(self, query: str, num_results: int = 3) -> list[dict[str, Any]]:
        await asyncio.sleep(0.06)
        return [
            {"title": f"Web result {i+1}", "snippet": f"Info about {query[:30]}…", "url": f"https://example.com/{i+1}"}
            for i in range(num_results)
        ]


# Initialize mock services
primary_llm = MockLLM("gpt-4o", latency=0.08, failure_rate=0.3)
fallback_llm = MockLLM("gpt-4o-mini", latency=0.03, failure_rate=0.0)
vector_db = MockVectorDB()
web_search = MockWebSearch()


# ---------------------------------------------------------------------------
# Notes — retrieval stage
# ---------------------------------------------------------------------------


@note
@timeout(5.0)
async def retrieve_from_vectors(score: LLMPipelineScore) -> None:
    """Search the vector database for relevant context."""
    score.vector_results = await vector_db.search(score.user_query)


@note
@fallback(default=[], field="web_results")
@timeout(10.0)
async def retrieve_from_web(score: LLMPipelineScore) -> None:
    """Search the web for supplementary context. Non-critical — falls back to empty list."""
    score.web_results = await web_search.search(score.user_query)


# ---------------------------------------------------------------------------
# Notes — classification stage
# ---------------------------------------------------------------------------


@note
@retry(max_attempts=2, delay=0.05)
@timeout(3.0)
async def classify_intent(score: LLMPipelineScore) -> None:
    """Classify user intent to route the pipeline."""
    query_lower = score.user_query.lower()
    if any(kw in query_lower for kw in ("code", "implement", "function", "write")):
        score.intent = "code_generation"
        score.confidence = 0.92
    elif any(kw in query_lower for kw in ("what", "who", "explain", "how")):
        score.intent = "factual_qa"
        score.confidence = 0.88
    else:
        score.intent = "general"
        score.confidence = 0.75


# ---------------------------------------------------------------------------
# Notes — generation stage (with model fallback)
# ---------------------------------------------------------------------------


@note
@retry(max_attempts=3, backoff="exponential", delay=0.05)
@timeout(30.0)
async def generate_with_primary(score: LLMPipelineScore) -> None:
    """Generate answer with the primary model. Retries up to 3 times."""
    context = "\n".join(r["chunk"] for r in score.vector_results)
    prompt = f"Context:\n{context}\n\nQuestion: {score.user_query}\nAnswer:"
    result = await primary_llm.generate(prompt)
    score.answer = result["text"]
    score.model_used = result["model"]
    score.tokens_used = result["tokens"]


@note
@timeout(15.0)
async def generate_with_fallback(score: LLMPipelineScore) -> None:
    """Fallback generation with a smaller, more reliable model."""
    context = "\n".join(r["chunk"] for r in score.vector_results[:2])
    prompt = f"Context:\n{context}\n\nQuestion: {score.user_query}\nAnswer concisely:"
    result = await fallback_llm.generate(prompt)
    score.answer = result["text"]
    score.model_used = result["model"]
    score.tokens_used = result["tokens"]


# ---------------------------------------------------------------------------
# Notes — code agent sub-cadence
# ---------------------------------------------------------------------------


@note
@fallback(default="", field="code")
@retry(max_attempts=3, delay=0.05)
@timeout(10.0)
async def generate_code(score: CodeAgentScore) -> None:
    """Generate code using the LLM. Falls back to empty string after retries exhausted."""
    result = await primary_llm.generate(f"Write {score.language} code: {score.query}")
    score.code = result["text"]


@note
async def validate_code(score: CodeAgentScore) -> None:
    """Validate generated code (mock syntax check)."""
    await asyncio.sleep(0.01)
    score.passed_validation = "def " in score.code or "class " in score.code


# ---------------------------------------------------------------------------
# Notes — citation agent sub-cadence
# ---------------------------------------------------------------------------


@note
@timeout(5.0)
async def extract_citations(score: CitationScore) -> None:
    """Extract citations from the answer and match to sources."""
    await fallback_llm.generate(f"Cite sources for: {score.answer_text[:80]}")
    score.citations = [
        f"[{i+1}] {src.get('url', src.get('chunk', 'unknown'))}"
        for i, src in enumerate(score.sources[:3])
    ]


# ---------------------------------------------------------------------------
# Pipeline assembly
# ---------------------------------------------------------------------------


def build_pipeline(score: LLMPipelineScore) -> Cadence[LLMPipelineScore]:
    """Assemble the full RAG pipeline."""

    # Code generation sub-agent
    code_child = (
        Cadence("code_agent", CodeAgentScore(query=score.user_query))
        .then("generate", generate_code)
        .then("validate", validate_code)
    )

    def merge_code(parent: LLMPipelineScore, child: CodeAgentScore) -> None:
        parent.code_output = child.code
        parent.answer = f"```python\n{child.code}\n```" if child.passed_validation else child.code

    # Citation extraction sub-agent
    citation_child = (
        Cadence("citation_agent", CitationScore(answer_text=score.user_query, sources=[]))
        .then("extract", extract_citations)
    )

    def merge_citations(parent: LLMPipelineScore, child: CitationScore) -> None:
        parent.citations = child.citations

    def is_code_query(s: LLMPipelineScore) -> bool:
        return s.intent == "code_generation"

    return (
        Cadence("llm_pipeline", score)
        # Stage 1: Parallel retrieval
        .sync("retrieve", [retrieve_from_vectors, retrieve_from_web])
        # Stage 2: Classify intent
        .then("classify", classify_intent)
        # Stage 3: Route — code queries get the code agent, others get standard generation
        .split(
            "route",
            condition=is_code_query,
            if_true=[generate_with_primary],
            if_false=[generate_with_primary],
        )
        # Stage 4: Code agent sub-cadence (refines code queries)
        .child("code_agent", code_child, merge_code)
        # Stage 5: Citation extraction sub-agent
        .child("citations", citation_child, merge_citations)
    )


# ---------------------------------------------------------------------------
# Demo functions
# ---------------------------------------------------------------------------


async def demo_factual_query():
    """Demo 1: Factual RAG query."""
    print("\n" + "=" * 60)
    print("DEMO 1: Factual RAG Query")
    print("=" * 60)

    score = LLMPipelineScore(user_query="What is retrieval-augmented generation?")
    hooks = TimingHooks()

    pipeline = build_pipeline(score).with_hooks(hooks)

    try:
        result = await pipeline.run()
        print(f"\n  Query:   {result.user_query}")
        print(f"  Intent:  {result.intent} (confidence: {result.confidence:.0%})")
        print(f"  Model:   {result.model_used}")
        print(f"  Tokens:  {result.tokens_used}")
        print(f"  Sources: {len(result.vector_results)} vector + {len(result.web_results)} web")
        print(f"  Answer:  {result.answer[:80]}…")
        print(f"\n{hooks.get_report()}")
    except Exception as e:
        print(f"\n  Pipeline failed: {e}")
        print(f"\n{hooks.get_report()}")


async def demo_code_query():
    """Demo 2: Code generation with sub-agent."""
    print("\n" + "=" * 60)
    print("DEMO 2: Code Generation Query")
    print("=" * 60)

    # Force primary to succeed for this demo
    primary_llm.failure_rate = 0.0

    score = LLMPipelineScore(user_query="Write a function to calculate fibonacci numbers")
    hooks = TimingHooks()

    pipeline = build_pipeline(score).with_hooks(hooks)

    try:
        result = await pipeline.run()
        print(f"\n  Query:   {result.user_query}")
        print(f"  Intent:  {result.intent} (confidence: {result.confidence:.0%})")
        print(f"  Model:   {result.model_used}")
        print(f"  Code:    {result.code_output[:60] if result.code_output else '(via main generate)'}")
        print(f"\n{hooks.get_report()}")
    except Exception as e:
        print(f"\n  Pipeline failed: {e}")
        print(f"\n{hooks.get_report()}")

    primary_llm.failure_rate = 0.3  # Restore


async def demo_model_fallback():
    """Demo 3: Primary model failure → fallback model."""
    print("\n" + "=" * 60)
    print("DEMO 3: Model Fallback Chain")
    print("=" * 60)

    # Force primary to always fail to demonstrate fallback
    primary_llm.failure_rate = 1.0

    score = LLMPipelineScore(user_query="Explain how circuit breakers work in microservices")

    # Build a pipeline that uses the fallback model
    fallback_pipeline = (
        Cadence("fallback_demo", score)
        .sync("retrieve", [retrieve_from_vectors, retrieve_from_web])
        .then("classify", classify_intent)
        .then("generate", generate_with_fallback)
    )

    hooks = TimingHooks()
    fallback_pipeline = fallback_pipeline.with_hooks(hooks)

    try:
        result = await fallback_pipeline.run()
        print(f"\n  Query:   {result.user_query}")
        print(f"  Model:   {result.model_used} (fallback)")
        print(f"  Tokens:  {result.tokens_used}")
        print(f"  Answer:  {result.answer[:80]}…")
        print(f"\n{hooks.get_report()}")
    except Exception as e:
        print(f"\n  Pipeline failed: {e}")
        print(f"\n{hooks.get_report()}")

    primary_llm.failure_rate = 0.3  # Restore


async def demo_mermaid_diagram():
    """Show the pipeline structure as a Mermaid diagram."""
    print("\n" + "=" * 60)
    print("Pipeline Diagram (Mermaid)")
    print("=" * 60)

    score = LLMPipelineScore(user_query="example")
    pipeline = build_pipeline(score)
    print(f"\n{to_mermaid(pipeline)}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main():
    print("Cadence LLM Pipeline Orchestration Demo")
    print("=" * 60)
    print("Patterns: RAG, intent routing, model fallback, sub-agents")
    print("All services are mocked — zero external dependencies.\n")

    random.seed(42)  # Reproducible demo output

    await demo_factual_query()
    await demo_code_query()
    await demo_model_fallback()
    await demo_mermaid_diagram()

    print("\n" + "=" * 60)
    print("All LLM pipeline demos completed!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
