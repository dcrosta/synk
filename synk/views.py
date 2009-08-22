import logging
import time
import types

import simplejson

from django.http import HttpResponse
from django.http import HttpResponseForbidden
from django.http import HttpResponseRedirect
from django.http import QueryDict
from django.core.urlresolvers import reverse

from google.appengine.ext.webapp import template

from synk.models import *
from synk.forms import UserForm

from synk.middleware import requires_digest_auth
from synk.middleware import allow_method


def render(request, template_filename, **kwargs):
    template_filename = 'synk/templates/' + template_filename
    return HttpResponse(template.render(template_filename, kwargs))

def msg(message, error=False):
    return simplejson.dumps({'error': error, 'message': message})

def authenticate_user(realm, username):
    u = User.by_username(username)
    if u is None:
        return ''
    return u.password_hash

def get_user(username):
    u = User.by_username(username)
    return u

def require_auth(func):
    decorator_wrapper = requires_digest_auth(realm=User.realm, auth_callback=authenticate_user, user_callback=get_user)
    return decorator_wrapper(func)

def JsonResponse(body=None, message=None, error=False):
    if body is None and message is None and error == False:
        raise Exception('JsonResponse() requires at least one argument')

    if message is None and error is False:
        out = body
    else:
        out = {}
        if message is not None:
            out['message'] = message
        if body is not None:
            out['body'] = body
        out['error'] = error

    return HttpResponse(simplejson.dumps(out), 'text/json')

class InvalidSchemaError(Exception):
    """JSON sent in a PUT or POST did not conform to the expected schema"""
    pass

VALID_ID_CHARS = set([l for l in 'abcdef0123456789'])
def validate_schema(jsonobj):
    # it should be a flat list of
    # dictionaries, no nesting. each dict
    # should have keys 'status' (1 or 0),
    # 'id' (32 characters in [0-9a-f]), and
    # 'last_changed', a UNIX timestamp assumed
    # to be in UTC time zone
    #
    # if everything is valid, returns a dict
    # of lists, partitioned by item prefix

    def validate_item(item):
        keys = item.keys()

        if len(keys) != 3:
            raise InvalidSchemaError("expected 3 keys, found: %s" % repr(keys))
        
        for key in ('id', 'status', 'last_changed'):
            if key not in keys:
                raise InvalidSchemaError("expected key '%s' (not found)" % key)

        if type(item['id']) not in types.StringTypes:
            raise InvalidSchemaError("value for key 'id' must be a string")
        if len(item['id']) != 32:
            raise InvalidSchemaError("value for key 'id' must 32 characters long")
        if len(set([l for l in item['id']]) - VALID_ID_CHARS) != 0:
            raise InvalidSchemaError("value for key 'id' must contain only the characters [0-9a-f]")

        if type(item['status']) not in (types.IntType, types.LongType):
            raise InvalidSchemaError("value for key 'status' must be an integer (got %s)" % type(item['status']))

        if type(item['last_changed']) not in (types.IntType, types.LongType):
            raise InvalidSchemaError("value for key 'last_changed' must be an integer")

    out = {}

    for i, item in enumerate(jsonobj):
        try:
            assert type(item) == types.DictType
            validate_item(item)
        except AssertionError:
            raise InvalidSchemaError('item %d' % (i + 1))
        except InvalidSchemaError:
            raise
        
        prefix = item['id'][:Group.PREFIX_LEN]
        
        if prefix not in out:
            out[prefix] = []
        out[prefix].append(item)

    return out





# HTML VIEW METHODS

def index(request):
    return render(request, 'index.html')

def register(request):
    form = UserForm()

    if request.method == 'POST':
        form = UserForm(request.POST)
        if form.is_valid():
            u = User()
            u.username = request.POST['username']
            u.set_password(request.POST['password'])
            u.put()

            return HttpResponseRedirect('/')
    
    return render(request, 'register.html',
            form=form,
            form_action=reverse('synk.views.register'),
            submit_button='Register',
            )

