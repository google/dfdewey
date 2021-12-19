# -*- coding: utf-8 -*-
# Copyright 2021 Google LLC
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
"""Opensearch datastore."""

import collections

from opensearchpy import OpenSearch
from opensearchpy import exceptions


class OpenSearchDataStore():
  """Implements the datastore."""

  # Number of events to queue up when bulk inserting events.
  DEFAULT_FLUSH_INTERVAL = 20000
  DEFAULT_SIZE = 1000  # Max events to return

  def __init__(self, host='127.0.0.1', port=9200, url=None):
    """Create an OpenSearch client."""
    super().__init__()
    if url:
      self.client = OpenSearch([url], timeout=30)
    else:
      self.client = OpenSearch([{'host': host, 'port': port}], timeout=30)
    self.import_counter = collections.Counter()
    self.import_events = []

  @staticmethod
  def build_query(query_string):
    """Build OpenSearch DSL query.

    Args:
      query_string: Query string

    Returns:
      OpenSearch DSL query as a dictionary
    """

    query_dsl = {
        'query': {
            'bool': {
                'must': [{
                    'query_string': {
                        'query': query_string
                    }
                }]
            }
        }
    }

    return query_dsl

  def create_index(self, index_name):
    """Create an index.

    Args:
      index_name: Name of the index

    Returns:
      Index name in string format.
    """
    if not self.client.indices.exists(index_name):
      try:
        self.client.indices.create(index=index_name)
      except exceptions.ConnectionError as e:
        raise RuntimeError('Unable to connect to backend datastore.') from e

    return index_name

  def delete_index(self, index_name):
    """Delete OpenSearch index.

    Args:
      index_name: Name of the index to delete.
    """
    if self.client.indices.exists(index_name):
      try:
        self.client.indices.delete(index=index_name)
      except exceptions.ConnectionError as e:
        raise RuntimeError('Unable to connect to backend datastore.') from e

  def import_event(
      self, index_name, event=None, flush_interval=DEFAULT_FLUSH_INTERVAL):
    """Add event to OpenSearch.

    Args:
      index_name: Name of the index in OpenSearch
      event: Event dictionary
      flush_interval: Number of events to queue up before indexing

    Returns:
      The number of events processed.
    """
    if event:
      # Header needed by OpenSearch when bulk inserting.
      header = {'index': {'_index': index_name}}

      self.import_events.append(header)
      self.import_events.append(event)
      self.import_counter['events'] += 1

      if self.import_counter['events'] % int(flush_interval) == 0:
        self.client.bulk(body=self.import_events)
        self.import_events = []
    else:
      # Import the remaining events in the queue.
      if self.import_events:
        self.client.bulk(body=self.import_events)

    return self.import_counter['events']

  def index_exists(self, index_name):
    """Check if an index already exists.

    Args:
      index_name: Name of the index

    Returns:
      True if the index exists, False if not.
    """
    return self.client.indices.exists(index_name)

  def search(self, index_id, query_string, size=DEFAULT_SIZE):
    """Search OpenSearch.

    This will take a query string from the UI together with a filter definition.
    Based on this it will execute the search request on OpenSearch and get the
    result back.

    Args:
      index_id: Index to be searched
      query_string: Query string
      size: Maximum number of results to return

    Returns:
      Set of event documents in JSON format
    """

    query_dsl = self.build_query(query_string)

    # Default search type for OpenSearch is query_then_fetch.
    search_type = 'query_then_fetch'

    # pylint: disable=unexpected-keyword-arg
    return self.client.search(
        body=query_dsl, index=index_id, size=size, search_type=search_type)
