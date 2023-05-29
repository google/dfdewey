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
"""Index searcher."""

import json
import logging
import os
import re
import textwrap

from dfvfs.lib import errors as dfvfs_errors
import pytsk3
from tabulate import tabulate

import dfdewey.config as dfdewey_config
from dfdewey.datastore.opensearch import OpenSearchDataStore
from dfdewey.datastore.postgresql import PostgresqlDataStore
from dfdewey.utils.image_processor import FileEntryScanner

DATA_COLUMN_WIDTH = 110
TEXT_HIGHLIGHT = '\u001b[31m\u001b[1m'
TEXT_RESET = '\u001b[0m'

log = logging.getLogger('dfdewey.index_searcher')


class _SearchHit():
  """Search result.

  Attributes:
    offset: byte offset of the string within the source image.
    filename: filename containing the string if applicable.
    data: the responsive string.
  """

  def __init__(self):
    self.offset = 0
    self.filename = None
    self.data = ''

  def copy_to_dict(self):
    """Copies the search hit to a dictionary.

    Returns:
      dict[str, object]: search hit attributes.
    """
    search_hit_dict = {}
    search_hit_dict['Offset'] = self.offset
    search_hit_dict['Filename (inode)'] = self.filename
    search_hit_dict['String'] = self.data

    return search_hit_dict


