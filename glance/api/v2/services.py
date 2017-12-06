# Copyright 2012 OpenStack Foundation.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.
from cursive import exception as cursive_exception
import glance_store
from glance_store import backend
from oslo_config import cfg
from oslo_log import log as logging
from oslo_utils import encodeutils
from oslo_serialization import jsonutils as json
from oslo_utils import excutils
import six
import six.moves.urllib.parse as urlparse
from six.moves import http_client as http
import webob.exc

from glance.api import policy
from glance.common import exception
from glance.common import trust_auth
from glance.common import timeutils
from glance.common import utils
from glance.common import wsgi
import glance.db
import glance.gateway
from glance.i18n import _, _LE, _LI
import glance.notifier


LOG = logging.getLogger(__name__)

CONF = cfg.CONF

class RequestDeserializer(wsgi.JSONRequestDeserializer):
    """Deserializer request body to json"""

    _base_properties = ('status', 'name', 'schema', 'port', 'endpoint',
                        'total_size', 'avail_size', 'disk_wwn', 'host',
                        'file_system_uuid', 'storage_dir', 'id')

    _supported_operations = ('replace')

    _readonly_properties = ('created_at', 'updated_at', 'id')

    _reserved_properties = ('deleted_at', 'deleted')

    _available_sort_keys = ('name', 'status', 'available_size', 'total_size',
                            'created_at', 'updated_at', 'host', 'endpoint')

    _default_sort_key = 'created_at'

    _default_sort_dir = 'desc'

    def __init__(self, schema=None):
        super(RequestDeserializer, self).__init__()
#        self.schema = schema or get_schema()

    def _get_request_body(self, request):
        output = super(RequestDeserializer, self).default(request)
        if 'body' not in output:
            msg = _('Body expected in request.')
            raise webob.exc.HTTPBadRequest(explanation=msg)
        return output['body']

    def create(self, request):
        import pdb
        pdb.set_trace()
        body = self._get_request_body(request)
        service = {}
        properties = body

        for key in self._base_properties:
            if 'id' == key:
                service['service_id'] = properties.pop(key, None)
            else:
                service[key] = properties.pop(key, None)

        tags = properties.pop('tags', [])
        return dict(service=service, extra_properties=properties, tags=tags)

    def update(self, request):
        changes = []
        content_type = 'application/json'
        if request.content_type != content_type:
            headers = {'Accept-Patch':
                    ', '.join(content_type)}
            raise webob.exc.HTTPUnsupportedMediaType(headers=headers)

        body = self._get_request_body(request)

        if not isinstance(body, list):
            msg = _('Request body must be a JSON array of operation objects.')
            raise webob.exc.HTTPBadRequest(explanation=msg)

        for raw_change in body:
            if not isinstance(raw_change, dict):
                msg = _('Operations must be JSON objects.')
                raise webob.exc.HTTPBadRequest(explanation=msg)
            (op, path) = self._parse_json_schema_change(raw_change)

            self._validate_path(path)
            change = {'op': op, 'path': path}

            if not op == 'remove':
                change['value'] = self._get_change_value(raw_change, op)

            self._validate_change(change)

            changes.append(change)

        return {'changes': changes}

    def _validate_path(self, path):
        pass

    def _validate_change(self, change):
        key = change['path']
        if key in self._readonly_properties:
            msg = _("Attribute '%s' is read-only") % key
            raise webob.exc.HTTPForbidden(explanation=six.text_type(msg))

        if change['op'] == 'remove':
            return

    def _get_change_value(self, raw_change, op):
         if 'value' not in raw_change:
             msg = _('Operation "%s" requires a member named "value".')
             raise webob.exc.HTTPBadRequest(explanation=msg % op)
         return raw_change['value']

    def _get_change_operation(self, raw_change):
        op = raw_change.get('op')
        if op is None:
            msg = (_('Unable to find `op` in JSON Schema change. '
                     'It must be one of the following: %(available)s.') %
                     {'available': ', '.join(self._supported_operations)})
            raise webob.exc.HTTPBadRequest(explanation=msg)
        if op not in self._supported_operations:
            msg = (_('Invalid operation: `%(op)s`. '
                     'It must be one of the following : %(available)s.') %
                   {'op': op,
                    'available': ', '.join(self._supported_operations)})
            raise webob.exc.HTTPBadRequest(explanation=msg)
        return op

    def _get_change_path(self, raw_change):
        try:
            return raw_change['path'][1:]
        except KeyError:
            msg = _("Unable to find '%d' in JSON Schema change") % 'path'
            raise webob.exc.HTTPBadRequest(explanation=msg)

    def _decode_json_pointer(self, path):
        pass

    def _parse_json_schema_change(self, raw_change):
        op = self._get_change_operation(raw_change)
        path = self._get_change_path(raw_change)

        #path_list = self._decode_json_pointer(path)
        #return op, path_list
        return op, path

    def index(self, request):
        """List services instance"""
        params = request.params.copy()
        limit = params.pop('limit', None)
        marker = params.pop('marker', None)

        query_params = {
                'filters': self._get_filters(params)
                }

        if limit is not None:
            query_params['limit'] = self._validate_limit(limit)

        if marker is not None:
            query_params['marker'] = marker

        query_params['sort_keys'], query_params['sort_dirs'] = (
                self._get_sorting_params(params))

        return query_params

    def _get_sorting_params(self, params):
        """
        Process sorting params.
        Currently service supports two sorting syntax: classic and new one,
        that is uniform for storage service project.
        Classic syntax: sort_key=name&sort_dir=asc&sort_key=size&sort_dir=desc
        New syntax: sort=name:asc,size:desc
        """
        sort_keys = []
        sort_dirs = []

        if 'sort' in params:
            #pass
            raise webob.exc.HTTPBadRequest()
        else:
            while 'sort_key' in params:
                sort_keys.append(self._validate_sort_key(
                    params.pop('sort_key').strip()))

            while 'sort_dir' in params:
                sort_dirs.append(self._validate_sort_dir(
                    params.pop('sort_dir').strip()))

            if sort_dirs:
                dir_len = len(sort_dirs)
                key_len = len(sort_keys)

                if dir_len > 1 and dir_len != key_len:
                    msg = _("Number of sort dirs does not match the number "
                            "of sort keys")
                    raise webob.exc.HTTPBadRequest(explanation=msg)

        if not sort_keys:
            sort_keys = [self._default_sort_key]

        if not sort_dirs:
            sort_dirs = [self._default_sort_dir]

        return sort_keys, sort_dirs

    def _get_filters(self, filters):
        status = filters.get('status')
        if status:
            if status not in ['active', 'inactive', 'deleted', 'error']:
                msg = _("Invalid status value: %s") % status
                raise webob.exc.HTTPBadRequest(explanation=msg)

        return filters

    def _validate_limit(self, limit):
        try:
            limit = int(limit)
        except ValueError:
            msg = _("limit param must be an integer")
            raise webob.exc.HTTPBadRequest(explanation=msg)

        if limit < 0:
            msg = _("limit param must be positive")
            raise webob.exc.HTTPBadRequest(explanation=msg)

        return limit

    def _validate_sort_key(self, sort_key):
        if sort_key not in self._available_sort_keys:
            msg = _('Invalid sort key: %(sort_key)s '
                    'It must be one of the following: %(available)s ') % (
                    {'sort_key': sort_key,
                     'available': ', '.join(self_available_sort_keys)})
            raise webob.exc.HTTPBadRequest(explanation=msg)

        return sort_key

    def _validate_sort_dir(self, sort_dir):
        if sort_dir not in ['asc', 'desc']:
            msg = ('Invalid sort direction: %s') % sort_dir
            raise webob.exc.HTTPBadRequest(explanation=msg)

        return sort_dir

