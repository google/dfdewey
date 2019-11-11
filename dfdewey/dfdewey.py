# -*- coding: utf-8 -*-
# Copyright 2019 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""DFDewey Command-Line Interface."""

import argparse
import datetime
import os
import subprocess
import sys
import tempfile

from datastore.elastic import ElasticsearchDataStore
from utils import image


class _StringRecord(object):

  def __init__(self):
    self.image = ''
    self.offset = 0
    self.file_offset = None
    self.data = ''


def parse_args():
  """Argument parsing function.

  Returns:
      Arguments namespace.
  """
  parser = argparse.ArgumentParser()

  # Indexing args
  parser.add_argument(
      '--no_base64', help='don\'t decode base64', action='store_true')
  parser.add_argument(
      '--no_gzip', help='don\'t process gzip files', action='store_true')
  parser.add_argument(
      '--no_zip', help='don\'t process zip files', action='store_true')
  parser.add_argument('--image_file', help='image file to be processed')

  parser.add_argument('--index_id', help='datastore index ID')

  # Search args
  parser.add_argument('-s', '--search', help='search query')
  parser.add_argument(
      '-f', '--file_lookup', help='enable file lookups', action='store_true')

  args = parser.parse_args()
  return args


def index_record(es, index_name, event_type, string_record):
  """Index a single record.

  Args:
      es (Elasticsearch):     Elasticsearch datastore
      index_name (string):    UUID for the index
      event_type (string):    Type of event being processed
      string_record (record): String record to be indexed

  Returns:
      Number of records processed
  """
  json_record = {
      'image': string_record.image,
      'offset': string_record.offset,
      'file_offset': string_record.file_offset,
      'data': string_record.data
  }
  return es.import_event(index_name, event_type, event=json_record)


def index_strings(output_path, image_path):
  """ElasticSearch indexing function.

  Args:
      output_path (string): The output directory from bulk_extractor
      image_path (string):  Path to the parsed image
  """
  print('\n*** Indexing data...')
  print(datetime.datetime.now())
  es = ElasticsearchDataStore()
  index_name, event_type = es.create_index()
  print('Index {0:s} created.'.format(index_name))

  with open('/'.join((output_path, 'wordlist.txt')), 'r') as strings:
    for line in strings:
      if line[0] != '#':
        string_record = _StringRecord()
        string_record.image = image_path

        line = line.split('\t')
        offset = line[0]
        data = '\t'.join(line[1:])
        if offset.find('-') > 0:
          offset = offset.split('-')
          image_offset = offset[0]
          file_offset = '-'.join(offset[1:])
          string_record.offset = int(image_offset)
          string_record.file_offset = file_offset
        else:
          string_record.offset = int(offset)

        string_record.data = data
        records = index_record(es, index_name, event_type, string_record)
        if records % 10000000 == 0:
          print('Indexed {0:d} records...'.format(records))

  records = es.import_event(index_name, event_type)
  print('\n*** Indexing complete.\nIndexed {0:d} strings.'.format(records))
  print(datetime.datetime.now())


def search_index(index_id, search_query):
  """ElasticSearch indexing function.

  Args:
      index_id (string): The ID of the index to be searched
      search_query (string): The query to run against the index

  Returns:
      Search results returned
  """
  es = ElasticsearchDataStore()
  return es.search(index_id, search_query, size=1000)


def main():
  """Main DFDewey function."""
  args = parse_args()
  if args.image_file:
    image_path = os.path.abspath(args.image_file)
    output_path = tempfile.mkdtemp()

    cmd = ['bulk_extractor',
           '-o', output_path,
           '-x', 'all',
           '-e', 'wordlist']

    if not args.no_base64:
      cmd.extend(['-e', 'base64'])
    if not args.no_gzip:
      cmd.extend(['-e', 'gzip'])
    if not args.no_zip:
      cmd.extend(['-e', 'zip'])

    cmd.extend(['-S', 'strings=YES', '-S', 'word_max=1000000'])
    cmd.extend([image_path])
    print('\n*** Running bulk extractor:\n{0:s}'.format(' '.join(cmd)))
    subprocess.run(cmd)
    index_strings(output_path, image_path)
  elif args.search:
    if not args.index_id:
      print('Index ID is required to search.')
      sys.exit(-1)

    print('\n*** Searching for \'{0:s}\'...'.format(args.search))
    results = search_index(args.index_id, args.search)
    print('Returned {0:d} results:'.format(results['hits']['total']['value']))
    filename = '*Disabled*'
    for hit in results['hits']['hits']:
      if args.file_lookup:
        filename = image.get_filename_from_offset(
            hit['_source']['image'],
            int(hit['_source']['offset']))
      if hit['_source']['file_offset']:
        print('Offset: {0:d}\tFile: {1:s}\tFile offset:{2:s}\t'
              'String: {3:s}'.format(
                  hit['_source']['offset'],
                  filename,
                  hit['_source']['file_offset'],
                  hit['_source']['data'].strip()))
      else:
        print('Offset: {0:d}\tFile: {1:s}\tString: {2:s}'.format(
            hit['_source']['offset'],
            filename,
            hit['_source']['data'].strip()))


if __name__ == '__main__':
  main()
