# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
# Copyright 2010-2012 OpenStack Foundation
# Copyright 2013 IBM Corp.
# Copyright 2015 Mirantis, Inc.
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

from oslo_config import cfg
from oslo_utils import importutils
from wsme.rest import json

from glance.api.v2.model.metadef_property_type import PropertyType
from glance.common import crypt
from glance.common import exception
from glance.common import location_strategy
import glance.domain
import glance.domain.proxy
from glance.i18n import _

CONF = cfg.CONF
CONF.import_opt('image_size_cap', 'glance.common.config')
CONF.import_opt('metadata_encryption_key', 'glance.common.config')


def get_api(v1_mode=False):
    """
    When using v2_registry with v2_api or alone, it is essential that the opt
    'data_api' be set to 'glance.db.registry.api'. This requires us to
    differentiate what this method returns as the db api. i.e., we do not want
    to return 'glance.db.registry.api' for a call from v1 api.
    Reference bug #1516706
    """
    if v1_mode:
        # prevent v1_api from talking to v2_registry.
        if CONF.data_api == 'glance.db.simple.api':
            api = importutils.import_module(CONF.data_api)
        else:
            api = importutils.import_module('glance.db.sqlalchemy.api')
    else:
        api = importutils.import_module(CONF.data_api)

    if hasattr(api, 'configure'):
        api.configure()

    return api


def unwrap(db_api):
    return db_api


# attributes common to all models
BASE_MODEL_ATTRS = set(['id', 'created_at', 'updated_at', 'deleted_at',
                        'deleted'])


IMAGE_ATTRS = BASE_MODEL_ATTRS | set(['name', 'status', 'size', 'virtual_size',
                                      'disk_format', 'container_format',
                                      'min_disk', 'min_ram', 'is_public',
                                      'locations', 'checksum', 'owner',
                                      'protected'])


class ServiceProxy(glance.domain.proxy.Service):
    """proxy for Service dict instance"""
    def __init__(self, service, context, db_api):
        self.context = context
        self.db_api = db_api
        self.service = service
        super(ServiceProxy, self).__init__(service)


class ServiceRepo(object):
    def __init__(self, context, db_api):
        self.context = context
        self.db_api = db_api

    def _format_service_to_db(self, service):
        """format service instance to dict for db"""
        return {
                "id": service.id,
                "name": service.name,
                "schema": service.schema,
                "port": service.port,
                "host": service.host,
                "endpoint": service.endpoint,
                "status": service.status,
                "total_size": service.total_size,
                "avail_size": service.avail_size,
                "disk_wwn": service.disk_wwn,
                "file_system_uuid": service.file_system_uuid,
                "storage_dir": service.storage_dir,
                "created_at": service.created_at,
                "updated_at": service.updated_at
                }

    def _format_service_from_db(self, db_service):
        return glance.domain.Service(
        service_id = db_service['id'],
        status = db_service['status'],
        name = db_service['name'],
        schema = db_service['schema'],
        port = db_service['port'],
        host = db_service['host'],
        endpoint = db_service['endpoint'],
        total_size = db_service['total_size'],
        avail_size = db_service['avail_size'],
        disk_wwn = db_service['disk_wwn'],
        file_system_uuid = db_service['file_system_uuid'],
        storage_dir = db_service['storage_dir'],
        created_at = db_service['created_at'],
        updated_at = db_service['updated_at'],
        extra_properties = {},
        tags = {}
        )

    def add(self, service):
        service_values = self._format_service_to_db(service)

        if (service_values['avail_size'] is not None
         and service_values['total_size'] is not None
         and service_values['total_size'] < service_values['avail_size']):
            raise exception.ImageSizeLimitExceeded

        new_values = self.db_api.service_create(self.context, service_values)
        service.created_at = new_values['created_at']
        service.updated_at = new_values['updated_at']

    def get(self, service_id):
        try:
            db_api_service = dict(self.db_api.service_get(self.context, service_id))
            if db_api_service['deleted']:
                raise exception.ImageNotFound()
        except (exception.ImageNotFound, exception.Forbidden):
            msg = _("No storage service found with ID %s") % service_id
            raise exception.ImageNotFound(msg)
        service = self._format_service_from_db(db_api_service)
        return ServiceProxy(service, self.context, self.db_api)

    def remove(self, service):
        try:
            self.db_api.service_update(self.context, service.id,
                                        {'status': service.status},
                                        purge_props=True)
        except (exception.ImageNotFound, exception.Forbidden):
            msg = _("No image found with ID %s") % service_id
            raise exception.ImageNotFound(msg)
        new_values = self.db_api.service_destroy(self.context, service.id)
        service.updated_at = new_values['updated_at']

    def save(self, service, from_state=None):
        service_values = self._format_service_to_db(service)
        try:
            new_values = self.db_api.service_update(self.context,
                                                  service.id,
                                                  service_values,
                                                  purge_props=True,
                                                  from_state=from_state)
        except (exception.ImageNotFound, exception.Forbidden):
            msg = _("No service found with ID %s") % service.id
            raise exception.ImageNotFound(msg)
        service.updated_at = new_values['updated_at']
    def list(self, marker=None, limit=None, sort_keys=None,
            sort_dirs=None, filters=None):
        sort_keys = ['created_at'] if not sort_keys else sort_keys
        sort_dirs = ['desc'] if not sort_dirs else sort_dirs
        db_api_services = self.db_api.service_get_all(
                self.context, filters=filters, marker=marker, limit=limit,
                sort_keys=sort_keys, sort_dirs=sort_dirs)
        services = []
        for db_api_service in db_api_services:
            db_service = dict(db_api_service)
            service = self._format_service_from_db(db_service)
            services.append(service)
        return services