def dev(request):
    return render(request, 'dev.html')


# API VIEW METHODS

@allow_method('GET', 'PUT', 'POST', 'DELETE')
@require_auth
def status(request):
    start = time.time()

    user = request.user
    response = JsonResponse(message='OK')

    if request.method in ('GET'):
        groups = Group.for_user(user)
        out = []
        for group in groups:
            for status in group.get_statuses():
                status.init_status_map()
                for id, data in status.status_map.iteritems():
                    data['id'] = id
                    out.append(data)

        response = JsonResponse(out)

    elif request.method in ('PUT', 'POST'):
        # put a new status item or group of stauts items,
        # and return a confirmation for each along with its
        # modified date
        try:
            jsonobj = simplejson.loads(request.raw_post_data)
        except:
            response = JsonResponse('Could not parse JSON in PUT body', error=True)

        try:
            partitioned = validate_schema(jsonobj)
        except InvalidSchemaError, e:
            response = JsonResponse('Invalid format for PUT body: %s' % e.message, error=True)

        groups = Group.for_user_prefixes(user, partitioned.keys())
        groups_by_prefix = {}
        for group in groups:
            groups_by_prefix[group.prefix] = group

        mod_count = 0

        for prefix, items in partitioned.iteritems():
            if prefix not in groups_by_prefix:
                group = Group()
                group.user = user
                group.prefix = prefix
                group.put()
                groups_by_prefix[prefix] = group
            else:
                group = groups_by_prefix[prefix]

            statuses = group.get_statuses()
            modified_statuses = set()

            # for each item, see if it already exists,
            # then update or insert as appropriate
            for item in items:
                item_id = item['id']

                found = False
                for status in statuses:
                    del item['id']

                    existing_item = status.get_item(item_id)
                    if existing_item is not None and item['last_changed'] > existing_item['last_changed']:
                        status.set_item(item_id, item)
                        mod_count += 1
                        modified_statuses.add(status)
                        continue
                    elif existing_item:
                        # existing item is newer, so just move on
                        continue

                # if we didn't find and update an existing item,
                # then insert it into the last (least-full) status
                try:
                    statuses[-1].set_item(item_id, item)
                    modified_statuses.add(statuses[-1])
                except (FullStatusError, IndexError), e:
                    newstatus = Status()
                    newstatus.group = group
                    newstatus.set_item(item_id, item)
                    statuses.append(newstatus)
                    modified_statuses.add(newstatus)
                mod_count += 1

            for status in modified_statuses:
                status.put()

            logging.info("modified %d items in %d statuses", mod_count, len(modified_statuses))

    elif request.method == 'DELETE':
        # delete items with the given ids. expect a flat
        # JSON list of item IDs
        try:
            jsonobj = simplejson.loads(request.raw_post_data)
        except:
            response = JsonResponse('Could not parse JSON in PUT body', error=True)

        partitioned = {}
        for id in jsonobj:
            if len(id) == 32 and len(set([l for l in id]) - VALID_ID_CHARS) == 0:
                prefix = id[:Group.PREFIX_LEN]
                if prefix not in partitioned:
                    partitioned[prefix] = []
                partitioned[prefix].append(id)

        groups = Group.for_user_prefixes(user, partitioned.keys())
        groups_by_prefix = {}
        for group in groups:
            groups_by_prefix[group.prefix] = group

        for prefix, ids_to_delete in partitioned.iteritems():
            if prefix not in groups_by_prefix:
                # we don't know about these ids, so skip them
                continue
            group = groups_by_prefix[prefix]
            statuses = group.get_statuses()

            for status in statuses:
                if status.has_item(id):
                    status.del_item(id)
                    break

            for status in statuses:
                status.put()


    end = time.time()
    logging.info("request time %s %s %f sec", request.method, request.path, end - start)

    return response

