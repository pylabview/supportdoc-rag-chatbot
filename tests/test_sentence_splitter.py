from __future__ import annotations

from supportdoc_rag_chatbot.app.services import ClaimKind, split_answer_claims


def test_split_answer_claims_handles_sentences_and_bullets() -> None:
    answer = (
        "Pods run one or more containers [1]. Services expose Pods over the network [2].\n"
        "- ConfigMaps store non-confidential configuration data [3]\n"
        "1. Secrets store sensitive data [4]"
    )

    claims = split_answer_claims(answer)

    assert [claim.kind for claim in claims] == [
        ClaimKind.SENTENCE,
        ClaimKind.SENTENCE,
        ClaimKind.BULLET,
        ClaimKind.BULLET,
    ]
    assert [claim.text for claim in claims] == [
        "Pods run one or more containers [1].",
        "Services expose Pods over the network [2].",
        "- ConfigMaps store non-confidential configuration data [3]",
        "1. Secrets store sensitive data [4]",
    ]


def test_split_answer_claims_keeps_common_abbreviations_inside_sentence() -> None:
    answer = "Use e.g. a Pod template [1]. Services expose Pods over the network [2]."

    claims = split_answer_claims(answer)

    assert [claim.text for claim in claims] == [
        "Use e.g. a Pod template [1].",
        "Services expose Pods over the network [2].",
    ]