class ImageRepo(object):

    def __init__(self, context, db_api):
        self.context = context
        self.db_api = db_api

    def get(self, image_id):
        try:
            db_api_image = dict(self.db_api.image_get(self.context, image_id))
            if db_api_image['deleted']:
                raise exception.ImageNotFound()
        except (exception.ImageNotFound, exception.Forbidden):
            msg = _("No image found with ID %s") % image_id
            raise exception.ImageNotFound(msg)
        tags = self.db_api.image_tag_get_all(self.context, image_id)
        db_service =  dict(self.db_api.service_get(self.context,
                                                   db_api_image.get('service_uuid')))
        image = self._format_image_from_db(db_api_image, tags,
                                           db_service=db_service)
        return ImageProxy(image, self.context, self.db_api)

    def list(self, marker=None, limit=None, sort_key=None,
             sort_dir=None, filters=None, member_status='accepted'):
        sort_key = ['created_at'] if not sort_key else sort_key
        sort_dir = ['desc'] if not sort_dir else sort_dir
        db_api_images = self.db_api.image_get_all(
            self.context, filters=filters, marker=marker, limit=limit,
            sort_key=sort_key, sort_dir=sort_dir,
            member_status=member_status, return_tag=True)
        images = []
        for db_api_image in db_api_images:
            db_image = dict(db_api_image)
            db_service = dict(self.db_api.service_get(self.context, db_image.get('service_uuid')))
            image = self._format_image_from_db(db_image, db_image['tags'], db_service=db_service)
            images.append(image)
        return images

    def _format_image_from_db(self, db_image, db_tags, db_service=None):
        properties = {}
        for prop in db_image.pop('properties'):
            # NOTE(markwash) db api requires us to filter deleted
            if not prop['deleted']:
                properties[prop['name']] = prop['value']
        locations = [loc for loc in db_image['locations']
                     if loc['status'] == 'active']
        if CONF.metadata_encryption_key:
            key = CONF.metadata_encryption_key
            for l in locations:
                l['url'] = crypt.urlsafe_decrypt(key, l['url'])
        return glance.domain.Image(
            image_id=db_image['id'],
            name=db_image['name'],
            status=db_image['status'],
            created_at=db_image['created_at'],
            updated_at=db_image['updated_at'],
            visibility=db_image['visibility'],
            min_disk=db_image['min_disk'],
            min_ram=db_image['min_ram'],
            protected=db_image['protected'],
            locations=location_strategy.get_ordered_locations(locations),
            checksum=db_image['checksum'],
            owner=db_image['owner'],
            disk_format=db_image['disk_format'],
            container_format=db_image['container_format'],
            size=db_image['size'],
            virtual_size=db_image['virtual_size'],
            service=db_service,
            extra_properties=properties,
            tags=db_tags
        )

    def _format_image_to_db(self, image):
        locations = image.locations
        if CONF.metadata_encryption_key:
            key = CONF.metadata_encryption_key
            ld = []
            for loc in locations:
                url = crypt.urlsafe_encrypt(key, loc['url'])
                ld.append({'url': url, 'metadata': loc['metadata'],
                           'status': loc['status'],
                           # NOTE(zhiyan): New location has no ID field.
                           'id': loc.get('id')})
            locations = ld
        return {
            'id': image.image_id,
            'name': image.name,
            'status': image.status,
            'created_at': image.created_at,
            'min_disk': image.min_disk,
            'min_ram': image.min_ram,
            'protected': image.protected,
            'locations': locations,
            'checksum': image.checksum,
            'owner': image.owner,
            'disk_format': image.disk_format,
            'container_format': image.container_format,
            'size': image.size,
            'virtual_size': image.virtual_size,
            'visibility': image.visibility,
            'properties': dict(image.extra_properties),
            'service_uuid': image.service.get('id'),
        }

    def add(self, image):
        image_values = self._format_image_to_db(image)
        if (image_values['size'] is not None
           and image_values['size'] > CONF.image_size_cap):
            raise exception.ImageSizeLimitExceeded
        # the updated_at value is not set in the _format_image_to_db
        # function since it is specific to image create
        image_values['updated_at'] = image.updated_at
        new_values = self.db_api.image_create(self.context, image_values)
        self.db_api.image_tag_set_all(self.context,
                                      image.image_id, image.tags)
        image.created_at = new_values['created_at']
        image.updated_at = new_values['updated_at']

    def save(self, image, from_state=None):
        image_values = self._format_image_to_db(image)
        if (image_values['size'] is not None
           and image_values['size'] > CONF.image_size_cap):
            raise exception.ImageSizeLimitExceeded
        try:
            new_values = self.db_api.image_update(self.context,
                                                  image.image_id,
                                                  image_values,
                                                  purge_props=True,
                                                  from_state=from_state)
        except (exception.ImageNotFound, exception.Forbidden):
            msg = _("No image found with ID %s") % image.image_id
            raise exception.ImageNotFound(msg)
        self.db_api.image_tag_set_all(self.context, image.image_id,
                                      image.tags)
        image.updated_at = new_values['updated_at']

    def remove(self, image):
        try:
            self.db_api.image_update(self.context, image.image_id,
                                     {'status': image.status},
                                     purge_props=True)
        except (exception.ImageNotFound, exception.Forbidden):
            msg = _("No image found with ID %s") % image.image_id
            raise exception.ImageNotFound(msg)
        # NOTE(markwash): don't update tags?
        new_values = self.db_api.image_destroy(self.context, image.image_id)
        image.updated_at = new_values['updated_at']


