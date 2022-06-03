# Using dfDewey

```shell
usage: dfdewey [-h] [-c CONFIG] [--no_base64] [--no_gzip] [--no_zip] [--reparse] [--reindex] [--delete] [--highlight] [-s SEARCH] [--search_list SEARCH_LIST] case [image]

positional arguments:
  case                  case ID
  image                 image file (default: 'all')

optional arguments:
  -h, --help            show this help message and exit
  -c CONFIG, --config CONFIG
                        datastore config file
  --no_base64           don't decode base64
  --no_gzip             don't decompress gzip
  --no_zip              don't decompress zip
  --reparse             reparse filesystem (will delete existing filesystem mapping)
  --reindex             recreate index (will delete existing index)
  --delete              delete image (filesystem mapping and index)
  --highlight           highlight search term in results
  -s SEARCH, --search SEARCH
                        search query
  --search_list SEARCH_LIST
                        file with search queries
```

## Docker

If using OpenSearch and PostgreSQL in Docker, they can be started using
[docker-compose](https://docs.docker.com/compose/install/) from the `docker`
folder.

```shell
docker-compose up -d
```

Note: Java memory for OpenSearch is set high to improve performance when
indexing large volumes of data. If running on a system with limited resources,
you can change the setting in `docker/docker-compose.yml`.

To shut the containers down again (and purge the data), run:

```shell
docker-compose down
```

### Running dfDewey in Docker

The `docker` folder also contains a `Dockerfile` to build dfDewey and its
dependencies into a Docker image.

To build the image (must be run from the root of the repo):

```shell
docker build -t <docker_name> -f ./docker/Dockerfile .
```

When running dfDewey within a Docker container, we need to give the container
access to the host network so it will be able to access OpenSearch and
PostgreSQL in their respective containers. We also need to map a folder in the
container to allow access to the image we want to process. For example:

```shell
docker run --network=host -v ~/images/:/mnt/images <docker_name> dfdewey -h
```

## Processing an Image

To process an image in dfDewey, you need to supply a `CASE` and `IMAGE`.

```shell
dfdewey testcase /path/to/image.dd
```

dfDewey will have bulk_extractor decode base64 data, and decompress gzip / zip
data by default. These can be disabled by adding the flags `--no_base64`,
`--no_gzip`, and `--no_zip`.

If an image has already been processed, you can opt to reparse and reindex the
image (this will first delete the existing data) by adding the flags
`--reparse` and `--reindex`.

You can also delete the data for a given image from the datastores by adding
the `--delete` flag.

## Searching

To search the index for a single image, you need to supply a `CASE`, `IMAGE`,
and `SEARCH`.

```shell
dfdewey testcase /path/to/image.dd -s 'foo'
```

If an `IMAGE` is not provided, dfDewey will search all images in the given case.

dfDewey can also search for a list of terms at once. The terms can be placed in
a text file one per line. In this case, only the number of results for each term
is returned.

```shell
dfdewey testcase /path/to/image.dd --search_list search_terms.txt
```