class ServiceController(object):
    def __init__(self, db_api=None, store_api=None,
                policy_enforcer=None, notifier=None,
                gateway=None):
        if gateway is None:
            self.db_api = db_api or glance.db.get_api()
            self.store_api = store_api or glance_store
            self.notifier = notifier or glance.notifier.Notifier()
            self.policy = policy_enforcer or policy.Enforcer()
            gateway = glance.gateway.Gateway(self.db_api, self.store_api,
                                             self.notifier, self.policy)
        self.gateway = gateway

    @utils.mutating
    def create(self, req, service, extra_properties, tags):
        import pdb
        pdb.set_trace()
        service_factory = self.gateway.get_service_factory(req.context)
        service_repo = self.gateway.get_service_repo(req.context)
        try:
            service = service_factory.new_service(extra_properties=extra_properties,
                    tags=tags, **service)
            service_repo.add(service)
        except (exception.DuplicateLocation, exception.Invalid) as e:
            raise webob.exc.HTTPBadRequest(explanation=e.msg)
        except exception.Duplicate as e:
            raise webob.exc.HTTPConflict(explanation=e.msg)

        return service

    def show(self, req, service_id):
        service_repo = self.gateway.get_service_repo(req.context)
        try:
            return service_repo.get(service_id)
        except exception.Forbidden as e:
            LOG.debug("User not permitted to show image '%s'", image_id)
            raise webob.exc.HTTPForbidden(explanation=e.msg)
        except exception.NotFound as e:
            raise webob.exc.HTTPNotFound(explanation=e.msg)
        except exception.NotAuthenticated as e:
            raise webob.exc.HTTPUnauthorized(explanation=e.msg)

    @utils.mutating
    def delete(self, req, service_id):
        service_repo = self.gateway.get_service_repo(req.context)
        try:
            service = service_repo.get(service_id)
            service.delete()
            service_repo.remove(service)
        except exception.InvalidImageStatusTransition as e:
            raise webob.exc.HTTPBadRequest(explanation=e.msg)
        except exception.NotAuthenticated as e:
            raise webob.exc.HTTPUnauthorized(explanation=e.msg)

    @utils.mutating
    def update(self, req, service_id, changes):
        service_repo = self.gateway.get_service_repo(req.context)
        try:
            service = service_repo.get(service_id)
            for change in changes:
                change_method_name = '_do_%s' % change['op']
                change_method = getattr(self, change_method_name)
                change_method(req, service, change)

            if changes:
                service_repo.save(service)
        except exception.NotFound as e:
            raise webob.exc.HTTPNotFound(explanation=e.msg)
        except (exception.Invalid, exception.BadStoreUri) as e:
            raise webob.exc.HTTPBadRequest(explanation=e.msg)
        except exception.Forbidden as e:
            LOG.debug("User not permitted to update service '%s'.", service_id)
            raise webob.exc.HTTPForbidden(explanation=e.msg)

        return service

    def  _do_replace(self, req, service, change):
        path = change['path']
        value = change['value']
        if hasattr(service, path):
            setattr(service, path, value)
        else:
            msg = _("Property %s does not exist.")
            raise webob.exc.HTTPConflict(msg % path)

    def index(self, req, marker=None, limit=None, sort_keys=None,
            sort_dirs=None, filters=None):
        sort_keys = ['created_at'] if not sort_keys else sort_keys

        sort_dirs = ['desc'] if not sort_dirs else sort_dirs

        result = {}
        if filters is None:
            filters = {}
        filters['deleted'] = False

        if limit is None:
            limit = CONF.limit_param_default
        limit = min(CONF.api_limit_max, limit)

        service_repo = self.gateway.get_service_repo(req.context)
        try:
            services = service_repo.list(marker=marker, limit=limit,
                                        sort_keys=sort_keys,
                                        sort_dirs=sort_dirs,
                                        filters=filters)
            if len(services) != 0 and len(services) == limit:
                result['next_marker'] = services[-1].id
        except (exception.NotFound, exception.InvalidSortKey,
                exception.InvalidFilterRangeValue,
                exception.InvalidParameterValue,
                exception.InvalidFilterOperatorValue) as e:
            raise webob.exc.HTTPBadRequest(explanation=e.msg)
        except exception.Forbidden as e:
            LOG.debug("User not permitted to retrieve services index")
            raise webob.exc.HTTPForbidden(explanation=e.msg)
        except exception.NotAuthenticated as e:
            raise webob.exc.HTTPUnauthorized(explanation=e.msg)

        result['services'] = services

        return result


