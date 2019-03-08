"""
API endpoints to access organizations through ElasticSearch
"""
from django.conf import settings
from django.utils.translation import get_language_from_request

from elasticsearch.exceptions import NotFoundError
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet

from ..exceptions import QueryFormatException
from ..indexers import ES_INDICES
from ..utils.viewsets import AutocompleteMixin, ViewSetMetadata


class OrganizationsViewSet(AutocompleteMixin, ViewSet):
    """
    A simple viewset with GET endpoints to fetch organizations
    See API Blueprint for details on consumer use.
    """

    _meta = ViewSetMetadata(indexer=ES_INDICES.organizations)

    # pylint: disable=no-self-use,unused-argument
    def list(self, request, version):
        """
        Organization search endpoint: pass query params to ElasticSearch so it filters
        organizations and returns a list of matching items
        """
        try:
            limit, offset, query = self._meta.indexer.build_es_query(request)
        except QueryFormatException as exc:
            # Return a 400 with error information if the query params are not as expected
            return Response(status=400, data={"errors": exc.args[0]})

        search_query_response = settings.ES_CLIENT.search(
            _source=getattr(self._meta.indexer, "display_fields", "*"),
            index=self._meta.indexer.index_name,
            doc_type=self._meta.indexer.document_type,
            body=query,
            # Directly pass meta-params through as arguments to the ES client
            from_=offset,
            size=limit or settings.ES_DEFAULT_PAGE_SIZE,
        )

        # Format the response in a consumer-friendly way
        # NB: if there are 0 hits the query response is formatted the exact same way, only the
        # .hits.hits array is empty.
        response_object = {
            "meta": {
                "count": len(search_query_response["hits"]["hits"]),
                "offset": offset,
                "total_count": search_query_response["hits"]["total"],
            },
            "objects": [
                self._meta.indexer.format_es_object_for_api(
                    organization,
                    # Get the best language to return multilingual fields
                    get_language_from_request(request),
                )
                for organization in search_query_response["hits"]["hits"]
            ],
        }
        return Response(response_object)

    # pylint: disable=no-self-use,invalid-name,unused-argument
    def retrieve(self, request, pk, version):
        """
        Return a single organization by ID
        """
        # Wrap the ES get in a try/catch so we control the exception we emit — it would
        # raise and end up in a 500 error otherwise
        try:
            query_response = settings.ES_CLIENT.get(
                index=self._meta.indexer.index_name,
                doc_type=self._meta.indexer.document_type,
                id=pk,
            )
        except NotFoundError:
            return Response(status=404)

        # Format a clean organization object as a response
        return Response(
            self._meta.indexer.format_es_object_for_api(
                query_response,
                # Get the best language we can return multilingual fields in
                get_language_from_request(request),
            )
        )
