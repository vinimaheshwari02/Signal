# ADR 0006: Rule-based enrichment (no LLM or RAG in v1)

Status: Accepted

## Context

Each feedback item must be labelled with language, sentiment, kind (problem, praise, question, suggestion, other), area and topic, in several languages, at burst speeds, and with results a product manager can explain and trust. Cost must be predictable and no personal data should leave the platform to a third party. Accuracy has to be measurable against a labelled sample.

## Decision

Enrichment in v1 is rule-based and uses open-source libraries only. There is no LLM and no retrieval-augmented generation.

- An `Enricher` interface with one implementation per label: language, sentiment, classifier.
- A taxonomy kept in a config file in the repository: areas, topics and trigger words per language. All tenants share it for now.
- Kind is decided by ordered rules: known problem pattern, then suggestion, then question, then positive sentiment, otherwise other.
- Feedback that matches no topic goes to the area's "other" topic, and its frequent keywords are reported so new topics can be added.
- Each enricher sits behind a feature flag and records its rule version in `extras`.
- Accuracy is reported against a labelled sample and tracked as a metric.
- One enricher failing does not fail the item: the rest is saved, the failure is marked and retried.

## Alternatives considered

- **Hosted LLM API.** Higher accuracy on messy text, but recurring cost, variable latency under burst load, rate limits, and personal data leaving the platform. Rejected for v1.
- **Self-hosted model or embeddings with RAG.** Operationally heavy for a first version and hard to explain. Rejected for v1.
- **Keyword clustering.** Produces unstable themes that change between runs. Rejected.

## Consequences

- Zero marginal cost, predictable throughput, deterministic and explainable labels, stable theme keys.
- Lower accuracy than a language model, and only listed topics are recognised; the taxonomy needs curation, and each new language needs word lists.
- The `Enricher` interface makes a model-based enricher a drop-in replacement behind a flag.
- Revisit if measured accuracy is too low or the unclassified share keeps growing.
