# dfDewey
dfDewey is a digital forensics string extraction, indexing, and searching tool.

[Usage](docs/usage.md)

## Requirements
dfDewey currently requires bulk_extractor for string extraction.
bulk_extractor can be downloaded and built from source here:
https://github.com/simsong/bulk_extractor

bulk_extractor can also be installed from the GIFT PPA.

```shell
sudo add-apt-repository ppa:gift/stable
sudo apt update
sudo apt install -y bulk-extractor
```

Elasticsearch and PostgreSQL are also required to store extracted data.
These can be installed separately or started in Docker using `docker-compose`.

```shell
cd dfdewey/docker
sudo docker-compose up -d
```

Note: To stop the containers (and purge the stored data) run
`sudo docker-compose down` from the `dfdewey/docker` directory.

All other requirements can be installed using pip:
`pip install -r requirements.txt`
