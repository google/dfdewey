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
"""Image processor."""

from datetime import datetime
import logging
import os
import subprocess
import tempfile

from dfvfs.helpers import volume_scanner
from dfvfs.lib import definitions as dfvfs_definitions
from dfvfs.lib import errors as dfvfs_errors
from dfvfs.resolver import resolver
from dfvfs.volume import tsk_volume_system
import pytsk3

from dfdewey.datastore.elastic import ElasticsearchDataStore
from dfdewey.datastore.postgresql import PostgresqlDataStore

BATCH_SIZE = 1500
STRING_INDEXING_LOG_INTERVAL = 10000000

log = logging.getLogger('dfdewey.image_processor')


class _StringRecord():
  """Elasticsearch string record.

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


class FileEntryScanner(volume_scanner.VolumeScanner):
  """File entry scanner."""

  _NON_PRINTABLE_CHARACTERS = list(range(0, 0x20)) + list(range(0x7f, 0xa0))
  _ESCAPE_CHARACTERS = str.maketrans({
      value: '\\x{0:02x}'.format(value) for value in _NON_PRINTABLE_CHARACTERS
  })

  def __init__(self, mediator=None):
    """Initializes a file entry scanner.

    Args:
      mediator (VolumeScannerMediator): a volume scanner mediator.
    """
    super().__init__(mediator=mediator)
    self._datastore = None
    self._list_only_files = False
    self._rows = []
    self._volumes = {}

  def _get_display_path(self, path_spec, path_segments, data_stream_name):
    """Retrieves a path to display.

    Args:
      path_spec (dfvfs.PathSpec): path specification of the file entry.
      path_segments (list[str]): path segments of the full path of the file
          entry.
      data_stream_name (str): name of the data stream.

    Returns:
      str: path to display.
    """
    display_path = ''

    if path_spec.HasParent():
      parent_path_spec = path_spec.parent
      if parent_path_spec and parent_path_spec.type_indicator == (
          dfvfs_definitions.TYPE_INDICATOR_TSK_PARTITION):
        display_path = ''.join([display_path, parent_path_spec.location])

    path_segments = [
        segment.translate(self._ESCAPE_CHARACTERS) for segment in path_segments
    ]
    display_path = ''.join([display_path, '/'.join(path_segments)])

    if data_stream_name:
      data_stream_name = data_stream_name.translate(self._ESCAPE_CHARACTERS)
      display_path = ':'.join([display_path, data_stream_name])

    return display_path or '/'

  def _get_inode(self, path_spec):
    """Gets the inode from a file entry path spec.

    Args:
      path_spec (dfvfs.PathSpec): file entry path spec.
    """
    inode = None
    if path_spec.type_indicator == dfvfs_definitions.TYPE_INDICATOR_NTFS:
      inode = getattr(path_spec, 'mft_entry', None)
    else:
      inode = getattr(path_spec, 'inode', None)
    return inode

  def _get_tsk_partition_path_spec(self, path_spec):
    """Gets the path spec for the TSK partition.

    Args:
      path_spec (dfvfs.PathSpec): path spec of the volume.

    Returns:
      TSK partition path_spec or None.
    """
    partition_path_spec = None
    while path_spec.HasParent():
      type_indicator = path_spec.type_indicator
      if type_indicator == dfvfs_definitions.TYPE_INDICATOR_TSK_PARTITION:
        partition_path_spec = path_spec
        break
      path_spec = path_spec.parent
    return partition_path_spec

  def _get_volume_location(self, path_spec):
    """Gets volume location / identifier for the given path spec.

    Args:
      path_spec (dfvfs.PathSpec): path spec of the volume.

    Returns:
      Volume location / identifier.
    """
    location = getattr(path_spec, 'location', None)
    while path_spec.HasParent():
      type_indicator = path_spec.type_indicator
      if type_indicator == dfvfs_definitions.TYPE_INDICATOR_TSK_PARTITION:
        if location in ('\\', '/'):
          location = getattr(path_spec, 'location', None)
        break
      path_spec = path_spec.parent
    return location

  def _list_file_entry(
      self, file_system, file_entry, parent_path_segments, location):
    """Lists a file entry.

    Args:
      file_system (dfvfs.FileSystem): file system that contains the file entry.
      file_entry (dfvfs.FileEntry): file entry to list.
      parent_path_segments (str): path segments of the full path of the parent
          file entry.
      location (str): volume location / identifier.
    """
    path_segments = parent_path_segments + [file_entry.name]

    inode = self._get_inode(file_entry.path_spec)
    filename = self._get_display_path(file_entry.path_spec, path_segments, '')
    if not self._list_only_files or file_entry.IsFile():
      if inode is not None:
        self._rows.append((
            inode,
            filename,
            location,
        ))
        for data_stream in file_entry.data_streams:
          if not data_stream.IsDefault():
            filename = self._get_display_path(
                file_entry.path_spec, path_segments, data_stream.name)
            self._rows.append((
                inode,
                filename,
                location,
            ))
        if len(self._rows) >= BATCH_SIZE:
          self._datastore.bulk_insert(
              'files (inum, filename, part)', self._rows)
          self._rows = []

    for sub_file_entry in file_entry.sub_file_entries:
      self._list_file_entry(
          file_system, sub_file_entry, path_segments, location)

  def get_volume_extents(self, image_path):
    """Gets the extents of all volumes.

    Args:
      image_path (str): path of the source image.

    Returns:
      Volume location / identifier, offset, and size for all volumes.
    """
    if not self._volumes or self._source_path != image_path:
      base_path_specs = self.GetBasePathSpecs(image_path)

      for path_spec in base_path_specs:
        partition_path_spec = self._get_tsk_partition_path_spec(path_spec)
        if not partition_path_spec:
          location = getattr(path_spec, 'location', None)
          self._volumes[location] = {'start': 0, 'end': None}
        else:
          location = getattr(partition_path_spec, 'location', None)
          partition_offset = None
          partition_size = None

          volume_system = tsk_volume_system.TSKVolumeSystem()
          try:
            volume_system.Open(partition_path_spec)
            volume_identifier = location.replace('/', '')
            volume = volume_system.GetVolumeByIdentifier(volume_identifier)

            partition_offset = volume.extents[0].offset
            partition_size = volume.extents[0].size
          except dfvfs_errors.VolumeSystemError as e:
            log.error('Could not process partition: %s', e)

          self._volumes[location] = {
              'start': partition_offset,
              'end': partition_offset + partition_size
          }

    return self._volumes

  def parse_file_entries(self, base_path_specs, datastore):
    """Parses file entries in the base path specification.

    Stores parsed entries in the PostgreSQL datastore.

    Args:
      base_path_specs (list[dfvfs.PathSpec]): source path specification.
      datastore (PostgresqlDataStore): PostgreSQL datastore.
    """
    self._datastore = datastore
    for base_path_spec in base_path_specs:
      file_system = resolver.Resolver.OpenFileSystem(base_path_spec)
      file_entry = resolver.Resolver.OpenFileEntry(base_path_spec)
      if file_entry is None:
        log.warning(
            'Unable to open base path specification: %s',
            base_path_spec.comparable)
        return

      location = self._get_volume_location(base_path_spec)
      self._list_file_entry(file_system, file_entry, [], location)
    if self._rows:
      self._datastore.bulk_insert('files (inum, filename, part)', self._rows)
      self._rows = []


class ImageProcessor():
  """Image processor class.

  Attributes:
    case (str): case ID.
    elasticsearch (ElasticsearchDataStore): elasticsearch datastore.
    image_hash (str): MD5 hash of the image.
    image_path (str): path to source image.
    options (ImageProcessorOptions): image processor options.
    output_path (str): output directory for string extraction.
    path_specs (dfvfs.PathSpec): volume path specs.
    postgresql (PostgresqlDataStore): postgresql database.
    scanner (FileEntryScanner): dfvfs volume / file entry scanner.
  """

  def __init__(self, case, image_path, options):
    """Create an image processor."""
    super().__init__()
    self.case = case
    self.elasticsearch = None
    self.image_hash = None
    self.image_path = image_path
    self.options = options
    self.output_path = None
    self.path_specs = []
    self.postgresql = None
    self.scanner = None

  def _already_parsed(self):
    """Check if image is already parsed.

    Checks whether the image is already in the database.
    If so, checks whether it's attached to the case.
    Adds the image to the database and attaches it to the case.

    Returns:
      True if image has already been parsed, False if not.
    """
    tables_exist = self.postgresql.table_exists('images')

    image_exists = False
    if not tables_exist:
      self._initialise_database()
    else:
      image_exists = self.postgresql.value_exists(
          'images', 'image_hash', self.image_hash)

    # Even if the image has already been parsed, it may have been in a different
    # case.
    image_case_exists = False
    if image_exists:
      image_case = self.postgresql.query_single_row((
          'SELECT 1 from image_case '
          'WHERE image_hash = \'{0:s}\' AND case_id = \'{1:s}\'').format(
              self.image_hash, self.case))
      if image_case:
        image_case_exists = True
    else:
      self.postgresql.execute((
          'INSERT INTO images (image_path, image_hash) '
          'VALUES (\'{0:s}\', \'{1:s}\')').format(
              self.image_path, self.image_hash))

    if not image_case_exists:
      self.postgresql.execute((
          'INSERT INTO image_case (case_id, image_hash) '
          'VALUES (\'{0:s}\', \'{1:s}\')').format(self.case, self.image_hash))

    return image_exists

  def _create_filesystem_database(self):
    """Create a filesystem database for the image."""
    self.postgresql.execute((
        'CREATE TABLE blocks (block INTEGER, inum INTEGER, part TEXT, '
        'PRIMARY KEY (block, inum, part))'))
    self.postgresql.execute((
        'CREATE TABLE files (inum INTEGER, filename TEXT, part TEXT, '
        'PRIMARY KEY (inum, filename, part))'))

  def _extract_strings(self):
    """String extraction.

    Extract strings from the image using bulk_extractor.
    """
    cmd = [
        'bulk_extractor', '-o', self.output_path, '-x', 'all', '-e', 'wordlist'
    ]

    if self.options.base64:
      cmd.extend(['-e', 'base64'])
    if self.options.gunzip:
      cmd.extend(['-e', 'gzip'])
    if self.options.unzip:
      cmd.extend(['-e', 'zip'])

    cmd.extend(['-S', 'strings=YES', '-S', 'word_max=1000000'])
    cmd.append(self.image_path)

    log.info('Running bulk_extractor: [%s]', ' '.join(cmd))
    try:
      output = subprocess.check_output(cmd)
    except subprocess.CalledProcessError as e:
      raise RuntimeError('String extraction failed.') from e
    md5_offset = output.index(b'MD5') + 19
    self.image_hash = output[md5_offset:md5_offset + 32].decode('utf-8')

  def _get_volume_details(self, path_spec):
    """Logs volume details for the given path spec.

    Args:
      path_spec (dfvfs.PathSpec): path spec of the volume.

    Returns:
      Volume location / identifier and byte offset.
    """
    location = getattr(path_spec, 'location', None)
    start_offset = 0
    while path_spec.HasParent():
      type_indicator = path_spec.type_indicator
      if type_indicator == dfvfs_definitions.TYPE_INDICATOR_TSK_PARTITION:
        if location in ('\\', '/'):
          location = getattr(path_spec, 'location', None)
        start_offset = getattr(path_spec, 'start_offset', 0)
        break
      path_spec = path_spec.parent
    return location, start_offset

  def _index_record(self, index_name, string_record):
    """Index a single record.

    Args:
      index_name: ID of the elasticsearch index.
      string_record: String record to be indexed.

    Returns:
      Number of records processed
    """
    json_record = {
        'image': string_record.image,
        'offset': string_record.offset,
        'file_offset': string_record.file_offset,
        'data': string_record.data
    }
    return self.elasticsearch.import_event(index_name, event=json_record)

  def _index_strings(self):
    """Index the extracted strings."""
    self.elasticsearch = ElasticsearchDataStore()
    index_name = ''.join(('es', self.image_hash))
    index_exists = self.elasticsearch.index_exists(index_name)
    if index_exists:
      log.info('Image already indexed: [%s]', self.image_path)
      if self.options.reindex:
        log.info('Reindexing.')
        self.elasticsearch.delete_index(index_name)
        log.info('Index %s deleted.', index_name)
        index_exists = False
    if not index_exists:
      index_name = self.elasticsearch.create_index(index_name=index_name)
      log.info('Index %s created.', index_name)

      string_list = os.path.join(self.output_path, 'wordlist.txt')
      records = 0
      with open(string_list, 'r') as strings:
        for line in strings:
          # Ignore the comments added by bulk_extractor
          if not line.startswith('#'):
            string_record = _StringRecord()
            string_record.image = self.image_hash

            # Split each string into offset and data
            line = line.split('\t')
            offset = line[0]
            data = '\t'.join(line[1:])

            # If the string is from a decoded / decompressed stream, split the
            # offset into image offset and file offset
            if offset.find('-') > 0:
              offset = offset.split('-')
              image_offset = offset[0]
              file_offset = '-'.join(offset[1:])
              string_record.offset = int(image_offset)
              string_record.file_offset = file_offset
            else:
              string_record.offset = int(offset)

            string_record.data = data
            records = self._index_record(index_name, string_record)

            if records % STRING_INDEXING_LOG_INTERVAL == 0:
              log.info('Indexed %d records...', records)
      # Flush the import buffer
      records = self.elasticsearch.import_event(index_name)
      log.info('Indexed %d records...', records)

  def _initialise_database(self):
    """Initialse the image database."""
    self.postgresql.execute(
        'CREATE TABLE images (image_path TEXT, image_hash TEXT PRIMARY KEY)')

    self.postgresql.execute((
        'CREATE TABLE image_case ('
        'case_id TEXT, image_hash TEXT REFERENCES images(image_hash), '
        'PRIMARY KEY (case_id, image_hash))'))

  def _parse_filesystems(self):
    """Filesystem parsing.

    Parse each filesystem to create a mapping from byte offsets to files.
    """
    self.postgresql = PostgresqlDataStore(autocommit=True)
    if self._already_parsed():
      log.info('Image already parsed: [%s]', self.image_path)
    else:
      db_name = ''.join(('fs', self.image_hash))
      self.postgresql.execute('CREATE DATABASE {0:s}'.format(db_name))
      self.postgresql.switch_database(db_name=db_name)

      self._create_filesystem_database()

      # Scan image for volumes
      dfvfs_definitions.PREFERRED_GPT_BACK_END = (
          dfvfs_definitions.TYPE_INDICATOR_GPT)
      mediator = UnattendedVolumeScannerMediator()
      try:
        self.scanner = FileEntryScanner(mediator=mediator)
        self.path_specs = self.scanner.GetBasePathSpecs(self.image_path)
        log.info(
            'Found %d volume%s in [%s]:', len(self.path_specs),
            '' if len(self.path_specs) == 1 else 's', self.image_path)
      except dfvfs_errors.ScannerError as e:
        log.error('Error scanning for partitions: %s', e)

      for path_spec in self.path_specs:
        location, start_offset = self._get_volume_details(path_spec)
        log.info(
            '%s: %s (Offset %d)', location, path_spec.type_indicator,
            start_offset)
        if path_spec.type_indicator in (dfvfs_definitions.TYPE_INDICATOR_NTFS,
                                        dfvfs_definitions.TYPE_INDICATOR_TSK):
          self._parse_inodes(location, start_offset)
          self.scanner.parse_file_entries([path_spec], self.postgresql)
        else:
          log.warning(
              'Volume type %s is not supported.', path_spec.type_indicator)
      self.postgresql.db.commit()

  def _parse_inodes(self, location, start_offset):
    """Parse filesystem inodes.

    Create a mapping from blocks to inodes.

    Args:
      location (str): location / identifier of the volume.
      start_offset (int): byte offset of the volume.
    """
    rows = []
    image = pytsk3.Img_Info(self.image_path)
    filesystem = pytsk3.FS_Info(image, offset=start_offset)
    for inode in range(filesystem.info.first_inum,
                       filesystem.info.last_inum + 1):
      file_metadata = filesystem.open_meta(inode)
      if file_metadata.info.meta.nlink > 0:
        for attribute in file_metadata:
          for run in attribute:
            for block in range(run.len):
              rows.append((
                  run.addr + block,
                  inode,
                  location,
              ))
              if len(rows) >= BATCH_SIZE:
                self.postgresql.bulk_insert('blocks (block, inum, part)', rows)
                rows = []
    if rows:
      self.postgresql.bulk_insert('blocks (block, inum, part)', rows)

  def process_image(self):
    """Process the image."""
    self.output_path = tempfile.mkdtemp()
    log.info('* Processing start: %s', datetime.now())
    self._extract_strings()
    log.info('String extraction complete.')

    log.info('* Parsing image: %s', datetime.now())
    self._parse_filesystems()
    log.info('Parsing complete.')

    log.info('* Indexing strings: %s', datetime.now())
    self._index_strings()
    log.info('Indexing complete.')

    log.info('* Processing complete: %s', datetime.now())


class ImageProcessorOptions():
  """Image processor options.

  Attributes:
    base64 (bool): decode base64.
    gunzip (bool): decompress gzip.
    unzip (bool): decompress zip.
  """

  def __init__(self, base64=True, gunzip=True, unzip=True, reindex=False):
    """Initialise image processor options."""
    super().__init__()
    self.base64 = base64
    self.gunzip = gunzip
    self.unzip = unzip
    self.reindex = reindex


class UnattendedVolumeScannerMediator(volume_scanner.VolumeScannerMediator):
  """Unattended volume scanner mediator."""

  def GetAPFSVolumeIdentifiers(self, volume_system, volume_identifiers):
    """Retrieves APFS volume identifiers.

    In an unattended execution, this method returns all volume identifiers.

    Args:
      volume_system (APFSVolumeSystem): volume system.
      volume_identifiers (list[str]): volume identifiers including prefix.

    Returns:
      list[str]: all volume identifiers including prefix.
    """
    prefix = 'apfs'
    return [
        '{0:s}{1:d}'.format(prefix, volume_index)
        for volume_index in range(1, volume_system.number_of_volumes + 1)
    ]

  def GetLVMVolumeIdentifiers(self, volume_system, volume_identifiers):
    """Retrieves LVM volume identifiers.

    This method can be used to prompt the user to provide LVM volume
    identifiers.

    Args:
      volume_system (LVMVolumeSystem): volume system.
      volume_identifiers (list[str]): volume identifiers including prefix.

    Returns:
      list[str]: selected volume identifiers including prefix or None.
    """
    prefix = 'lvm'
    return [
        '{0:s}{1:d}'.format(prefix, volume_index)
        for volume_index in range(1, volume_system.number_of_volumes + 1)
    ]

  def GetPartitionIdentifiers(self, volume_system, volume_identifiers):
    """Retrieves partition identifiers.

    In an unattended execution, this method returns all partition identifiers.

    Args:
      volume_system (TSKVolumeSystem): volume system.
      volume_identifiers (list[str]): volume identifiers including prefix.

    Returns:
      list[str]: all volume identifiers including prefix.
    """
    prefix = 'p'
    return [
        '{0:s}{1:d}'.format(prefix, volume_index)
        for volume_index in range(1, volume_system.number_of_volumes + 1)
    ]

  def GetVSSStoreIdentifiers(self, volume_system, volume_identifiers):
    """Retrieves VSS store identifiers.

    Placeholder method for VSS support.

    Args:
      volume_system (VShadowVolumeSystem): volume system.
      volume_identifiers (list[str]): volume identifiers including prefix.

    Returns:
      list[str]: None.
    """
    return []

  def UnlockEncryptedVolume(
      self, source_scanner_object, scan_context, locked_scan_node, credentials):
    """Unlocks an encrypted volume.

    Placeholder method for encrypted volume support.

    Args:
      source_scanner_object (SourceScanner): source scanner.
      scan_context (SourceScannerContext): source scanner context.
      locked_scan_node (SourceScanNode): locked scan node.
      credentials (Credentials): credentials supported by the locked scan node.

    Returns:
      bool: True if the volume was unlocked.
    """
    log.warning(
        'Encrypted volumes are currently unsupported: %s',
        locked_scan_node.path_spec.CopyToDict())
    return False
