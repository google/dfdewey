# dfDewey
dfDewey is a digital forensics string extraction, indexing, and searching tool.

<img src="https://user-images.githubusercontent.com/52063018/101560727-fc827900-3a17-11eb-93a1-f2a0589b6b6b.png" width="240" />

[Usage](docs/usage.md)

## Requirements
### bulk_extractor
dfDewey currently requires bulk_extractor for string extraction.

bulk_extractor can be installed from the GIFT PPA.

```shell
sudo add-apt-repository ppa:gift/stable
sudo apt update
sudo apt install -y bulk-extractor
```

bulk_extractor can also be downloaded and built from source here:
https://github.com/simsong/bulk_extractor

Note: bulk_extractor v2.0.3 or greater is required.

### dfVFS
[dfVFS](https://github.com/log2timeline/dfvfs) is required for image parsing. It
can be installed from the GIFT PPA.

```shell
sudo add-apt-repository ppa:gift/stable
sudo apt update
sudo apt install -y python3-dfvfs
```

It can also be installed using pip:

```shell
pip install -r dfvfs_requirements.txt
```

### Datastores
OpenSearch and PostgreSQL are also required to store extracted data.
These can be installed separately or started in Docker using `docker-compose`.

```shell
cd docker
sudo docker-compose up -d
```

Note: To stop the containers (and purge the stored data) run
`sudo docker-compose down` from the `docker` directory.

dfDewey will try to connect to datastores on localhost by default. If running
datastores on separate servers, copy the config file template
`dfdewey/config/config_template.py` to `~/.dfdeweyrc` and adjust the server
connection settings in the file. You can also specify a different config file
location on the command line using `-c`.

## Installation

```shell
python setup.py install
```

Note: It's recommended to install dfDewey within a virtual environment.