class ImageProxy(glance.domain.proxy.Image):

    def __init__(self, image, context, db_api):
        self.context = context
        self.db_api = db_api
        self.image = image
        super(ImageProxy, self).__init__(image)


class ImageMemberRepo(object):

    def __init__(self, context, db_api, image):
        self.context = context
        self.db_api = db_api
        self.image = image

    def _format_image_member_from_db(self, db_image_member):
        return glance.domain.ImageMembership(
            id=db_image_member['id'],
            image_id=db_image_member['image_id'],
            member_id=db_image_member['member'],
            status=db_image_member['status'],
            created_at=db_image_member['created_at'],
            updated_at=db_image_member['updated_at']
        )

    def _format_image_member_to_db(self, image_member):
        image_member = {'image_id': self.image.image_id,
                        'member': image_member.member_id,
                        'status': image_member.status,
                        'created_at': image_member.created_at}
        return image_member

    def list(self):
        db_members = self.db_api.image_member_find(
            self.context, image_id=self.image.image_id)
        image_members = []
        for db_member in db_members:
            image_members.append(self._format_image_member_from_db(db_member))
        return image_members

    def add(self, image_member):
        try:
            self.get(image_member.member_id)
        except exception.NotFound:
            pass
        else:
            msg = _('The target member %(member_id)s is already '
                    'associated with image %(image_id)s.') % {
                        'member_id': image_member.member_id,
                        'image_id': self.image.image_id}
            raise exception.Duplicate(msg)

        image_member_values = self._format_image_member_to_db(image_member)
        # Note(shalq): find the image member including the member marked with
        # deleted. We will use only one record to represent membership between
        # the same image and member. The record of the deleted image member
        # will be reused, if it exists, update its properties instead of
        # creating a new one.
        members = self.db_api.image_member_find(self.context,
                                                image_id=self.image.image_id,
                                                member=image_member.member_id,
                                                include_deleted=True)
        if members:
            new_values = self.db_api.image_member_update(self.context,
                                                         members[0]['id'],
                                                         image_member_values)
        else:
            new_values = self.db_api.image_member_create(self.context,
                                                         image_member_values)
        image_member.created_at = new_values['created_at']
        image_member.updated_at = new_values['updated_at']
        image_member.id = new_values['id']

    def remove(self, image_member):
        try:
            self.db_api.image_member_delete(self.context, image_member.id)
        except (exception.NotFound, exception.Forbidden):
            msg = _("The specified member %s could not be found")
            raise exception.NotFound(msg % image_member.id)

    def save(self, image_member, from_state=None):
        image_member_values = self._format_image_member_to_db(image_member)
        try:
            new_values = self.db_api.image_member_update(self.context,
                                                         image_member.id,
                                                         image_member_values)
        except (exception.NotFound, exception.Forbidden):
            raise exception.NotFound()
        image_member.updated_at = new_values['updated_at']

    def get(self, member_id):
        try:
            db_api_image_member = self.db_api.image_member_find(
                self.context,
                self.image.image_id,
                member_id)
            if not db_api_image_member:
                raise exception.NotFound()
        except (exception.NotFound, exception.Forbidden):
            raise exception.NotFound()

        image_member = self._format_image_member_from_db(
            db_api_image_member[0])
        return image_member