class ResponseSerializer(wsgi.JSONResponseSerializer):
    def __init__(self, schema=None):
        super(ResponseSerializer, self).__init__()
#        self.schema = schema or get_schema()

    def _get_service_href(self, service, subcollection=''):
        base_href = '/v2/services/%s' % service.id
        if subcollection:
            base_href = '%s/%s' % (base_href, subcollection)

        return base_href

    def _format_service(self, service):
        try:
            service_view = dict(service.extra_properties)
            attributes = ['name', 'schema', 'port', 'host', 'endpoint', 'status',
                    'total_size', 'avail_size', 'disk_wwn', 'file_system_uuid',
                    'storage_dir']
            for key in attributes:
                service_view[key] = getattr(service, key)

            service_view['id'] = service.id
            service_view['self'] = self._get_service_href(service)
            service_view['used_size'] = service.total_size - service.avail_size
            service_view['created_at'] = timeutils.isotime(service.created_at)
            service_view['updated_at'] = timeutils.isotime(service.updated_at)
            service_view['tags'] = list(service.tags)

            return service_view
        except exception.Forbidden as e:
            raise webob.exc.HTTPForbidden(explanation=e.msg)


    def create(self, response, service):
        import pdb
        pdb.set_trace()
        response.status_int = http.CREATED
        self.show(response, service)

    def show(self, response, service):
        service_view = self._format_service(service)
        body = json.dumps(service_view, ensure_ascii=False)
        response.unicode_body = six.text_type(body)
        response.content_type = 'application/json'

    def update(self, response, service):
        service_view = self._format_service(service)
        body = json.dumps(service_view, ensure_ascii=False)
        response.unicode_body = six.text_type(body)
        response.content_type = 'application/json'

    def index(self, response, result):
        params = dict(response.request.params)
        params.pop('marker', None)
        query = urlparse.urlencode(params)
        body = {
                'services': [self._format_service(s) for s in result['services']],
                'first': '/v2/services',
                }

        if query:
            body['first'] = '%s?%s' % (body['first'], query)

        if 'next_marker' in result:
            params['marker'] = result['next_marker']
            next_query = urlparse.urlencode(params)
            body['next'] = '/v2/services?%s' % next_query

        response.unicode_body = six.text_type(json.dumps(body, ensure_ascii=False))
        response.content_type = 'application/json'


def create_resource(custom_properties=None):
    """services resource factory method"""
    deserializer = RequestDeserializer()
    serializer = ResponseSerializer()
    controller = ServiceController()
    return wsgi.Resource(controller, deserializer, serializer)
