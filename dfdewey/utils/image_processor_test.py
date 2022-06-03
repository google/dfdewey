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

from dfvfs.helpers import volume_scanner
from dfvfs.lib import definitions as dfvfs_definitions
from dfvfs.path import factory as path_spec_factory
import mock

from dfdewey.utils.image_processor import (
    _StringRecord, FileEntryScanner, ImageProcessor, ImageProcessorOptions)

TEST_CASE = 'testcase'
TEST_IMAGE = 'test.dd'
TEST_IMAGE_HASH = 'd41d8cd98f00b204e9800998ecf8427e'
TEST_IMAGE_ID = 'd41d8cd98f00b204e9800998ecf8427e'


class FileEntryScannerTest(unittest.TestCase):
  """Tests for file entry scanner."""

  @mock.patch('dfdewey.datastore.postgresql.PostgresqlDataStore')
  def test_parse_file_entries(self, mock_datastore):
    """Test parse file entries method."""
    options = volume_scanner.VolumeScannerOptions()
    options.partitions = ['all']
    options.volumes = ['all']
    options.snapshots = ['none']
    scanner = FileEntryScanner()
    current_path = os.path.abspath(os.path.dirname(__file__))
    image_path = os.path.join(
        current_path, '..', '..', 'test_data', 'test_volume.dd')
    path_specs = scanner.GetBasePathSpecs(image_path, options=options)
    scanner.parse_file_entries(path_specs, mock_datastore)
    self.assertEqual(mock_datastore.bulk_insert.call_count, 2)
    insert_calls = mock_datastore.bulk_insert.mock_calls
    self.assertEqual(len(insert_calls[0].args[1]), 1500)
    self.assertEqual(len(insert_calls[1].args[1]), 2)

    # Test APFS
    mock_datastore.reset_mock()
    scanner = FileEntryScanner()
    image_path = os.path.join(current_path, '..', '..', 'test_data', 'test.dmg')
    path_specs = scanner.GetBasePathSpecs(image_path, options=options)
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
        TEST_CASE, TEST_IMAGE_ID, TEST_IMAGE, image_processor_options)
    image_processor.config = None
    image_processor.image_hash = TEST_IMAGE_HASH
    return image_processor

  @mock.patch('dfdewey.datastore.postgresql.PostgresqlDataStore')
  def test_already_parsed(self, mock_postgresql):
    """Test already parsed method."""
    image_processor = self._get_image_processor()

    # Test if new database
    mock_postgresql.table_exists.return_value = False
    image_processor.postgresql = mock_postgresql
    result = image_processor._already_parsed()

    mock_postgresql.initialise_database.assert_called_once()
    mock_postgresql.insert_image.assert_called_once_with(
        TEST_IMAGE_ID, TEST_IMAGE, TEST_IMAGE_HASH)
    mock_postgresql.link_image_to_case.assert_called_once_with(
        TEST_IMAGE_ID, TEST_CASE)
    self.assertEqual(result, False)

    # Test database exists, image already in case
    mock_postgresql.table_exists.return_value = True
    mock_postgresql.value_exists.return_value = True
    mock_postgresql.is_image_in_case.return_value = True
    mock_postgresql.link_image_to_case.reset_mock()

    image_processor.postgresql = mock_postgresql
    result = image_processor._already_parsed()
    mock_postgresql.link_image_to_case.assert_not_called()
    self.assertEqual(result, True)

    # Test database exists, image exists, but not in case
    mock_postgresql.is_image_in_case.return_value = False
    image_processor.postgresql = mock_postgresql
    result = image_processor._already_parsed()
    mock_postgresql.link_image_to_case.assert_called_once_with(
        TEST_IMAGE_ID, TEST_CASE)
    self.assertEqual(result, True)

  @mock.patch(
      'dfdewey.utils.image_processor.ImageProcessor._connect_opensearch_datastore'
  )
  @mock.patch(
      'dfdewey.utils.image_processor.ImageProcessor._connect_postgresql_datastore'
  )
  @mock.patch('dfdewey.datastore.opensearch.OpenSearchDataStore')
  @mock.patch('dfdewey.datastore.postgresql.PostgresqlDataStore')
  def test_delete_image_data(
      self, mock_postgresql, mock_opensearch, mock_connect_postgres,
      mock_connect_opensearch):
    """Test delete image data method."""
    image_processor = self._get_image_processor()
    image_processor.postgresql = mock_postgresql
    image_processor.opensearch = mock_opensearch
    # Test if image is not in case
    mock_postgresql.is_image_in_case.return_value = False
    image_processor._delete_image_data()
    mock_connect_postgres.assert_called_once()
    mock_postgresql.unlink_image_from_case.assert_not_called()

    # Test if image is linked to multiple cases
    mock_postgresql.is_image_in_case.return_value = True
    mock_postgresql.get_image_cases.return_value = ['test']
    image_processor._delete_image_data()
    mock_postgresql.get_image_cases.assert_called_once()
    mock_connect_opensearch.assert_not_called()

    # Test if index exists
    mock_postgresql.get_image_cases.return_value = None
    mock_opensearch.index_exists.return_value = True
    image_processor._delete_image_data()
    mock_opensearch.delete_index.assert_called_once()
    mock_postgresql.delete_filesystem_database.assert_called_once()
    mock_postgresql.delete_image.assert_called_once()

    # Test if index doesn't exist
    mock_opensearch.delete_index.reset_mock()
    mock_opensearch.index_exists.return_value = False
    image_processor._delete_image_data()
    mock_opensearch.delete_index.assert_not_called()

  @mock.patch('tempfile.mkdtemp')
  @mock.patch('subprocess.check_call')
  def test_extract_strings(self, mock_subprocess, mock_mkdtemp):
    """Test extract strings method."""
    image_processor = self._get_image_processor()
    mock_mkdtemp.return_value = '/tmp/tmpxaemz75r'

    # Test with default options
    image_processor._extract_strings()
    mock_subprocess.assert_called_once_with([
        'bulk_extractor', '-o', '/tmp/tmpxaemz75r', '-x', 'all', '-e',
        'wordlist', '-e', 'base64', '-e', 'gzip', '-e', 'zip', '-S',
        'strings=YES', '-S', 'word_max=1000000', TEST_IMAGE
    ])

    # Test options
    mock_subprocess.reset_mock()
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

    current_path = os.path.abspath(os.path.dirname(__file__))
    image_path = os.path.join(current_path, '..', '..', 'test_data', TEST_IMAGE)

    os_path_spec = path_spec_factory.Factory.NewPathSpec(
        dfvfs_definitions.TYPE_INDICATOR_OS, location=image_path)
    raw_path_spec = path_spec_factory.Factory.NewPathSpec(
        dfvfs_definitions.TYPE_INDICATOR_RAW, parent=os_path_spec)
    tsk_partition_spec = path_spec_factory.Factory.NewPathSpec(
        dfvfs_definitions.TYPE_INDICATOR_TSK_PARTITION, parent=raw_path_spec,
        location='/p1', start_offset=1048576)
    tsk_spec = path_spec_factory.Factory.NewPathSpec(
        dfvfs_definitions.TYPE_INDICATOR_NTFS, parent=tsk_partition_spec,
        location='/')

    location, start_offset = image_processor._get_volume_details(tsk_spec)

    self.assertEqual(location, '/p1')
    self.assertEqual(start_offset, 1048576)

  @mock.patch('dfdewey.datastore.opensearch.OpenSearchDataStore')
  def test_index_record(self, mock_opensearch):
    """Test index record method."""
    image_processor = self._get_image_processor()

    index_name = ''.join(('es', TEST_IMAGE_HASH))
    string_record = _StringRecord()
    string_record.image = TEST_IMAGE_HASH
    string_record.offset = 1234567
    string_record.data = 'test string'

    image_processor.opensearch = mock_opensearch
    image_processor._index_record(index_name, string_record)

    json_record = {
        'image': string_record.image,
        'offset': string_record.offset,
        'file_offset': string_record.file_offset,
        'data': string_record.data
    }
    mock_opensearch.import_event.assert_called_once_with(
        index_name, event=json_record)

  @mock.patch('opensearchpy.client.IndicesClient')
  @mock.patch('dfdewey.utils.image_processor.ImageProcessor._index_record')
  @mock.patch('dfdewey.datastore.opensearch.OpenSearchDataStore.index_exists')
  @mock.patch('dfdewey.datastore.opensearch.OpenSearchDataStore.import_event')
  @mock.patch('dfdewey.datastore.opensearch.OpenSearchDataStore.create_index')
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

    # Test reindex flag
    image_processor.options.reindex = True
    image_processor._index_strings()
    mock_create_index.assert_called_once_with(
        index_name=''.join(('es', TEST_IMAGE_HASH)))
    self.assertEqual(mock_index_record.call_count, 3)
    mock_import_event.assert_called_once()
    image_processor.options.reindex = False
    mock_create_index.reset_mock()
    mock_index_record.reset_mock()
    mock_import_event.reset_mock()

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
  @mock.patch('dfdewey.datastore.postgresql.PostgresqlDataStore._execute')
  @mock.patch('dfdewey.datastore.postgresql.PostgresqlDataStore.bulk_insert')
  def test_parse_filesystems(
      self, mock_bulk_insert, mock_execute, mock_switch_database,
      mock_already_parsed, _):
    """Test parse filesystems method."""
    db_name = ''.join(('fs', TEST_IMAGE_HASH))
    image_processor = self._get_image_processor()

    # Test image already parsed
    mock_already_parsed.return_value = True
    image_processor._parse_filesystems()
    mock_execute.assert_not_called()

    # Test reparse flag
    image_processor.options.reparse = True
    image_processor._parse_filesystems()
    mock_execute.assert_any_call('DROP DATABASE {0:s}'.format(db_name))
    mock_execute.reset_mock()
    mock_switch_database.reset_mock()

    # Test image not parsed
    current_path = os.path.abspath(os.path.dirname(__file__))
    image_processor.image_path = os.path.join(
        current_path, '..', '..', 'test_data', 'test.dd')
    mock_already_parsed.return_value = False
    image_processor._parse_filesystems()
    self.assertEqual(mock_execute.call_count, 3)
    mock_switch_database.assert_called_once_with(db_name=db_name)
    self.assertIsInstance(image_processor.scanner, FileEntryScanner)
    self.assertEqual(len(image_processor.path_specs), 2)
    ntfs_path_spec = image_processor.path_specs[0]
    tsk_path_spec = image_processor.path_specs[1]
    self.assertEqual(
        ntfs_path_spec.type_indicator, dfvfs_definitions.TYPE_INDICATOR_NTFS)
    self.assertEqual(
        tsk_path_spec.type_indicator, dfvfs_definitions.TYPE_INDICATOR_EXT)
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
    self.assertEqual(len(mock_bulk_insert.mock_calls[47].args[1]), 3)

    # Test missing image
    image_processor.image_path = TEST_IMAGE
    image_processor.path_specs = []
    image_processor._parse_filesystems()

    # Test unsupported volume
    image_processor.image_path = os.path.join(
        current_path, '..', '..', 'test_data', 'test.dmg')
    image_processor._parse_filesystems()

  @mock.patch('dfdewey.utils.image_processor.ImageProcessor._delete_image_data')
  @mock.patch('dfdewey.utils.image_processor.ImageProcessor._parse_filesystems')
  @mock.patch('dfdewey.utils.image_processor.ImageProcessor._index_strings')
  @mock.patch('dfdewey.utils.image_processor.ImageProcessor._extract_strings')
  def test_process_image(
      self, mock_extract_strings, mock_index_strings, mock_parse_filesystems,
      mock_delete_image_data):
    """Test process image method."""
    image_processor = self._get_image_processor()
    image_processor.process_image()
    mock_extract_strings.assert_called_once()
    mock_index_strings.assert_called_once()
    mock_parse_filesystems.assert_called_once()
    mock_delete_image_data.assert_not_called()


if __name__ == '__main__':
  unittest.main()