class TaskRepo(object):

    def __init__(self, context, db_api):
        self.context = context
        self.db_api = db_api

    def _format_task_from_db(self, db_task):
        return glance.domain.Task(
            task_id=db_task['id'],
            task_type=db_task['type'],
            status=db_task['status'],
            owner=db_task['owner'],
            expires_at=db_task['expires_at'],
            created_at=db_task['created_at'],
            updated_at=db_task['updated_at'],
            task_input=db_task['input'],
            result=db_task['result'],
            message=db_task['message'],
        )

    def _format_task_stub_from_db(self, db_task):
        return glance.domain.TaskStub(
            task_id=db_task['id'],
            task_type=db_task['type'],
            status=db_task['status'],
            owner=db_task['owner'],
            expires_at=db_task['expires_at'],
            created_at=db_task['created_at'],
            updated_at=db_task['updated_at'],
        )

    def _format_task_to_db(self, task):
        task = {'id': task.task_id,
                'type': task.type,
                'status': task.status,
                'input': task.task_input,
                'result': task.result,
                'owner': task.owner,
                'message': task.message,
                'expires_at': task.expires_at,
                'created_at': task.created_at,
                'updated_at': task.updated_at,
                }
        return task

    def get(self, task_id):
        try:
            db_api_task = self.db_api.task_get(self.context, task_id)
        except (exception.NotFound, exception.Forbidden):
            msg = _('Could not find task %s') % task_id
            raise exception.NotFound(msg)
        return self._format_task_from_db(db_api_task)

    def list(self, marker=None, limit=None, sort_key='created_at',
             sort_dir='desc', filters=None):
        db_api_tasks = self.db_api.task_get_all(self.context,
                                                filters=filters,
                                                marker=marker,
                                                limit=limit,
                                                sort_key=sort_key,
                                                sort_dir=sort_dir)
        return [self._format_task_stub_from_db(task) for task in db_api_tasks]

    def save(self, task):
        task_values = self._format_task_to_db(task)
        try:
            updated_values = self.db_api.task_update(self.context,
                                                     task.task_id,
                                                     task_values)
        except (exception.NotFound, exception.Forbidden):
            msg = _('Could not find task %s') % task.task_id
            raise exception.NotFound(msg)
        task.updated_at = updated_values['updated_at']

    def add(self, task):
        task_values = self._format_task_to_db(task)
        updated_values = self.db_api.task_create(self.context, task_values)
        task.created_at = updated_values['created_at']
        task.updated_at = updated_values['updated_at']

    def remove(self, task):
        task_values = self._format_task_to_db(task)
        try:
            self.db_api.task_update(self.context, task.task_id, task_values)
            updated_values = self.db_api.task_delete(self.context,
                                                     task.task_id)
        except (exception.NotFound, exception.Forbidden):
            msg = _('Could not find task %s') % task.task_id
            raise exception.NotFound(msg)
        task.updated_at = updated_values['updated_at']
        task.deleted_at = updated_values['deleted_at']


