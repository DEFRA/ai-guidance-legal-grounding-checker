import math


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0.0 or mag_b == 0.0:
        return 0.0
    return dot / (mag_a * mag_b)


def find_candidates(
    guidance_embedding: list[float],
    law_embeddings: list[tuple[str, list[float]]],
    top_k: int = 15,
    threshold: float = 0.65,
    score_gap: float | None = 0.04,
) -> list[tuple[str, float]]:
    """
    Return the law proposition ids that survive retrieval for one guidance
    proposition, sorted by descending similarity score.

    Retrieval is threshold-led with an adaptive size: keep candidates within
    ``score_gap`` of the top score (so a strong single anchor doesn't drag in a
    long tail of weaker neighbours), capped at ``top_k`` as a safety net.

    Args:
        guidance_embedding: Embedding of the guidance proposition text.
        law_embeddings: List of (law_proposition_id, embedding) pairs.
        top_k: Hard cap on the number of survivors returned.
        threshold: Minimum cosine similarity to be considered a candidate.
        score_gap: When set, drop candidates more than this far below the top
            score. Pass ``None`` for a plain threshold + top_k retrieval.

    Returns:
        List of (law_proposition_id, score) sorted by descending score.
    """
    scored = [
        (law_id, cosine_similarity(guidance_embedding, law_emb))
        for law_id, law_emb in law_embeddings
    ]
    filtered = [(law_id, score) for law_id, score in scored if score >= threshold]
    if not filtered:
        return []
    filtered.sort(key=lambda x: x[1], reverse=True)
    if score_gap is not None:
        cutoff = max(threshold, filtered[0][1] - score_gap)
        filtered = [(law_id, score) for law_id, score in filtered if score >= cutoff]
    return filtered[:top_k]
