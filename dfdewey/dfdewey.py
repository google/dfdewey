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
import os
import subprocess
import tempfile

from elastic import ElasticsearchDataStore


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
  parser.add_argument(
      '--no_base64', help='don\'t decode base64', action='store_true')
  parser.add_argument(
      '--no_gzip', help='don\'t process gzip files', action='store_true')
  parser.add_argument(
      '--no_zip', help='don\'t process zip files', action='store_true')
  parser.add_argument('image_file', help='image file to be processed')
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
  es = ElasticsearchDataStore()
  index_name, event_type = es.create_index()
  print('Index {0:s} created.'.format(index_name))

  with open('/'.join((output_path, 'strings.txt')), 'r') as strings:
    for line in strings:
      if line[0] != '#':
        string_record = _StringRecord()
        string_record.image = image_path

        line = line.split('\t')
        offset = line[0]
        data = ''.join(line[1:])
        if offset.find('-') > 0:
          offset = offset.split('-')
          image_offset = offset[0]
          file_offset = ''.join(offset[1:])
          string_record.offset = int(image_offset)
          string_record.file_offset = file_offset
        else:
          string_record.offset = int(offset)

        string_record.data = data
        records = index_record(es, index_name, event_type, string_record)
        if records % 10000 == 0:
          print('Indexed {0:d} records...'.format(records))

  records = es.import_event(index_name, event_type)
  print('\n*** Indexing complete.\nIndexed {0:d} strings.'.format(records))


def main():
  """Main DFDewey function."""
  args = parse_args()
  image_path = os.path.abspath(args.image_file)
  output_path = tempfile.mkdtemp()

  cmd = ['bulk_extractor',
         '-o', output_path,
         '-x', 'all',
         '-e', 'strings']
  if not args.no_base64:
    cmd.extend(['-e', 'base64'])
  if not args.no_gzip:
    cmd.extend(['-e', 'gzip'])
  if not args.no_zip:
    cmd.extend(['-e', 'zip'])
  cmd.extend([image_path])
  print('\n*** Running bulk extractor:\n{0:s}'.format(' '.join(cmd)))
  subprocess.run(cmd)

  index_strings(output_path, image_path)

if __name__ == '__main__':
  main()
