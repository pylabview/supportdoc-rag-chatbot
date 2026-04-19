# Task 5 cloud runtime smoke

Date UTC: 2026-04-19T14:26:12Z

## Backend base URL used for operator smoke

```text
https://supportdocragchatbotmvpalb-1097825852.us-west-2.elb.amazonaws.com
```

Note: operator smoke used `curl -k` against the raw ALB DNS. The Amplify browser build must use a real HTTPS backend origin with a valid certificate.

## Supported query smoke

Request:

```json
{
  "question": "What is a Pod?"
}
```

Response summary:

```text
refusal: {'is_refusal': False, 'reason_code': None, 'message': None}
citation_count: 1
answer_preview: A Pod is the smallest and simplest Kubernetes object [1]. It represents a set of running containers on your cluster [1].
```

Pass condition:

```text
HTTP 200
refusal.is_refusal=false
citations length >= 1
```

## Failure-path query smoke

Request:

```json
{
  "question": "What is the refund policy for a fictional product named BananaCloud Quantum Edition?"
}
```

Response summary:

```text
refusal: {'is_refusal': True, 'reason_code': 'insufficient_evidence', 'message': 'I can’t answer that confidently from the approved support corpus.'}
citation_count: 0
answer_preview: I can’t answer that confidently from the approved support corpus.
```

Pass condition:

```text
HTTP 200
refusal.is_refusal=true
citations length = 0
```