class MetadefNamespaceRepo(object):

    def __init__(self, context, db_api):
        self.context = context
        self.db_api = db_api

    def _format_namespace_from_db(self, namespace_obj):
        return glance.domain.MetadefNamespace(
            namespace_id=namespace_obj['id'],
            namespace=namespace_obj['namespace'],
            display_name=namespace_obj['display_name'],
            description=namespace_obj['description'],
            owner=namespace_obj['owner'],
            visibility=namespace_obj['visibility'],
            protected=namespace_obj['protected'],
            created_at=namespace_obj['created_at'],
            updated_at=namespace_obj['updated_at']
        )

    def _format_namespace_to_db(self, namespace_obj):
        namespace = {
            'namespace': namespace_obj.namespace,
            'display_name': namespace_obj.display_name,
            'description': namespace_obj.description,
            'visibility': namespace_obj.visibility,
            'protected': namespace_obj.protected,
            'owner': namespace_obj.owner
        }
        return namespace

    def add(self, namespace):
        self.db_api.metadef_namespace_create(
            self.context,
            self._format_namespace_to_db(namespace)
        )

    def get(self, namespace):
        try:
            db_api_namespace = self.db_api.metadef_namespace_get(
                self.context, namespace)
        except (exception.NotFound, exception.Forbidden):
            msg = _('Could not find namespace %s') % namespace
            raise exception.NotFound(msg)
        return self._format_namespace_from_db(db_api_namespace)

    def list(self, marker=None, limit=None, sort_key='created_at',
             sort_dir='desc', filters=None):
        db_namespaces = self.db_api.metadef_namespace_get_all(
            self.context,
            marker=marker,
            limit=limit,
            sort_key=sort_key,
            sort_dir=sort_dir,
            filters=filters
        )
        return [self._format_namespace_from_db(namespace_obj)
                for namespace_obj in db_namespaces]

    def remove(self, namespace):
        try:
            self.db_api.metadef_namespace_delete(self.context,
                                                 namespace.namespace)
        except (exception.NotFound, exception.Forbidden):
            msg = _("The specified namespace %s could not be found")
            raise exception.NotFound(msg % namespace.namespace)

    def remove_objects(self, namespace):
        try:
            self.db_api.metadef_object_delete_namespace_content(
                self.context,
                namespace.namespace
            )
        except (exception.NotFound, exception.Forbidden):
            msg = _("The specified namespace %s could not be found")
            raise exception.NotFound(msg % namespace.namespace)

    def remove_properties(self, namespace):
        try:
            self.db_api.metadef_property_delete_namespace_content(
                self.context,
                namespace.namespace
            )
        except (exception.NotFound, exception.Forbidden):
            msg = _("The specified namespace %s could not be found")
            raise exception.NotFound(msg % namespace.namespace)

    def remove_tags(self, namespace):
        try:
            self.db_api.metadef_tag_delete_namespace_content(
                self.context,
                namespace.namespace
            )
        except (exception.NotFound, exception.Forbidden):
            msg = _("The specified namespace %s could not be found")
            raise exception.NotFound(msg % namespace.namespace)

    def object_count(self, namespace_name):
        return self.db_api.metadef_object_count(
            self.context,
            namespace_name
        )

    def property_count(self, namespace_name):
        return self.db_api.metadef_property_count(
            self.context,
            namespace_name
        )

    def save(self, namespace):
        try:
            self.db_api.metadef_namespace_update(
                self.context, namespace.namespace_id,
                self._format_namespace_to_db(namespace)
            )
        except exception.NotFound as e:
            raise exception.NotFound(explanation=e.msg)
        return namespace


