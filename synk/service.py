import logging
import sys
import time
import types

import simplejson

from django.http import HttpResponse
from django.http import HttpResponseServerError

from google.appengine.ext.webapp import template

from synk.models import *

from synk.middleware import requires_digest_auth
from synk.middleware import allow_method


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

def JsonResponse(body=None, error=False, **kwargs):
    if body is None and kwargs:
        body = kwargs
    elif body is None:
        body = ''

    out = simplejson.dumps(body)

    if error:
        return HttpResponseServerError(out, 'text/json')
    else:
        return HttpResponse(out, 'text/json')

def validate_put_post(raw_body):
    # a valid PUT/POST body contains a JSON representation
    # of an array of objects. each object should contain
    # the following fields:
    #
    # timestamp (int)
    # 
    # each object may contain any number of other fields,
    # nested as deeply as desired, so long as the total
    # length of JSON of remaining objects is no greater
    # than 1k bytes

    def stringify(thing):
        if type(thing) == types.DictType:
            return dict([(stringify(key), stringify(value)) for key, value in thing.iteritems()])
        elif type(thing) == types.StringType:
            return thing
        elif type(thing) == types.UnicodeType:
            return str(thing)
        elif type(thing) == types.ListType:
            return [stringify(element) for element in thing]
        else:
            return thing

    try:
        items = simplejson.loads(raw_body)
    except:
        raise Exception('could not parse JSON')

    if type(items) != types.ListType:
        raise Exception('JSON top-level element was not an array')

    out = []

    for i, item in enumerate(items):
        if type(item) != types.DictType:
            raise Exception('item %d was not a JSON object' % i)

        if 'timestamp' not in item:
            raise Exception('item %d did not have "timestamp" field' % i)
        if type(item['timestamp']) not in (types.IntType, types.LongType):
            raise Exception('item %d did not have integer "timestamp" field' % i)

        if 'service' in item:
            raise Exception('item %d contained invalid key "service"' % i)
        if 'type' in item:
            raise Exception('item %d contained invalid key "type"' % i)
        
        data = dict(item)
        del data['timestamp']
        if len(serialize(data)) > 1024:
            raise Exception('item %d exceeds 1024 bytes of data' % i)

    return items


def log_request_time(view_func, logfunc=logging.info):
    def inner(request, *args, **kwargs):
        start = time.time()
        response = view_func(request, *args, **kwargs)
        logfunc("request time %s %s %f sec", request.method, request.path, time.time() - start)
        return response
    return inner
                

@allow_method('GET', 'POST')
@require_auth
@log_request_time
def events(request, service, type, since):
    user = request.user
    since = int(since)

    if type == 'all':
        type = None

    if request.method == 'POST' and (service is None or type is None):
        return JsonResponse('POST requests require service and type')

    if request.method == 'GET':
        out = []
        for journal in user.journals(service=service, type=type, last_timestamp=since):
            for item in journal:
                if since and item['timestamp'] < since:
                    continue
                item['service'] = journal.service
                item['type'] = journal.type
                out.append(item)
        
        return JsonResponse(out)

    elif request.method == 'POST':
        try:
            items = validate_put_post(request.raw_post_data)
        except Exception, e:
            return JsonResponse(mesage='Invalid JSON Schema', detail=str(e), error=True)

        items.sort(key=lambda item: item['timestamp'])

        try:
            last_journal = tuple(user.journals(service, type, limit=1))[0]
        except:
            last_journal = Journal()
            last_journal.user = user
            last_journal.service = service
            last_journal.type = type

        for item in items:
            try:
                last_journal.append(item)
            except JournalError, e:
                last_journal.put()
                last_journal = Journal()
                last_journal.user = user
                last_journal.service = service
                last_journal.type = type
                last_journal.append(item)

        last_journal.put()

        return JsonResponse('OK')

    return JsonResponse(message='Could not process request', error=True)

