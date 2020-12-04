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

import os
from subprocess import CalledProcessError
import unittest

from dfvfs.lib import definitions as dfvfs_definitions
from dfvfs.path import factory as path_spec_factory
import mock

from dfdewey.utils.image_processor import (
    _StringRecord, FileEntryScanner, ImageProcessor, ImageProcessorOptions,
    UnattendedVolumeScannerMediator)

TEST_CASE = 'testcase'
TEST_IMAGE = 'test.dd'
TEST_IMAGE_HASH = 'd41d8cd98f00b204e9800998ecf8427e'


class FileEntryScannerTest(unittest.TestCase):
  """Tests for file entry scanner."""

  def _get_file_entry_scanner(self):
    """Get a test file entry scanner.

    Returns:
      Test file entry scanner.
    """
    mediator = UnattendedVolumeScannerMediator()
    scanner = FileEntryScanner(mediator=mediator)
    return scanner

  @mock.patch('dfdewey.datastore.postgresql.PostgresqlDataStore')
  def test_parse_file_entries(self, mock_datastore):
    """Test parse file entries method."""
    scanner = self._get_file_entry_scanner()
    current_path = os.path.abspath(os.path.dirname(__file__))
    image_path = os.path.join(
        current_path, '..', '..', 'test_data', 'test_volume.dd')
    path_specs = scanner.GetBasePathSpecs(image_path)
    scanner.parse_file_entries(path_specs, mock_datastore)
    self.assertEqual(mock_datastore.bulk_insert.call_count, 2)
    insert_calls = mock_datastore.bulk_insert.mock_calls
    self.assertEqual(len(insert_calls[0].args[1]), 1500)
    self.assertEqual(len(insert_calls[1].args[1]), 3)

    # Test APFS
    mock_datastore.reset_mock()
    scanner = self._get_file_entry_scanner()
    image_path = os.path.join(current_path, '..', '..', 'test_data', 'test.dmg')
    path_specs = scanner.GetBasePathSpecs(image_path)
    self.assertEqual(getattr(path_specs[0].parent, 'location', None), '/apfs1')
    scanner.parse_file_entries(path_specs, mock_datastore)
    mock_datastore.bulk_insert.assert_not_called()


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
    return image_processor

  @mock.patch(
      'dfdewey.utils.image_processor.ImageProcessor._initialise_database')
  @mock.patch('dfdewey.datastore.postgresql.PostgresqlDataStore')
  def test_already_parsed(self, mock_postgresql, mock_initialise_database):
    """Test already parsed method."""
    image_processor = self._get_image_processor()

    # Test if new database
    mock_postgresql.table_exists.return_value = False
    image_processor.postgresql = mock_postgresql
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
    mock_postgresql.execute.assert_has_calls(calls)
    self.assertEqual(result, False)

    # Test database exists, image already in case
    mock_postgresql.table_exists.return_value = True
    mock_postgresql.value_exists.return_value = True
    mock_postgresql.query_single_row.return_value = (1,)
    mock_postgresql.execute.reset_mock()

    image_processor.postgresql = mock_postgresql
    result = image_processor._already_parsed()
    mock_postgresql.execute.assert_not_called()
    self.assertEqual(result, True)

    # Test database exists, image exists, but not in case
    mock_postgresql.query_single_row.return_value = None
    image_processor.postgresql = mock_postgresql
    result = image_processor._already_parsed()
    mock_postgresql.execute.assert_called_once_with((
        'INSERT INTO image_case (case_id, image_hash) '
        'VALUES (\'{0:s}\', \'{1:s}\')').format(TEST_CASE, TEST_IMAGE_HASH))
    self.assertEqual(result, True)

  @mock.patch('dfdewey.datastore.postgresql.PostgresqlDataStore')
  def test_create_filesystem_database(self, mock_postgresql):
    """Test create filesystem database method."""
    image_processor = self._get_image_processor()
    image_processor.postgresql = mock_postgresql
    image_processor._create_filesystem_database()

    calls = [
        mock.call((
            'CREATE TABLE blocks (block INTEGER, inum INTEGER, part TEXT, '
            'PRIMARY KEY (block, inum, part))')),
        mock.call((
            'CREATE TABLE files (inum INTEGER, filename TEXT, part TEXT, '
            'PRIMARY KEY (inum, filename, part))'))
    ]
    mock_postgresql.execute.assert_has_calls(calls)

  @mock.patch('subprocess.check_output')
  def test_extract_strings(self, mock_subprocess):
    """Test extract strings method."""
    image_processor = self._get_image_processor()
    image_processor.output_path = '/tmp/tmpxaemz75r'
    image_processor.image_hash = None

    # Test with default options
    mock_subprocess.return_value = 'MD5 of Disk Image: {0:s}'.format(
        TEST_IMAGE_HASH).encode('utf-8')
    image_processor._extract_strings()
    mock_subprocess.assert_called_once_with([
        'bulk_extractor', '-o', '/tmp/tmpxaemz75r', '-x', 'all', '-e',
        'wordlist', '-e', 'base64', '-e', 'gzip', '-e', 'zip', '-S',
        'strings=YES', '-S', 'word_max=1000000', TEST_IMAGE
    ])
    self.assertEqual(image_processor.image_hash, TEST_IMAGE_HASH)

    # Test options
    mock_subprocess.reset_mock()
    mock_subprocess.return_value = 'MD5 of Disk Image: {0:s}'.format(
        TEST_IMAGE_HASH).encode('utf-8')
    image_processor.options.base64 = False
    image_processor.options.gunzip = False
    image_processor.options.unzip = False
    image_processor._extract_strings()
    mock_subprocess.assert_called_once_with([
        'bulk_extractor', '-o', '/tmp/tmpxaemz75r', '-x', 'all', '-e',
        'wordlist', '-S', 'strings=YES', '-S', 'word_max=1000000', TEST_IMAGE
    ])

    # Test error in processing
    mock_subprocess.reset_mock()
    mock_subprocess.side_effect = CalledProcessError(1, 'bulk_extractor')
    with self.assertRaises(RuntimeError):
      image_processor._extract_strings()

  def test_get_volume_details(self):
    """Test get volume details method."""
    image_processor = self._get_image_processor()

    os_path_spec = path_spec_factory.Factory.NewPathSpec(
        dfvfs_definitions.TYPE_INDICATOR_OS, location=TEST_IMAGE)
    raw_path_spec = path_spec_factory.Factory.NewPathSpec(
        dfvfs_definitions.TYPE_INDICATOR_RAW, parent=os_path_spec)
    tsk_partition_spec = path_spec_factory.Factory.NewPathSpec(
        dfvfs_definitions.TYPE_INDICATOR_TSK_PARTITION, parent=raw_path_spec,
        location='/p1', part_index=2, start_offset=2048)
    tsk_spec = path_spec_factory.Factory.NewPathSpec(
        dfvfs_definitions.TYPE_INDICATOR_NTFS, parent=tsk_partition_spec,
        location='/')

    location, start_offset = image_processor._get_volume_details(tsk_spec)

    self.assertEqual(location, '/p1')
    self.assertEqual(start_offset, 2048)

  @mock.patch('dfdewey.datastore.elastic.ElasticsearchDataStore')
  def test_index_record(self, mock_elasticsearch):
    """Test index record method."""
    image_processor = self._get_image_processor()

    index_name = ''.join(('es', TEST_IMAGE_HASH))
    string_record = _StringRecord()
    string_record.image = TEST_IMAGE_HASH
    string_record.offset = 1234567
    string_record.data = 'test string'

    image_processor.elasticsearch = mock_elasticsearch
    image_processor._index_record(index_name, string_record)

    json_record = {
        'image': string_record.image,
        'offset': string_record.offset,
        'file_offset': string_record.file_offset,
        'data': string_record.data
    }
    mock_elasticsearch.import_event.assert_called_once_with(
        index_name, event=json_record)

  @mock.patch('elasticsearch.client.IndicesClient.create')
  @mock.patch('dfdewey.utils.image_processor.ImageProcessor._index_record')
  @mock.patch('dfdewey.datastore.elastic.ElasticsearchDataStore.index_exists')
  @mock.patch('dfdewey.datastore.elastic.ElasticsearchDataStore.import_event')
  @mock.patch('dfdewey.datastore.elastic.ElasticsearchDataStore.create_index')
  def test_index_strings(
      self, mock_create_index, mock_import_event, mock_index_exists,
      mock_index_record, _):
    """Test index strings method."""
    image_processor = self._get_image_processor()
    current_path = os.path.abspath(os.path.dirname(__file__))
    image_processor.output_path = os.path.join(
        current_path, '..', '..', 'test_data')

    # Test index already exists
    mock_index_exists.return_value = True
    image_processor._index_strings()
    mock_index_record.assert_not_called()

    # Test new index
    mock_index_exists.return_value = False
    mock_index_record.return_value = 10000000
    image_processor._index_strings()
    mock_create_index.assert_called_once_with(
        index_name=''.join(('es', TEST_IMAGE_HASH)))
    self.assertEqual(mock_index_record.call_count, 3)
    mock_import_event.assert_called_once()

  @mock.patch('psycopg2.connect')
  @mock.patch('dfdewey.utils.image_processor.ImageProcessor._already_parsed')
  @mock.patch(
      'dfdewey.datastore.postgresql.PostgresqlDataStore.switch_database')
  @mock.patch('dfdewey.datastore.postgresql.PostgresqlDataStore.execute')
  @mock.patch('dfdewey.datastore.postgresql.PostgresqlDataStore.bulk_insert')
  def test_parse_filesystems(
      self, mock_bulk_insert, mock_execute, mock_switch_database,
      mock_already_parsed, _):
    """Test parse filesystems method."""
    image_processor = self._get_image_processor()

    # Test image already parsed
    mock_already_parsed.return_value = True
    image_processor._parse_filesystems()
    mock_execute.assert_not_called()

    # Test image not parsed
    current_path = os.path.abspath(os.path.dirname(__file__))
    image_processor.image_path = os.path.join(
        current_path, '..', '..', 'test_data', 'test.dd')
    mock_already_parsed.return_value = False
    image_processor._parse_filesystems()
    self.assertEqual(mock_execute.call_count, 3)
    mock_switch_database.assert_called_once_with(
        db_name=''.join(('fs', TEST_IMAGE_HASH)))
    self.assertIsInstance(image_processor.scanner, FileEntryScanner)
    self.assertEqual(len(image_processor.path_specs), 2)
    ntfs_path_spec = image_processor.path_specs[0]
    tsk_path_spec = image_processor.path_specs[1]
    self.assertEqual(
        ntfs_path_spec.type_indicator, dfvfs_definitions.TYPE_INDICATOR_NTFS)
    self.assertEqual(
        tsk_path_spec.type_indicator, dfvfs_definitions.TYPE_INDICATOR_TSK)
    self.assertEqual(mock_bulk_insert.call_count, 48)
    # Check number of blocks inserted for p1
    self.assertEqual(len(mock_bulk_insert.mock_calls[0].args[1]), 639)
    # Check number of files inserted for p1
    self.assertEqual(len(mock_bulk_insert.mock_calls[1].args[1]), 21)
    # Check number of blocks inserted for p3
    for mock_call in mock_bulk_insert.mock_calls[2:46]:
      self.assertEqual(len(mock_call.args[1]), 1500)
    self.assertEqual(len(mock_bulk_insert.mock_calls[46].args[1]), 1113)
    # Check number of files inserted for p3
    self.assertEqual(len(mock_bulk_insert.mock_calls[47].args[1]), 4)

    # Test missing image
    image_processor.image_path = TEST_IMAGE
    image_processor.path_specs = []
    image_processor._parse_filesystems()

    # Test unsupported volume
    image_processor.image_path = os.path.join(
        current_path, '..', '..', 'test_data', 'test.dmg')
    image_processor._parse_filesystems()

  @mock.patch('dfdewey.utils.image_processor.ImageProcessor._parse_filesystems')
  @mock.patch('dfdewey.utils.image_processor.ImageProcessor._index_strings')
  @mock.patch('dfdewey.utils.image_processor.ImageProcessor._extract_strings')
  def test_process_image(
      self, mock_extract_strings, mock_index_strings, mock_parse_filesystems):
    """Test process image method."""
    image_processor = self._get_image_processor()
    image_processor.process_image()
    mock_extract_strings.assert_called_once()
    mock_index_strings.assert_called_once()
    mock_parse_filesystems.assert_called_once()


if __name__ == '__main__':
  unittest.main()
