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
"""Tests for PostgreSQL datastore."""

import unittest

import mock
from psycopg2 import OperationalError

from dfdewey.datastore.postgresql import PostgresqlDataStore
from dfdewey.utils.image_processor_test import TEST_CASE, TEST_IMAGE, TEST_IMAGE_HASH, TEST_IMAGE_ID


class PostgresqlTest(unittest.TestCase):
  """Tests for PostgreSQL datastore."""

  def _get_datastore(self):
    """Get a mock postgresql datastore.

    Returns:
      Mock postgresql datastore.
    """
    with mock.patch('psycopg2.connect') as _:
      db = PostgresqlDataStore(autocommit=True)
    return db

  @mock.patch('psycopg2.extras.execute_values')
  def test_bulk_insert(self, mock_execute_values):
    """Test bulk insert method."""
    db = self._get_datastore()
    rows = [(1, 1), (2, 2), (3, 3)]
    db.bulk_insert('blocks (block, inum)', rows)

    expected_sql = (
        'INSERT INTO blocks (block, inum) '
        'VALUES %s ON CONFLICT DO NOTHING')
    mock_execute_values.assert_called_once_with(db.cursor, expected_sql, rows)

  def test_create_filesystem_database(self):
    """Test create filesystem database method."""
    db = self._get_datastore()
    with mock.patch.object(db.cursor, 'execute') as mock_execute:
      db.create_filesystem_database()

      calls = [
          mock.call((
              'CREATE TABLE blocks (block INTEGER, inum INTEGER, part TEXT, '
              'PRIMARY KEY (block, inum, part))')),
          mock.call((
              'CREATE TABLE files (inum INTEGER, filename TEXT, part TEXT, '
              'PRIMARY KEY (inum, filename, part))'))
      ]
      mock_execute.assert_has_calls(calls)

  def test_delete_filesystem_database(self):
    """Test delete filesystem database method."""
    db = self._get_datastore()
    db_name = ''.join(('fs', TEST_IMAGE_HASH))
    with mock.patch.object(db.cursor, 'execute') as mock_execute:
      db.delete_filesystem_database(db_name)
      mock_execute.assert_called_once_with(
          'DROP DATABASE {0:s}'.format(db_name))

  def test_execute(self):
    """Test execute method."""
    db = self._get_datastore()
    command = (
        'CREATE TABLE images (image_path TEXT, image_hash TEXT PRIMARY KEY)')
    with mock.patch.object(db.cursor, 'execute') as mock_execute:
      db._execute(command)
      mock_execute.assert_called_once_with(command)

  def test_get_case_images(self):
    """Test get case images method."""
    db = self._get_datastore()
    with mock.patch.object(db.cursor, 'fetchall',
                           return_value=[(TEST_IMAGE_HASH, TEST_IMAGE)]):
      images = db.get_case_images(TEST_CASE)
      self.assertEqual(images, {TEST_IMAGE_HASH: TEST_IMAGE})

  def test_get_filenames_from_inode(self):
    """Test get filenames from inode method."""
    db = self._get_datastore()
    with mock.patch.object(db.cursor, 'fetchall',
                           return_value=[('test.txt',), ('test.txt:ads',)]):
      filenames = db.get_filenames_from_inode(42, '/p1')
      self.assertEqual(len(filenames), 2)
      self.assertEqual(filenames[0], 'test.txt')
      self.assertEqual(filenames[1], 'test.txt:ads')

  def test_get_image_hash(self):
    """Test get image hash method."""
    db = self._get_datastore()
    with mock.patch.object(db.cursor, 'fetchone',
                           return_value=(TEST_IMAGE_HASH,)):
      image_hash = db.get_image_hash(TEST_IMAGE_ID)
      self.assertEqual(image_hash, TEST_IMAGE_HASH)

  def test_get_inodes(self):
    """Test get inodes method."""
    db = self._get_datastore()
    with mock.patch.object(db.cursor, 'fetchall', return_value=[(10,), (19,)]):
      inodes = db.get_inodes(1234, '/p1')
      self.assertEqual(inodes, [10, 19])

  @mock.patch('psycopg2.connect')
  def test_init(self, mock_connect):
    """Test init method."""
    mock_connect.side_effect = OperationalError
    with self.assertRaises(RuntimeError):
      db = PostgresqlDataStore()

  def test_initialise_database(self):
    """Test initialise database method."""
    db = self._get_datastore()
    calls = [
        mock.call(
            'CREATE TABLE images (image_id TEXT PRIMARY KEY, image_path TEXT, image_hash TEXT)'
        ),
        mock.call((
            'CREATE TABLE image_case ('
            'case_id TEXT, image_id TEXT REFERENCES images(image_id), '
            'PRIMARY KEY (case_id, image_id))'))
    ]
    with mock.patch.object(db.cursor, 'execute') as mock_execute:
      db.initialise_database()
      mock_execute.assert_has_calls(calls)

  def test_insert_image(self):
    """Test insert image method."""
    db = self._get_datastore()
    with mock.patch.object(db.cursor, 'execute') as mock_execute:
      db.insert_image(TEST_IMAGE_ID, TEST_IMAGE, TEST_IMAGE_HASH)
      mock_execute.assert_called_once_with((
          'INSERT INTO images (image_id, image_path, image_hash) '
          'VALUES (\'{0:s}\', \'{1:s}\', \'{2:s}\')').format(
              TEST_IMAGE_ID, TEST_IMAGE, TEST_IMAGE_HASH))

  def test_is_image_in_case(self):
    """Test is image in case method."""
    db = self._get_datastore()
    with mock.patch.object(db.cursor, 'fetchone', return_value=(1,)):
      result = db.is_image_in_case(TEST_IMAGE_ID, TEST_CASE)
      self.assertTrue(result)
    with mock.patch.object(db.cursor, 'fetchone', return_value=None):
      result = db.is_image_in_case(TEST_IMAGE_ID, TEST_CASE)
      self.assertFalse(result)

  def test_link_image_to_case(self):
    """Test link image to case method."""
    db = self._get_datastore()
    with mock.patch.object(db.cursor, 'execute') as mock_execute:
      db.link_image_to_case(TEST_IMAGE_ID, TEST_CASE)
      mock_execute.assert_called_once_with((
          'INSERT INTO image_case (case_id, image_id) '
          'VALUES (\'{0:s}\', \'{1:s}\')').format(TEST_CASE, TEST_IMAGE_ID))

  def test_query(self):
    """Test query method."""
    db = self._get_datastore()
    query = 'SELECT filename FROM files WHERE inum = 0'
    with mock.patch.object(db.cursor, 'fetchall', return_value=[('$MFT',)]):
      results = db._query(query)

    self.assertEqual(results, [('$MFT',)])

  def test_query_single_row(self):
    """Test query single row method."""
    db = self._get_datastore()
    query = (
        'SELECT 1 from image_case WHERE image_hash = '
        '\'d41d8cd98f00b204e9800998ecf8427e\'')
    with mock.patch.object(db.cursor, 'fetchone', return_value=(1,)):
      results = db._query_single_row(query)

    self.assertEqual(results, (1,))

  def test_switch_database(self):
    """Test switch database method."""
    db = self._get_datastore()
    with mock.patch('psycopg2.connect') as mock_connect:
      db.switch_database(db_name='dfdewey', autocommit=True)
      mock_connect.assert_called_once_with(
          database='dfdewey', user='dfdewey', password='password',
          host='127.0.0.1', port=5432)

  def test_table_exists(self):
    """Test table exists method."""
    db = self._get_datastore()

    with mock.patch.object(db.cursor, 'fetchone', return_value=(1,)):
      result = db.table_exists('images')
    self.assertEqual(result, True)

    with mock.patch.object(db.cursor, 'fetchone', return_value=None):
      result = db.table_exists('images')
    self.assertEqual(result, False)

  def test_value_exists(self):
    """Test value exists method."""
    db = self._get_datastore()

    with mock.patch.object(db.cursor, 'fetchone', return_value=(1,)):
      result = db.value_exists(
          'images', 'image_hash', 'd41d8cd98f00b204e9800998ecf8427e')
    self.assertEqual(result, True)

    with mock.patch.object(db.cursor, 'fetchone', return_value=None):
      result = db.value_exists(
          'images', 'image_hash', 'd41d8cd98f00b204e9800998ecf8427e')
    self.assertEqual(result, False)


if __name__ == '__main__':
  unittest.main()
