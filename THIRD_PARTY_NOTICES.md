# Third-party notices

| Component | Licence | Use |
|---|---|---|
| Synthetic Data Designer, vendored in `src/sdd` from Algoritmica-ai/deeploans (`synthetic-data-designer/`; `src/sdd/LICENSE`, `src/sdd/NOTICE`) | Apache-2.0 | Case generation from `specs/*.yaml`; the designer UI at `/sdd/` |
| pydantic | MIT | Contract validation |
| PyYAML | MIT | Spec and obligation files |
| Jinja2 | BSD-3-Clause | Document rendering |
| pandas | BSD-3-Clause | Tabular handling |
| pyarrow | Apache-2.0 | Parquet I/O |
| openai (Python client) | Apache-2.0 | OpenAI-compatible calls to NVIDIA Build and NIMs |
| python-dotenv | BSD-3-Clause | `.env` loading |
| pytest | MIT | Tests (dev only) |
| ruff | MIT | Lint (dev only) |

NVIDIA Nemotron models are accessed as hosted endpoints and are not
redistributed. Their licence terms are NVIDIA's.
