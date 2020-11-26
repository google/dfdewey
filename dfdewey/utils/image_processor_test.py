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
"""Tests for image processor."""

import unittest
import mock

from dfdewey.datastore.postgresql import PostgresqlDataStore
from dfdewey.utils.image_processor import ImageProcessor, ImageProcessorOptions

TEST_CASE = 'testcase'
TEST_IMAGE = 'test.dd'
TEST_IMAGE_HASH = 'd41d8cd98f00b204e9800998ecf8427e'


class ImageProcessorTest(unittest.TestCase):
  """Tests for image processor."""

  def _get_image_processor(self):
    """Get a test image processor.

    Returns:
      Test image processor.
    """
    image_processor_options = ImageProcessorOptions()
    image_processor = ImageProcessor(
        TEST_CASE, TEST_IMAGE, image_processor_options)

    image_processor.image_hash = TEST_IMAGE_HASH

    with mock.patch('psycopg2.connect') as _:
      postgresql = PostgresqlDataStore()
      image_processor.postgresql = postgresql
    return image_processor

  @mock.patch(
      'dfdewey.utils.image_processor.ImageProcessor._initialise_database')
  @mock.patch('dfdewey.datastore.postgresql.PostgresqlDataStore.value_exists')
  @mock.patch('dfdewey.datastore.postgresql.PostgresqlDataStore.table_exists')
  @mock.patch(
      'dfdewey.datastore.postgresql.PostgresqlDataStore.query_single_row')
  @mock.patch('dfdewey.datastore.postgresql.PostgresqlDataStore.execute')
  def test_already_parsed(
      self, mock_execute, mock_query_single_row, mock_table_exists,
      mock_value_exists, mock_initialise_database):
    """Test already parsed method."""
    image_processor = self._get_image_processor()

    # Test if new database
    mock_table_exists.return_value = False
    result = image_processor._already_parsed()

    mock_initialise_database.assert_called_once()
    calls = [
        mock.call((
            'INSERT INTO images (image_path, image_hash) '
            'VALUES (\'{0:s}\', \'{1:s}\')').format(
                TEST_IMAGE, TEST_IMAGE_HASH)),
        mock.call((
            'INSERT INTO image_case (case_id, image_hash) '
            'VALUES (\'{0:s}\', \'{1:s}\')').format(TEST_CASE, TEST_IMAGE_HASH))
    ]
    mock_execute.assert_has_calls(calls)
    self.assertEqual(result, False)

    # Test database exists, image already in case
    mock_table_exists.return_value = True
    mock_value_exists.return_value = True
    mock_query_single_row.return_value = (1,)
    mock_execute.reset_mock()

    result = image_processor._already_parsed()
    mock_execute.assert_not_called()
    self.assertEqual(result, True)

    # Test database exists, image exists, but not in case
    mock_query_single_row.return_value = None
    result = image_processor._already_parsed()
    mock_execute.assert_called_once_with((
        'INSERT INTO image_case (case_id, image_hash) '
        'VALUES (\'{0:s}\', \'{1:s}\')').format(TEST_CASE, TEST_IMAGE_HASH))
    self.assertEqual(result, True)


if __name__ == '__main__':
  unittest.main()