class MetadefObjectRepo(object):

    def __init__(self, context, db_api):
        self.context = context
        self.db_api = db_api
        self.meta_namespace_repo = MetadefNamespaceRepo(context, db_api)

    def _format_metadef_object_from_db(self, metadata_object,
                                       namespace_entity):
        required_str = metadata_object['required']
        required_list = required_str.split(",") if required_str else []

        # Convert the persisted json schema to a dict of PropertyTypes
        property_types = {}
        json_props = metadata_object['json_schema']
        for id in json_props:
            property_types[id] = json.fromjson(PropertyType, json_props[id])

        return glance.domain.MetadefObject(
            namespace=namespace_entity,
            object_id=metadata_object['id'],
            name=metadata_object['name'],
            required=required_list,
            description=metadata_object['description'],
            properties=property_types,
            created_at=metadata_object['created_at'],
            updated_at=metadata_object['updated_at']
        )

    def _format_metadef_object_to_db(self, metadata_object):

        required_str = (",".join(metadata_object.required) if
                        metadata_object.required else None)

        # Convert the model PropertyTypes dict to a JSON string
        properties = metadata_object.properties
        db_schema = {}
        if properties:
            for k, v in properties.items():
                json_data = json.tojson(PropertyType, v)
                db_schema[k] = json_data

        db_metadata_object = {
            'name': metadata_object.name,
            'required': required_str,
            'description': metadata_object.description,
            'json_schema': db_schema
        }
        return db_metadata_object

    def add(self, metadata_object):
        self.db_api.metadef_object_create(
            self.context,
            metadata_object.namespace,
            self._format_metadef_object_to_db(metadata_object)
        )

    def get(self, namespace, object_name):
        try:
            namespace_entity = self.meta_namespace_repo.get(namespace)
            db_metadata_object = self.db_api.metadef_object_get(
                self.context,
                namespace,
                object_name)
        except (exception.NotFound, exception.Forbidden):
            msg = _('Could not find metadata object %s') % object_name
            raise exception.NotFound(msg)
        return self._format_metadef_object_from_db(db_metadata_object,
                                                   namespace_entity)

    def list(self, marker=None, limit=None, sort_key='created_at',
             sort_dir='desc', filters=None):
        namespace = filters['namespace']
        namespace_entity = self.meta_namespace_repo.get(namespace)
        db_metadata_objects = self.db_api.metadef_object_get_all(
            self.context, namespace)
        return [self._format_metadef_object_from_db(metadata_object,
                                                    namespace_entity)
                for metadata_object in db_metadata_objects]

    def remove(self, metadata_object):
        try:
            self.db_api.metadef_object_delete(
                self.context,
                metadata_object.namespace.namespace,
                metadata_object.name
            )
        except (exception.NotFound, exception.Forbidden):
            msg = _("The specified metadata object %s could not be found")
            raise exception.NotFound(msg % metadata_object.name)

    def save(self, metadata_object):
        try:
            self.db_api.metadef_object_update(
                self.context, metadata_object.namespace.namespace,
                metadata_object.object_id,
                self._format_metadef_object_to_db(metadata_object))
        except exception.NotFound as e:
            raise exception.NotFound(explanation=e.msg)
        return metadata_object


