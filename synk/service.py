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

    if error:
        return HttpResponseServerError(simplejson.dumps(out), 'text/json')
    else:
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
    # if everything is valid, returns the earliest
    # last_changed that was present in the input

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

    earliest = sys.maxint
    for i, item in enumerate(jsonobj):
        try:
            assert type(item) == types.DictType
            validate_item(item)
            if item['last_changed'] < earliest:
                earliest = item['last_changed']
        except AssertionError:
            raise InvalidSchemaError('item %d' % (i + 1))
        except InvalidSchemaError:
            raise

    return earliest

def log_request_time(view_func, logfunc=logging.info):
    def inner(request, *args, **kwargs):
        start = time.time()
        response = view_func(request, *args, **kwargs)
        logfunc("request time %s %s %f sec", request.method, request.path, time.time() - start)
        return response
    return inner
                

@allow_method('GET', 'PUT', 'POST', 'DELETE')
@require_auth
@log_request_time
def status(request, since):
    user = request.user

    if request.method in ('GET'):
        since = int(since)
        out = []
        for journal in reversed(user.journals(since=since)):
            for id, item in journal.iteritems():
                item['id'] = id
                out.append(item)
        
        return JsonResponse(out)

    elif request.method in ('PUT', 'POST'):
        # put a new status item or group of stauts items,
        # and return a confirmation for each along with its
        # modified date
        try:
            items = simplejson.loads(request.raw_post_data)
        except:
            return JsonResponse('Could not parse JSON in PUT body', error=True)

        try:
            earliest = validate_schema(items)
        except InvalidSchemaError, e:
            return JsonResponse('Invalid format for PUT body: %s' % e.message, error=True)

        journals = user.journals(since=earliest)

        # first update existing items
        items_updated = 0
        for journal in journals:
            remaining = []
            for item in items:
                id = item['id']
                if id in journal:
                    if journal[id]['last_changed'] < item['last_changed']:
                        del item['id']
                        journal[id] = item
                        items_updated += 1
                    # else the existing one is newer, so skip this
                else:
                    remaining.append(item)
            items = remaining

        # then add items to the first journal
        items_added = len(items)
        try:
            first = journals[0]
        except IndexError:
            first = Journal()
            first.user = user
            journals.append(first)

        for item in items:
            id = item['id']
            del item['id']

            try:
                first[id] = item
            except FullJournalError:
                first = Journal()
                first.user = user
                journals.insert(0, first)
                first[id] = item

        for journal in journals:
            journal.put()

        logging.info("added %d, updated %d", items_added, items_updated)

    elif request.method == 'DELETE':
        # delete accepts a list of item IDs
        try:
            item_ids = simplejson.loads(request.raw_post_data)
        except:
            return JsonResponse('Could not parse JSON in PUT body', error=True)

        for i, id in enumerate(item_ids):
            if not type(id) in types.StringTypes or len(id) != 32:
                return JsonResponse('Invalid format for DELETE body: item %d must be 32-char string' % i, error=True)

        journals = user.journals()

        # first update existing items
        items_updated = 0
        for journal in journals:
            for id in item_ids:
                try:
                    del journal[id]
                except KeyError:
                    pass

        for journal in journals:
            journal.put()

        logging.info("deleted %d", len(item_ids))

    return JsonResponse('OK')