class IndexSearcher():
  """Index Searcher class."""

  def __init__(self, case, image_id, image, json=False, config_file=None):
    """Create an index searcher."""
    super().__init__()
    self.case = case
    self.config = dfdewey_config.load_config(config_file)
    self.opensearch = None
    self.image = image
    self.image_id = image_id
    self.images = {}
    self.json = json
    self.postgresql = None
    self.scanner = None

    if self.config:
      self.postgresql = PostgresqlDataStore(
          host=self.config.PG_HOST, port=self.config.PG_PORT,
          db_name=self.config.PG_DB_NAME)
      self.opensearch = OpenSearchDataStore(
          host=self.config.OS_HOST, port=self.config.OS_PORT,
          url=self.config.OS_URL)
    else:
      self.postgresql = PostgresqlDataStore()
      self.opensearch = OpenSearchDataStore()

    if image != 'all':
      self.image = os.path.abspath(self.image)
      image_hash = self.postgresql.get_image_hash(self.image_id)
      if image_hash:
        self.images[image_hash] = self.image
    else:
      self.images = self.postgresql.get_case_images(self.case)

  def _get_filenames_from_offset(self, image_path, image_hash, offset):
    """Gets filename(s) given a byte offset within an image.

    Args:
      image_path: source image path.
      image_hash: source image hash.
      offset: byte offset within the image.

    Returns:
      Filename(s) allocated to the given offset, or None.
    """
    filenames = []

    database_name = ''.join(('fs', image_hash))
    if self.config:
      self.postgresql.switch_database(
          host=self.config.PG_HOST, port=self.config.PG_PORT,
          db_name=database_name)
    else:
      self.postgresql.switch_database(db_name=database_name)

    volume_extents = {}
    try:
      if not self.scanner:
        self.scanner = FileEntryScanner()
      volume_extents = self.scanner.get_volume_extents(image_path)
    except dfvfs_errors.ScannerError as e:
      log.error('Error scanning for partitions: %s', e)

    hit_location = None
    partition_offset = None
    for location, extent in volume_extents.items():
      if not extent['end']:
        # Image is of a single volume
        hit_location = location
        partition_offset = extent['start']
      elif extent['start'] <= offset < extent['end']:
        hit_location = location
        partition_offset = extent['start']

    if partition_offset is not None:
      try:
        img = pytsk3.Img_Info(image_path)
        filesystem = pytsk3.FS_Info(img, offset=partition_offset)
        block_size = filesystem.info.block_size
      except TypeError as e:
        log.error('Error opening image: %s', e)

      inodes = self.postgresql.get_inodes(
          int((offset - partition_offset) / block_size), hit_location)

      if inodes:
        for inode in inodes:
          # Account for resident files
          if (inode == 0 and
              filesystem.info.ftype == pytsk3.TSK_FS_TYPE_NTFS_DETECT):
            mft_record_size_offset = 0x40 + partition_offset
            mft_record_size = int.from_bytes(
                img.read(mft_record_size_offset, 1), 'little', signed=True)
            if mft_record_size < 0:
              mft_record_size = 2**(mft_record_size * -1)
            else:
              mft_record_size = mft_record_size * block_size
            inode = self._get_ntfs_resident_inode((offset - partition_offset),
                                                  filesystem, mft_record_size)

          inode_filenames = self.postgresql.get_filenames_from_inode(
              inode, hit_location)
          filename = '\n'.join(inode_filenames)
          filenames.append('{0:s} ({1:d})'.format(filename, inode))

    return filenames

  def _get_ntfs_resident_inode(self, offset, filesystem, mft_record_size):
    """Gets the inode number associated with NTFS $MFT resident data.

    Args:
      offset: data offset within volume.
      filesystem: pytsk3 FS_INFO object.
      mft_record_size: size of each $MFT entry.

    Returns:
      inode number of resident data
    """
    block_size = filesystem.info.block_size
    offset_block = int(offset / block_size)

    inode = filesystem.open_meta(0)
    mft_entry = 0
    for attr in inode:
      for run in attr:
        for block in range(run.len):
          if run.addr + block == offset_block:
            mft_entry += int(
                (offset - (offset_block * block_size)) / mft_record_size)
            return mft_entry
          mft_entry += int(block_size / mft_record_size)
    return 0

  def _highlight_hit(self, data, hit_positions):
    """Highlight search term in hit data.

    Args:
      data (str): responsive strings.
      query (str): search term.

    Returns:
      Highlighted strings.
    """
    lengths = []
    for string in data:
      lengths.append(len(string))
    for hit in reversed(list(hit_positions)):
      complete = False
      i = 0
      hit_start = hit.start()
      hit_end = hit.end()
      while hit_start > lengths[i]:
        hit_start -= lengths[i] + 1
        hit_end -= lengths[i] + 1
        i += 1
      new_data = []
      new_data.append(data[i][:hit_start])
      new_data.append(TEXT_HIGHLIGHT)
      if hit_end <= lengths[i]:
        new_data.append(data[i][hit_start:hit_end])
        new_data.append(TEXT_RESET)
        new_data.append(data[i][hit_end:])
        complete = True
      else:
        new_data.append(data[i][hit_start:])
        new_data.append(TEXT_RESET)
      data[i] = ''.join(new_data)
      while hit_end > lengths[i]:
        hit_end -= lengths[i] + 1
        i += 1
        if hit_end > lengths[i]:
          new_data = []
          new_data.append(TEXT_HIGHLIGHT)
          new_data.append(data[i])
          new_data.append(TEXT_RESET)
          data[i] = ''.join(new_data)
      if not complete:
        new_data = []
        new_data.append(TEXT_HIGHLIGHT)
        new_data.append(data[i][:hit_end])
        new_data.append(TEXT_RESET)
        new_data.append(data[i][hit_end:])
        data[i] = ''.join(new_data)

    return data

  def _wrap_filenames(self, filenames, width=50):
    """Wrap filenames for tabular output.

    Args:
      filenames (List[str]): list of filenames to wrap.
      width (int): target string length.

    Returns:
      List of wrapped filenames.
    """
    for i in range(len(filenames)):
      filename = textwrap.wrap(filenames[i], width, replace_whitespace=False)
      filenames[i] = '\n'.join(filename)
    return filenames

  def list_search(self, query_list):
    """Query a list of search terms.

    Args:
      query_list (str): path to a text file containing multiple search terms.
    """
    search_results = {}
    for image_hash, image_path in self.images.items():
      search_results[image_hash] = {}
      search_results[image_hash]['image'] = image_path
      search_results[image_hash]['results'] = {}
      index = ''.join(('es', image_hash))
      with open(query_list, 'r') as search_terms:
        table_data = []
        for term in search_terms:
          term = ''.join(('"', term.strip(), '"'))
          results = self.opensearch.search(index, term)
          hit_count = results['hits']['total']['value']
          if hit_count > 0:
            search_results[image_hash]['results'][term] = hit_count
            table_data.append({'Search term': term, 'Hits': hit_count})
      if table_data:
        output = tabulate(table_data, headers='keys', tablefmt='simple')
      else:
        output = 'No results.'
      if not self.json:
        log.info(
            'Searched %s (%s) for terms in %s\n\n%s\n', image_path, image_hash,
            query_list, output)
    if self.json:
      log.info('%s', json.JSONEncoder().encode(search_results))

  def search(self, query, highlight=False):
    """Run a single query.

    Args:
      query (str): query to run.
      highlight (bool): flag to highlight search term in results.
    """
    search_results = {}
    for image_hash, image_path in self.images.items():
      search_results[image_hash] = {}
      search_results[image_hash]['image'] = image_path
      log.info('Searching %s (%s) for "%s"', image_path, image_hash, query)
      index = ''.join(('es', image_hash))
      results = self.opensearch.search(index, query)
      result_count = results['hits']['total']['value']
      time_taken = results['took']

      results = results['hits']['hits']
      hits = []
      for result in results:
        hit = _SearchHit()
        offset = str(result['_source']['offset'])
        if result['_source']['file_offset']:
          streams = result['_source']['file_offset'].split('-')
          file_offset = []
          for i in range(0, len(streams), 2):
            stream = '-'.join((streams[i], streams[i + 1]))
            file_offset.append(stream)
          file_offset = '\n'.join(file_offset)
          offset = '\n'.join((offset, file_offset))
        hit.offset = offset
        filenames = self._get_filenames_from_offset(
            image_path, image_hash, result['_source']['offset'])
        filenames = self._wrap_filenames(filenames)
        hit.filename = '\n'.join(filenames)
        hit.data = result['_source']['data'].strip()
        re_query = query.replace('*', '.*')
        re_query = re_query.replace('?', '.')
        hit_positions = re.finditer(re_query, hit.data, re.IGNORECASE)
        hit.data = textwrap.wrap(hit.data, DATA_COLUMN_WIDTH)
        if highlight:
          hit.data = self._highlight_hit(hit.data, hit_positions)
        hit.data = '\n'.join(hit.data)
        hits.append(hit.copy_to_dict())
      search_results[image_hash][query] = hits
      if not self.json:
        output = tabulate(hits, headers='keys', tablefmt='simple')
        log.info(
            'Returned %d results in %dms.\n\n%s\n', result_count, time_taken,
            output)
    if self.json:
      log.info('%s', json.JSONEncoder().encode(search_results))