class MetadefResourceTypeRepo(object):

    def __init__(self, context, db_api):
        self.context = context
        self.db_api = db_api
        self.meta_namespace_repo = MetadefNamespaceRepo(context, db_api)

    def _format_resource_type_from_db(self, resource_type, namespace):
        return glance.domain.MetadefResourceType(
            namespace=namespace,
            name=resource_type['name'],
            prefix=resource_type['prefix'],
            properties_target=resource_type['properties_target'],
            created_at=resource_type['created_at'],
            updated_at=resource_type['updated_at']
        )

    def _format_resource_type_to_db(self, resource_type):
        db_resource_type = {
            'name': resource_type.name,
            'prefix': resource_type.prefix,
            'properties_target': resource_type.properties_target
        }
        return db_resource_type

    def add(self, resource_type):
        self.db_api.metadef_resource_type_association_create(
            self.context, resource_type.namespace,
            self._format_resource_type_to_db(resource_type)
        )

    def get(self, resource_type, namespace):
        namespace_entity = self.meta_namespace_repo.get(namespace)
        db_resource_type = (
            self.db_api.
            metadef_resource_type_association_get(
                self.context,
                namespace,
                resource_type
            )
        )
        return self._format_resource_type_from_db(db_resource_type,
                                                  namespace_entity)

    def list(self, filters=None):
        namespace = filters['namespace']
        if namespace:
            namespace_entity = self.meta_namespace_repo.get(namespace)
            db_resource_types = (
                self.db_api.
                metadef_resource_type_association_get_all_by_namespace(
                    self.context,
                    namespace
                )
            )
            return [self._format_resource_type_from_db(resource_type,
                                                       namespace_entity)
                    for resource_type in db_resource_types]
        else:
            db_resource_types = (
                self.db_api.
                metadef_resource_type_get_all(self.context)
            )
            return [glance.domain.MetadefResourceType(
                namespace=None,
                name=resource_type['name'],
                prefix=None,
                properties_target=None,
                created_at=resource_type['created_at'],
                updated_at=resource_type['updated_at']
            ) for resource_type in db_resource_types]

    def remove(self, resource_type):
        try:
            self.db_api.metadef_resource_type_association_delete(
                self.context, resource_type.namespace.namespace,
                resource_type.name)

        except (exception.NotFound, exception.Forbidden):
            msg = _("The specified resource type %s could not be found ")
            raise exception.NotFound(msg % resource_type.name)


class MetadefPropertyRepo(object):

    def __init__(self, context, db_api):
        self.context = context
        self.db_api = db_api
        self.meta_namespace_repo = MetadefNamespaceRepo(context, db_api)

    def _format_metadef_property_from_db(
            self,
            property,
            namespace_entity):

        return glance.domain.MetadefProperty(
            namespace=namespace_entity,
            property_id=property['id'],
            name=property['name'],
            schema=property['json_schema']
        )

    def _format_metadef_property_to_db(self, property):

        db_metadata_object = {
            'name': property.name,
            'json_schema': property.schema
        }
        return db_metadata_object

    def add(self, property):
        self.db_api.metadef_property_create(
            self.context,
            property.namespace,
            self._format_metadef_property_to_db(property)
        )

    def get(self, namespace, property_name):
        try:
            namespace_entity = self.meta_namespace_repo.get(namespace)
            db_property_type = self.db_api.metadef_property_get(
                self.context,
                namespace,
                property_name
            )
        except (exception.NotFound, exception.Forbidden):
            msg = _('Could not find property %s') % property_name
            raise exception.NotFound(msg)
        return self._format_metadef_property_from_db(
            db_property_type, namespace_entity)

    def list(self, marker=None, limit=None, sort_key='created_at',
             sort_dir='desc', filters=None):
        namespace = filters['namespace']
        namespace_entity = self.meta_namespace_repo.get(namespace)

        db_properties = self.db_api.metadef_property_get_all(
            self.context, namespace)
        return (
            [self._format_metadef_property_from_db(
                property, namespace_entity) for property in db_properties]
        )

    def remove(self, property):
        try:
            self.db_api.metadef_property_delete(
                self.context, property.namespace.namespace, property.name)
        except (exception.NotFound, exception.Forbidden):
            msg = _("The specified property %s could not be found")
            raise exception.NotFound(msg % property.name)

    def save(self, property):
        try:
            self.db_api.metadef_property_update(
                self.context, property.namespace.namespace,
                property.property_id,
                self._format_metadef_property_to_db(property)
            )
        except exception.NotFound as e:
            raise exception.NotFound(explanation=e.msg)
        return property


