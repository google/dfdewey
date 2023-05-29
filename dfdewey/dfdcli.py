#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright 2020 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""DFDewey Command-Line Interface."""

import argparse
import hashlib
import logging
import os
import sys

from dfdewey.utils.image_processor import ImageProcessor, ImageProcessorOptions
from dfdewey.utils.index_searcher import IndexSearcher

STRING_INDEXING_LOG_INTERVAL = 10000000

# Setup logging
log = logging.getLogger('dfdewey')


class _StringRecord():
  """OpenSearch string record.

  Attributes:
    image: Hash to identify the source image of the string
    offset: Byte offset of the string within the source image
    file_offset: If the string is extracted from a compressed stream, the byte
        offset within the stream
    data: The string to be indexed
  """

  def __init__(self):
    self.image = ''
    self.offset = 0
    self.file_offset = None
    self.data = ''


def get_image_id(image_path):
  """Calculate image ID.

  The image ID is the MD5 of the first 2GB of the disk being processed.

  Args:
    image_path: Path to the image / disk

  Returns:
    The calculated image ID.
  """
  image_path = os.path.abspath(image_path)
  if not os.path.exists(image_path):
    log.error('Image does not exist: {0!s}'.format(image_path))
    sys.exit(1)

  image_id = None
  with open(image_path, 'rb') as image_file:
    hash = hashlib.md5()
    hashed = 0
    while True:
      chunk = image_file.read(8192)
      if not chunk:
        break
      hash.update(chunk)
      hashed += 1
      if hashed == 262144:
        break
    image_id = hash.digest().hex()

  return image_id


def main():
  """Main DFDewey function."""
  args = parse_args()

  setup_logging()

  image_id = None
  if args.image != 'all':
    image_id = get_image_id(args.image)
    if image_id is None:
      log.error('Could not calculate image ID.')
      sys.exit(1)

  if not args.search and not args.search_list:
    # Processing an image since no search terms specified
    if args.image == 'all':
      log.error('Image must be supplied for processing.')
      sys.exit(1)
    image_processor_options = ImageProcessorOptions(
        not args.no_base64, not args.no_gzip, not args.no_zip, args.reparse,
        args.reindex, args.delete)
    image_processor = ImageProcessor(
        args.case, image_id, os.path.abspath(args.image),
        image_processor_options, args.config)
    image_processor.process_image()
  else:
    index_searcher = IndexSearcher(
        args.case, image_id, args.image, args.json, args.config)
    if args.search:
      index_searcher.search(args.search, args.highlight)
    elif args.search_list:
      index_searcher.list_search(args.search_list)


def parse_args():
  """Argument parsing function.

  Returns:
    Arguments namespace.
  """
  parser = argparse.ArgumentParser()

  parser.add_argument('case', help='case ID')
  parser.add_argument(
      'image', nargs='?', default='all', help='image file (default: \'all\')')

  parser.add_argument('-c', '--config', help='datastore config file')

  # Indexing args
  parser.add_argument(
      '--no_base64', help='don\'t decode base64', action='store_true')
  parser.add_argument(
      '--no_gzip', help='don\'t decompress gzip', action='store_true')
  parser.add_argument(
      '--no_zip', help='don\'t decompress zip', action='store_true')
  parser.add_argument(
      '--reparse',
      help='reparse filesystem (will delete existing filesystem mapping)',
      action='store_true')
  parser.add_argument(
      '--reindex', help='recreate index (will delete existing index)',
      action='store_true')
  parser.add_argument(
      '--delete', help='delete image (filesystem mapping and index)',
      action='store_true')

  # Search args
  parser.add_argument(
      '--highlight', help='highlight search term in results',
      action='store_true')
  parser.add_argument(
      '--json', help='output results in JSON format', action='store_true')
  parser.add_argument('-s', '--search', help='search query')
  parser.add_argument('--search_list', help='file with search queries')

  args = parser.parse_args()
  return args


def setup_logging():
  """Configure the logger."""
  log.propagate = False
  log.setLevel(logging.INFO)

  # Log to stdout
  console_handler = logging.StreamHandler(sys.stdout)
  console_handler.setLevel(logging.INFO)
  formatter = logging.Formatter('[%(levelname)s] %(message)s')
  console_handler.setFormatter(formatter)
  log.addHandler(console_handler)


if __name__ == '__main__':
  main()
