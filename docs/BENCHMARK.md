# OpenClaw memory benchmark

This benchmark compares OpenClaw built-in hybrid search with the Memora
retrieval path implemented by this repository.

## Setup

- Date: 2026-07-26
- Corpus: 57 personal OpenClaw Markdown memory files
- Questions: 30 retrieval questions, evenly split between Korean and English
- End-to-end subset: 10 questions
- Shared embedding model: Ollama `bge-m3`, 1024 dimensions
- Hybrid: OpenClaw built-in vector plus full-text search
- Memora: primary abstractions plus cue indices with BGE-M3/BM25 retrieval
- Privacy: raw memory snippets, questions, and generated answers are not
  published

## Retrieval results

| Method | Complete@1 | Complete@3 | Complete@5 | MRR | Median | P95 |
|---|---:|---:|---:|---:|---:|---:|
| OpenClaw hybrid | 50.0% | 60.0% | 60.0% | 0.536 | 2.420s | 5.750s |
| Memora | 56.7% | 80.0% | 86.7% | 0.647 | 0.956s | 2.207s |

Paired Complete@5 outcomes: Memora won 12, hybrid won 4, and 14 tied.
The exact McNemar result was `p=0.0768`.

### Language split

| Language | Method | Complete@5 | MRR |
|---|---|---:|---:|
| Korean | Hybrid | 73.3% | 0.689 |
| Korean | Memora | 80.0% | 0.539 |
| English | Hybrid | 46.7% | 0.383 |
| English | Memora | 93.3% | 0.756 |

## End-to-end OpenClaw answers

| Method | Answer accuracy | Evidence complete | Grounded accuracy | Median |
|---|---:|---:|---:|---:|
| OpenClaw hybrid | 100.0% | 90.0% | 90.0% | 26.980s |
| Memora | 100.0% | 80.0% | 80.0% | 29.558s |

Paired answer outcomes: Memora won 1, hybrid won 2, and 7 tied
(`p=1.0000`).

## Interpretation

Memora retrieved broader top-five evidence, particularly for English and
paraphrased queries. Built-in hybrid search remained valuable for exact dates,
counts, filenames, and source strings. Memora's direct retrieval was faster in
this run, but its end-to-end agent path was slower and less consistently
grounded.

The practical production design is complementary retrieval: use Memora for
semantic or cross-language recall, then fall back to built-in hybrid search for
exact-string and numeric verification.

## Limitations

This is a private personal-corpus benchmark, not LoCoMo or LongMemEval. It is
small, its exact cases cannot be published without exposing personal memory,
and the headline Complete@5 difference did not reach the conventional
`p < 0.05` threshold. These results support further evaluation; they do not
establish state of the art.