class MetadefTagRepo(object):

    def __init__(self, context, db_api):
        self.context = context
        self.db_api = db_api
        self.meta_namespace_repo = MetadefNamespaceRepo(context, db_api)

    def _format_metadef_tag_from_db(self, metadata_tag,
                                    namespace_entity):
        return glance.domain.MetadefTag(
            namespace=namespace_entity,
            tag_id=metadata_tag['id'],
            name=metadata_tag['name'],
            created_at=metadata_tag['created_at'],
            updated_at=metadata_tag['updated_at']
        )

    def _format_metadef_tag_to_db(self, metadata_tag):
        db_metadata_tag = {
            'name': metadata_tag.name
        }
        return db_metadata_tag

    def add(self, metadata_tag):
        self.db_api.metadef_tag_create(
            self.context,
            metadata_tag.namespace,
            self._format_metadef_tag_to_db(metadata_tag)
        )

    def add_tags(self, metadata_tags):
        tag_list = []
        namespace = None
        for metadata_tag in metadata_tags:
            tag_list.append(self._format_metadef_tag_to_db(metadata_tag))
            if namespace is None:
                namespace = metadata_tag.namespace

        self.db_api.metadef_tag_create_tags(
            self.context, namespace, tag_list)

    def get(self, namespace, name):
        try:
            namespace_entity = self.meta_namespace_repo.get(namespace)
            db_metadata_tag = self.db_api.metadef_tag_get(
                self.context,
                namespace,
                name)
        except (exception.NotFound, exception.Forbidden):
            msg = _('Could not find metadata tag %s') % name
            raise exception.NotFound(msg)
        return self._format_metadef_tag_from_db(db_metadata_tag,
                                                namespace_entity)

    def list(self, marker=None, limit=None, sort_key='created_at',
             sort_dir='desc', filters=None):
        namespace = filters['namespace']
        namespace_entity = self.meta_namespace_repo.get(namespace)

        db_metadata_tag = self.db_api.metadef_tag_get_all(
            self.context, namespace, filters, marker, limit, sort_key,
            sort_dir)

        return [self._format_metadef_tag_from_db(metadata_tag,
                                                 namespace_entity)
                for metadata_tag in db_metadata_tag]

    def remove(self, metadata_tag):
        try:
            self.db_api.metadef_tag_delete(
                self.context,
                metadata_tag.namespace.namespace,
                metadata_tag.name
            )
        except (exception.NotFound, exception.Forbidden):
            msg = _("The specified metadata tag %s could not be found")
            raise exception.NotFound(msg % metadata_tag.name)

    def save(self, metadata_tag):
        try:
            self.db_api.metadef_tag_update(
                self.context, metadata_tag.namespace.namespace,
                metadata_tag.tag_id,
                self._format_metadef_tag_to_db(metadata_tag))
        except exception.NotFound as e:
            raise exception.NotFound(explanation=e.msg)
        return metadata_tag
