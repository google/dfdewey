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
"""Tests for index searcher."""

import os
import re
import unittest

import mock

from dfdewey.utils.image_processor import FileEntryScanner
from dfdewey.utils.index_searcher import IndexSearcher

TEST_CASE = 'testcase'
TEST_IMAGE = 'test.dd'
TEST_IMAGE_HASH = 'd41d8cd98f00b204e9800998ecf8427e'
TEST_IMAGE_ID = 'd41d8cd98f00b204e9800998ecf8427e'


class IndexSearcherTest(unittest.TestCase):
  """Tests for index searcher."""

  def _get_index_searcher(self):
    """Get a test index searcher.

    Returns:
      Test index searcher.
    """
    with mock.patch('psycopg2.connect'), mock.patch(
        'dfdewey.datastore.postgresql.PostgresqlDataStore._query_single_row'
    ) as mock_query_single_row:
      mock_query_single_row.return_value = (TEST_IMAGE_HASH,)
      index_searcher = IndexSearcher(TEST_CASE, TEST_IMAGE_ID, TEST_IMAGE)
      index_searcher.config = None
    return index_searcher

  @mock.patch('dfdewey.datastore.postgresql.PostgresqlDataStore._query')
  def test_get_case_images(self, mock_query):
    """Test get case images method."""
    mock_query.return_value = [(
        'hash1',
        'image1.dd',
    ), (
        'hash2',
        'image2.dd',
    )]
    with mock.patch('psycopg2.connect'):
      index_searcher = IndexSearcher(TEST_CASE, None, 'all')
    self.assertEqual(index_searcher.images['hash1'], 'image1.dd')
    self.assertEqual(index_searcher.images['hash2'], 'image2.dd')

  @mock.patch('dfdewey.datastore.postgresql.PostgresqlDataStore.get_inodes')
  @mock.patch(
      'dfdewey.datastore.postgresql.PostgresqlDataStore.get_filenames_from_inode'
  )
  @mock.patch(
      'dfdewey.datastore.postgresql.PostgresqlDataStore.switch_database')
  def test_get_filenames_from_offset(
      self, mock_switch_database, mock_get_filenames_from_inode,
      mock_get_inodes):
    """Test get filenames from offset method."""
    index_searcher = self._get_index_searcher()
    current_path = os.path.abspath(os.path.dirname(__file__))
    image_path = os.path.join(current_path, '..', '..', 'test_data', 'test.dd')
    # Test offset not within a file
    filenames = index_searcher._get_filenames_from_offset(
        image_path, TEST_IMAGE_HASH, 1048579)
    mock_switch_database.assert_called_once_with(
        db_name=''.join(('fs', TEST_IMAGE_HASH)))
    self.assertIsInstance(index_searcher.scanner, FileEntryScanner)
    mock_get_inodes.assert_called_once_with(0, '/p1')
    self.assertEqual(filenames, [])

    # Test offset within a file
    mock_get_inodes.reset_mock()
    mock_get_inodes.return_value = [0]
    mock_get_filenames_from_inode.return_value = ['adams.txt']
    filenames = index_searcher._get_filenames_from_offset(
        image_path, TEST_IMAGE_HASH, 1133936)
    mock_get_inodes.assert_called_once_with(20, '/p1')
    mock_get_filenames_from_inode.assert_called_once_with(67, '/p1')
    self.assertEqual(filenames, ['adams.txt (67)'])

    # Test volume image
    mock_get_inodes.reset_mock()
    mock_get_inodes.return_value = [2]
    mock_get_filenames_from_inode.reset_mock()
    mock_get_filenames_from_inode.return_value = []
    image_path = os.path.join(
        current_path, '..', '..', 'test_data', 'test_volume.dd')
    filenames = index_searcher._get_filenames_from_offset(
        image_path, TEST_IMAGE_HASH, 334216)
    mock_get_inodes.assert_called_once_with(326, '/')
    mock_get_filenames_from_inode.assert_called_once_with(2, '/')
    self.assertEqual(filenames, [' (2)'])

    # Test missing image
    index_searcher.scanner = None
    filenames = index_searcher._get_filenames_from_offset(
        'test.dd', TEST_IMAGE_HASH, 1048579)
    self.assertEqual(filenames, [])

  def test_highlight_hit(self):
    """Test highlight hit method."""
    index_searcher = self._get_index_searcher()
    data = 'test1 test2 test3'
    hit_positions = re.finditer('test3', data)
    wrapped_data = ['test1', 'test2', 'test3']
    result = index_searcher._highlight_hit(wrapped_data, hit_positions)
    self.assertEqual(
        result, ['test1', 'test2', '\u001b[31m\u001b[1mtest3\u001b[0m'])

    hit_positions = re.finditer('st1 test2 te', data)
    wrapped_data = ['test1', 'test2', 'test3']
    result = index_searcher._highlight_hit(wrapped_data, hit_positions)
    self.assertEqual(
        result, [
            'te\u001b[31m\u001b[1mst1\u001b[0m',
            '\u001b[31m\u001b[1mtest2\u001b[0m',
            '\u001b[31m\u001b[1mte\u001b[0mst3'
        ])

  @mock.patch('logging.Logger.info')
  @mock.patch('dfdewey.datastore.opensearch.OpenSearchDataStore.search')
  def test_list_search(self, mock_search, mock_output):
    """Test list search."""
    index_searcher = self._get_index_searcher()
    index_searcher.images = {TEST_IMAGE_HASH: TEST_IMAGE}
    current_path = os.path.abspath(os.path.dirname(__file__))
    query_list = os.path.join(
        current_path, '..', '..', 'test_data', 'searchlist.txt')
    mock_search.return_value = {'hits': {'total': {'value': 1}}}
    index_searcher.list_search(query_list)
    self.assertEqual(mock_search.call_count, 5)
    mock_output.assert_called_once()
    self.assertEqual(mock_output.call_args.args[1], TEST_IMAGE)
    self.assertEqual(mock_output.call_args.args[2], TEST_IMAGE_HASH)
    self.assertEqual(mock_output.call_args.args[3], query_list)

    # Test JSON output
    expected_output = '{"%s": {"image": "%s", "results": {"\\"list\\"": 1, "\\"of\\"": 1, "\\"test\\"": 1, "\\"search\\"": 1, "\\"terms\\"": 1}}}' % (
        TEST_IMAGE_HASH, TEST_IMAGE)
    mock_output.reset_mock()
    index_searcher.json = True
    index_searcher.list_search(query_list)
    mock_output.assert_called_once()
    self.assertEqual(mock_output.call_args.args[1], expected_output)

    # Test no results
    mock_output.reset_mock()
    index_searcher.json = False
    mock_search.return_value = {'hits': {'total': {'value': 0}}}
    index_searcher.list_search(query_list)
    mock_output.assert_called_once()
    self.assertEqual(mock_output.call_args.args[4], 'No results.')

  @mock.patch('logging.Logger.info')
  @mock.patch('dfdewey.datastore.postgresql.PostgresqlDataStore')
  @mock.patch('dfdewey.datastore.opensearch.OpenSearchDataStore.search')
  def test_search(self, mock_search, mock_postgresql, mock_output):
    """Test search method."""
    index_searcher = self._get_index_searcher()
    current_path = os.path.abspath(os.path.dirname(__file__))
    image_path = os.path.join(current_path, '..', '..', 'test_data', 'test.dd')
    index_searcher.images = {TEST_IMAGE_HASH: image_path}
    index_searcher.postgresql = mock_postgresql
    mock_search.return_value = {
        'took': 2,
        'hits': {
            'total': {
                'value': 1
            },
            'hits': [{
                '_source': {
                    'offset': 12889600,
                    'file_offset': 'GZIP-0',
                    'data': 'test'
                }
            }]
        }
    }
    # Test with highlighting
    index_searcher.search('test', True)
    mock_search.assert_called_once()
    output_calls = mock_output.mock_calls
    self.assertEqual(output_calls[0].args[1], image_path)
    self.assertEqual(output_calls[0].args[2], TEST_IMAGE_HASH)
    self.assertEqual(output_calls[0].args[3], 'test')
    self.assertEqual(output_calls[1].args[1], 1)
    self.assertEqual(output_calls[1].args[2], 2)
    table_output = output_calls[1].args[3]
    self.assertEqual(table_output[76:84], '12889600')
    self.assertEqual(table_output[106:123], '\u001b[31m\u001b[1mtest\u001b[0m')
    self.assertEqual(table_output[124:130], 'GZIP-0')

    # Test without highlighting
    mock_search.reset_mock()
    mock_output.reset_mock()
    index_searcher.search('test')
    mock_search.assert_called_once()
    output_calls = mock_output.mock_calls
    self.assertEqual(output_calls[0].args[1], image_path)
    self.assertEqual(output_calls[0].args[2], TEST_IMAGE_HASH)
    self.assertEqual(output_calls[0].args[3], 'test')
    self.assertEqual(output_calls[1].args[1], 1)
    self.assertEqual(output_calls[1].args[2], 2)
    table_output = output_calls[1].args[3]
    self.assertEqual(table_output[76:84], '12889600')
    self.assertEqual(table_output[106:110], 'test')
    self.assertEqual(table_output[111:117], 'GZIP-0')

    # Test JSON output
    expected_output = '{"%s": {"image": "%s", "test": [{"Offset": "12889600\\nGZIP-0", "Filename (inode)": "", "String": "test"}]}}' % (
        TEST_IMAGE_HASH, image_path)
    mock_search.reset_mock()
    mock_output.reset_mock()
    index_searcher.json = True
    index_searcher.search('test')
    mock_search.assert_called_once()
    output_calls = mock_output.mock_calls
    self.assertEqual(output_calls[1].args[1], expected_output)

  def test_wrap_filenames(self):
    """Test wrap filenames method."""
    index_searcher = self._get_index_searcher()
    filenames = ['aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa']
    filenames = index_searcher._wrap_filenames(filenames, width=20)
    expected_filenames = [
        'aaaaaaaaaaaaaaaaaaaa\naaaaaaaaaaaaaaaaaaaa\naaaaaaaaaaaaaaaaaaaa'
    ]
    self.assertEqual(filenames, expected_filenames)


if __name__ == '__main__':
  unittest.main()
