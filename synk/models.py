import types
import md5
import pickle
import logging
import time

from django.conf import settings

from google.appengine.ext import db

__all__ = ['User', 'Journal', 'JournalError', 'serialize', 'deserialize']

def serialize(obj):
    start = time.time()
    out = pickle.dumps(obj)
    logging.debug('serializing time: %f', time.time() - start)
    return out

def deserialize(obj):
    start = time.time()
    out = pickle.loads(obj)
    logging.debug('deserializing time: %f', time.time() - start)
    return out

class User(db.Model):
    username = db.StringProperty()
    password_hash = db.StringProperty()

    # pretend to be a property
    realm = 'Synk'

    def set_password(self, password):
        # HTTP digest user-realm-pass hash
        a1 = '%s:%s:%s' % (self.username, self.realm, password)
        ha1 = md5.new(a1)
        self.password_hash = ha1.hexdigest()

    def journals(self, service=None, type=None, last_timestamp=None, limit=''):
        # get journals, optionally filtering by service, type,
        # or last_timestamp (using >= for last_timestamp)
        args = [self]
        predicate = []
        i = 2 # start at 2, since :1 will always be user

        values = locals()
        for filter in ('service', 'type', 'last_timestamp'):
            value = values[filter]
            if value is not None:
                args.append(value)
                if filter == 'last_timestamp':
                    predicate.append('%s >= :%d' % (filter, i))
                else:
                    predicate.append('%s = :%d' % (filter, i))
                i += 1

        if predicate:
            predicate = ' and ' + ' and '.join(predicate)
        
        if limit is not '':
            limit = ' limit %d' % limit

        query = 'select * from Journal where user = :1 %s order by last_timestamp desc %s' % (predicate, limit)
        journals = db.GqlQuery(query, *args)
        return journals

    @staticmethod
    def by_username(username):
        try:
            user = db.GqlQuery('select * from User where username = :1 limit 1', username)[0]
            return user
        except IndexError:
            return None

class JournalError(Exception):
    """Raised when the status is at its max_size already"""
    pass

class Journal(db.Model):
    user = db.ReferenceProperty(User)

    # e.g. "rss"
    service = db.StringProperty()

    # e.g. "article" or "browser"
    type = db.StringProperty()
    
    # timestamp of the latest event in the Journal
    #
    # note that due to an optimization in __delitem__,
    # this value is always >= the last timestamp, but
    # is never less than the last timestamp
    last_timestamp = db.IntegerProperty()

    # serialized python dictionary mapping item id
    # to status key
    events_serialized = db.BlobProperty(default=None)
    events = None
    
    # maximum number of elements per Journal
    max_size = 2000 

    size = db.IntegerProperty()
    count = db.IntegerProperty()
    fill_factor = db.FloatProperty()

    def __init__(self, *args, **kwargs):
        db.Model.__init__(self, *args, **kwargs)

        if self.events_serialized:
            self.events = deserialize(self.events_serialized)
        else:
            self.events = []

    def is_full(self):
        return len(self.events) >= self.max_size

    def put(self):
        # sort before saving
        self.events.sort(key=lambda item: item['timestamp'])

        self.events_serialized = serialize(self.events)

        self.size = len(self.events_serialized)
        self.count = len(self.events)
        self.fill_factor = float(self.size) / 900000.0

        db.Model.put(self)

    def _check_value_for_add(self, value):
        # check some costraints, and update
        # the last_timestamp property before
        # inserting/updating/appending
        if type(value) != types.DictType:
            # don't expect this to happen ever, really
            raise JournalError('journal elements must be dictionaries')

        if self.is_full():
            raise JournalError('journal is already full')

        if 'timestamp' in value and value['timestamp'] > self.last_timestamp:
            self.last_timestamp = value['timestamp']


    # implement sequence protocol
    def __len__(self):
        return len(self.events)

    def __contains__(self, element):
        return (element in self.events)

    def __getitem__(self, key):
        return self.events[key]

    def __setitem__(self, key, value):
        self._check_value_for_add(value)
        self.events[key] = value

    def insert(self, index, value):
        self._check_value_for_add(value)
        self.events.insert(index, value)

    def append(self, value):
        self._check_value_for_add(value)
        self.events.append(value)

    def __delitem__(self, key):
        del self.events[key]

    def __iter__(self):
        return iter(self.events)

