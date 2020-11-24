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
"""Tests for elasticsearch datastore."""

import unittest
import mock

from elasticsearch import exceptions

from dfdewey.datastore.elastic import ElasticsearchDataStore

TEST_INDEX_NAME = ''.join(('es', 'd41d8cd98f00b204e9800998ecf8427e'))


class ElasticTest(unittest.TestCase):
  """Tests for Elasticsearch datastore."""

  def _get_datastore(self):
    """Get a mock elasticsearch datastore.

    Returns:
      Mock elasticsearch datastore.
    """
    # with mock.patch('psycopg2.connect') as _:
    es = ElasticsearchDataStore()
    return es

  def test_build_query(self):
    """Test build query method."""
    es = self._get_datastore()
    query_string = 'test'
    query = es.build_query(query_string)

    query_dsl = {
        'query': {
            'bool': {
                'must': [{
                    'query_string': {
                        'query': 'test'
                    }
                }]
            }
        }
    }

    self.assertEqual(query, query_dsl)

  @mock.patch('elasticsearch.client.IndicesClient.create')
  @mock.patch('elasticsearch.client.IndicesClient.exists')
  def test_create_index(self, mock_exists, mock_create):
    """Test create index method."""
    es = self._get_datastore()

    mock_exists.return_value = False

    result = es.create_index(TEST_INDEX_NAME)
    self.assertEqual(result, TEST_INDEX_NAME)

    mock_create.side_effect = exceptions.ConnectionError
    with self.assertRaises(RuntimeError):
      result = es.create_index(TEST_INDEX_NAME)

  @mock.patch('elasticsearch.client.IndicesClient.delete')
  @mock.patch('elasticsearch.client.IndicesClient.exists')
  def test_delete_index(self, mock_exists, mock_delete):
    """Test delete index method."""
    es = self._get_datastore()

    mock_exists.return_value = True

    es.delete_index(TEST_INDEX_NAME)
    mock_delete.assert_called_once_with(index=TEST_INDEX_NAME)

    mock_delete.side_effect = exceptions.ConnectionError
    with self.assertRaises(RuntimeError):
      es.delete_index(TEST_INDEX_NAME)

  def test_import_event(self):
    """Test import event method."""
    es = self._get_datastore()

    with mock.patch.object(es.client, 'bulk') as mock_bulk:
      result = es.import_event(TEST_INDEX_NAME)
      self.assertEqual(result, 0)
      mock_bulk.assert_not_called()

      es.import_events = [{
          'index': {
              '_index': 'esd41d8cd98f00b204e9800998ecf8427e'
          }
      }, {
          'image': 'd41d8cd98f00b204e9800998ecf8427e',
          'offset': 1048579,
          'file_offset': None,
          'data': 'NTFS    \n'
      }, {
          'index': {
              '_index': 'esd41d8cd98f00b204e9800998ecf8427e'
          }
      }, {
          'index': {
              '_index': 'esd41d8cd98f00b204e9800998ecf8427e'
          }
      }, {
          'image': 'd41d8cd98f00b204e9800998ecf8427e',
          'offset': 1048755,
          'file_offset': None,
          'data': 'press any key to try again ... \n'
      }]
      result = es.import_event(TEST_INDEX_NAME)
      self.assertEqual(result, 0)
      mock_bulk.assert_called_once()

      test_event = {
          'image': 'd41d8cd98f00b204e9800998ecf8427e',
          'offset': 1048579,
          'file_offset': None,
          'data': 'NTFS    \n'
      }
      result = es.import_event(TEST_INDEX_NAME, test_event, flush_interval=1)
      self.assertEqual(result, 1)

  @mock.patch('elasticsearch.client.IndicesClient.exists')
  def test_index_exists(self, mock_exists):
    """Test index exists method."""
    es = self._get_datastore()

    es.index_exists(TEST_INDEX_NAME)
    mock_exists.assert_called_once_with(TEST_INDEX_NAME)

  @mock.patch('elasticsearch.Elasticsearch.search')
  @mock.patch('elasticsearch.client.IndicesClient.exists')
  def test_search(self, mock_exists, mock_search):
    """Test search method."""
    es = self._get_datastore()

    mock_exists.return_value = True
    search_results = {
        'took': 24,
        'timed_out': False,
        '_shards': {
            'total': 1,
            'successful': 1,
            'skipped': 0,
            'failed': 0
        },
        'hits': {
            'total': {
                'value': 2,
                'relation': 'eq'
            },
            'max_score':
                13.436,
            'hits': [{
                '_index': 'esd41d8cd98f00b204e9800998ecf8427e',
                '_type': '_doc',
                '_id': '7gST1HUBuaTSqxk-XzDA',
                '_score': 13.436,
                '_source': {
                    'image': 'd41d8cd98f00b204e9800998ecf8427e',
                    'offset': 1048755,
                    'file_offset': None,
                    'data': 'press any key to try again ... \n'
                }
            }, {
                '_index': 'esd41d8cd98f00b204e9800998ecf8427e',
                '_type': '_doc',
                '_id': 'oAST1HUBuaTSqxk-XzLD',
                '_score': 13.436,
                '_source': {
                    'image': 'd41d8cd98f00b204e9800998ecf8427e',
                    'offset': 10485427,
                    'file_offset': None,
                    'data': 'press any key to try again ... \n'
                }
            }]
        }
    }
    mock_search.return_value = search_results

    results = es.search(TEST_INDEX_NAME, '"any key"')
    self.assertEqual(results, search_results)


if __name__ == '__main__':
  unittest.main()
