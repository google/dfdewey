# dfDewey
dfDewey is a digital forensics string extraction, indexing, and searching tool.

[Usage](docs/usage.md)

## Requirements
dfDewey currently requires bulk_extractor for string extraction.
bulk_extractor can be downloaded here: https://github.com/simsong/bulk_extractor

Elasticsearch and PostgreSQL are also required to store extracted data.
These can be installed separately or started in Docker.

All other requirements can be installed using pip:
`pip install -r requirements.txt`
