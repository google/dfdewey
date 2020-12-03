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
import unittest

import mock

from dfdewey.utils.image_processor import FileEntryScanner
from dfdewey.utils.index_searcher import IndexSearcher

TEST_CASE = 'testcase'
TEST_IMAGE = 'test.dd'
TEST_IMAGE_HASH = 'd41d8cd98f00b204e9800998ecf8427e'


class IndexSearcherTest(unittest.TestCase):
  """Tests for index searcher."""

  def _get_index_searcher(self):
    """Get a test index searcher.

    Returns:
      Test index searcher.
    """
    with mock.patch('psycopg2.connect'), mock.patch(
        'dfdewey.datastore.postgresql.PostgresqlDataStore.query_single_row'
    ) as mock_query_single_row:
      mock_query_single_row.return_value = (TEST_IMAGE_HASH,)
      index_searcher = IndexSearcher(TEST_CASE, TEST_IMAGE)
    return index_searcher

  @mock.patch('dfdewey.datastore.postgresql.PostgresqlDataStore.query')
  def test_get_case_images(self, mock_query):
    """Test get case images method."""
    index_searcher = self._get_index_searcher()
    mock_query.return_value = [(
        'hash1',
        'image1.dd',
    ), (
        'hash2',
        'image2.dd',
    )]
    index_searcher._get_case_images()
    self.assertEqual(index_searcher.images['hash1'], 'image1.dd')
    self.assertEqual(index_searcher.images['hash2'], 'image2.dd')

  @mock.patch('dfdewey.datastore.postgresql.PostgresqlDataStore.query')
  def test_get_filenames_from_inode(self, mock_query):
    """Test get filenames from inode method."""
    index_searcher = self._get_index_searcher()
    mock_query.return_value = [('test.txt',), ('test.txt:ads',)]
    filenames = index_searcher._get_filenames_from_inode(42, '/p1')
    self.assertEqual(len(filenames), 2)
    self.assertEqual(filenames[0], 'test.txt')
    self.assertEqual(filenames[1], 'test.txt:ads')

  @mock.patch('dfdewey.utils.index_searcher.IndexSearcher._get_inodes')
  @mock.patch(
      'dfdewey.utils.index_searcher.IndexSearcher._get_filenames_from_inode')
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
    mock_get_inodes.return_value = [(0,)]
    mock_get_filenames_from_inode.return_value = ['adams.txt']
    filenames = index_searcher._get_filenames_from_offset(
        image_path, TEST_IMAGE_HASH, 1133936)
    mock_get_inodes.assert_called_once_with(20, '/p1')
    mock_get_filenames_from_inode.assert_called_once_with(67, '/p1')
    self.assertEqual(filenames, ['adams.txt (67)'])

    # Test missing image
    index_searcher.scanner = None
    filenames = index_searcher._get_filenames_from_offset(
        'test.dd', TEST_IMAGE_HASH, 1048579)
    self.assertEqual(filenames, [])

    # TODO: Test volume image


if __name__ == '__main__':
  unittest.main()
