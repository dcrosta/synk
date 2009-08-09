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
        assert len(keys) == 3
        assert 'id' in keys
        assert 'status' in keys
        assert 'last_changed' in keys

        assert type(item['id']) in types.StringTypes
        assert len(item['id']) == 32
        assert len(set([l for l in item['id']]) - VALID_ID_CHARS) == 0

        assert item['status'] in Status.STATUS_VALUES

        assert type(item['last_changed']) == types.IntType

    out = {}

    for i, item in enumerate(jsonobj):
        try:
            assert type(item) == types.DictType
            validate_item(item)
        except AssertionError:
            raise InvalidSchemaError('item %d' % (i + 1))
        
        prefix = item['id'][:2]
        
        if prefix not in out:
            out[prefix] = []
        out[prefix].append(item)

    return out





# HTML VIEW METHODS

def index(request):
    return render(request, 'hello.html')

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


# API VIEW METHODS

@allow_method('GET', 'PUT', 'POST', 'DELETE')
@require_auth
def status(request):
    user = request.user

    if request.method in ('GET'):
        groups = Group.for_user(user)
        out = []
        for group in groups:
            for status in group.get_statuses():
                status.init_status_map()
                for id, data in status.status_map.iteritems():
                    data['id'] = id
                    out.append(data)

        return JsonResponse(out)

    elif request.method in ('PUT', 'POST'):
        # put a new status item or group of stauts items,
        # and return a confirmation for each along with its
        # modified date

        try:
            jsonobj = simplejson.loads(request.raw_post_data)
        except:
            return JsonResponse('Could not parse JSON in PUT body', error=True)

        try:
            partitioned = validate_schema(jsonobj)
        except InvalidSchemaError, e:
            return JsonResponse('Invalid format for PUT body', error=True)

        groups = Group.for_user_prefixes(user, partitioned.keys())
        groups_by_prefix = {}
        for group in groups:
            groups_by_prefix[group.prefix] = group

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

            # for each item, see if it already exists,
            # then update or insert as appropriate
            for item in items:
                item_id = item['id']
                item_data = dict(item)

                found = False
                for status in statuses:
                    del item_data['id']

                    if status.has_item(item_id):
                        found = True
                        status.set_item(item_id, item_data)
                        break

                if not found:
                    try:
                        statuses[-1].set_item(item_id, item_data)
                    except (FullStatusError, IndexError), e:
                        newstatus = Status()
                        newstatus.group = group
                        newstatus.set_item(item_id, item_data)
                        newstatus.put()
                        statuses.append(newstatus)

            for status in statuses:
                status.put()

        return JsonResponse(message='OK')

    elif request.method == 'DELETE':
        # delete items with the given ids. expect a flat
        # JSON list of item IDs
        try:
            jsonobj = simplejson.loads(request.raw_post_data)
        except:
            return JsonResponse('Could not parse JSON in PUT body', error=True)

        partitioned = {}
        for id in jsonobj:
            if len(id) == 32 and len(set([l for l in id]) - VALID_ID_CHARS) == 0:
                prefix = id[:2]
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

        return JsonResponse(message='OK')

