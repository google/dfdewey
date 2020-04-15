# Using dfDewey

```shell
usage: dfdewey.py [-h] -c CASE [-i IMAGE] [--no_base64] [--no_gzip] [--no_zip]
                  [-s SEARCH] [--search_list SEARCH_LIST]

optional arguments:
  -h, --help            show this help message and exit
  -c CASE, --case CASE  case ID
  -i IMAGE, --image IMAGE
                        image file
  --no_base64           don't decode base64
  --no_gzip             don't decompress gzip
  --no_zip              don't decompress zip
  -s SEARCH, --search SEARCH
                        search query
  --search_list SEARCH_LIST
                        file with search queries
```

## Processing an Image

To process an image in dfDewey, you need to supply a `CASE` and `IMAGE`.

```shell
python3 dfdewey.py -c testcase -i /path/to/image.dd
```

dfDewey will have bulk_extractor decode base64 data, and decompress gzip / zip
data by default. These can be disabled by adding the flags `--no_base64`,
`--no_gzip`, and `--no_zip`.

## Searching

To search the index for a single image, you need to supply a `CASE`, `IMAGE`,
and `SEARCH`.

```shell
python3 dfdewey.py -c testcase -i /path/to/image.dd -s foo
```

If an `IMAGE` is not provided, dfDewey will search all images in the given case.

dfDewey can also search for a list of terms at once. The terms can be placed in
a text file one per line. In this case, only the number of results for each term
is returned.

```shell
python3 dfdewey.py -c testcase -i /path/to/image.dd --search_list search_terms.txt
```
