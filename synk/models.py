import md5
import simplejson
import sys
import logging
import time

from django.conf import settings

from google.appengine.ext import db

__all__ = ['User', 'Journal', 'FullJournalError']

def serialize(obj):
    start = time.time()
    out = simplejson.dumps(obj, separators=[',', ':'])
    if settings.PROFILING:
        logging.debug('serializing time: %f', time.time() - start)
    return out

def deserialize(obj):
    start = time.time()
    out = simplejson.loads(obj)
    if settings.PROFILING:
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

    def journals(self, since=0):
        journals = list(db.GqlQuery('select * from Journal where user = :1 and latest >= :2 order by latest desc', self, since))
        if len(journals) == 0:
            # always try to get at least 1
            journals = list(db.GqlQuery('select * from Journal where user = :1 order by latest desc limit 1', self))
        return journals

    @staticmethod
    def by_username(username):
        try:
            user = db.GqlQuery('select * from User where username = :1 limit 1', username)[0]
            return user
        except IndexError:
            return None

class FullJournalError(Exception):
    """Raised when the status is at its max_size already"""
    pass

class Journal(db.Model):
    user = db.ReferenceProperty(User)

    # the greatest and least last_changed of any item
    # in this Journal
    latest = db.IntegerProperty(default=0)
    earliest = db.IntegerProperty(default=sys.maxint)

    # serialized python dictionary mapping item id
    # to status key
    status_map_serialized = db.TextProperty(default='{}')
    status_map = None
    
    # max_size is based on max_len of 900000 bytes
    # with a constant per-entry size of 79 bytes
    # (this is true when serializing as JSON)
    max_size = 11000
    max_len = 900000
    fill_factor = db.FloatProperty()

    def __init__(self, *args, **kwargs):
        db.Model.__init__(self, *args, **kwargs)

        if self.status_map_serialized:
            self.status_map = deserialize(self.status_map_serialized)
            logging.debug("%d items, %d bytes, %f fill factor", len(self.status_map), len(self.status_map_serialized), self.fill_factor)
        else:
            self.status_map = {}

    def is_full(self):
        return settings.PROFILING and len(serialize(self.status_map)) >= self.max_len \
            or len(self.status_map) >= self.max_size

    def put(self):
        self.status_map_serialized = serialize(self.status_map)
        self.fill_factor = float(len(self.status_map_serialized)) / float(self.max_len)
        db.Model.put(self)
        if settings.PROFILING:
            logging.debug("%d items, %d bytes, %f fill factor", len(self.status_map), len(self.status_map_serialized), self.fill_factor)

    # implement dictionary protocol
    def __len__(self):
        return len(self.status_map)

    def __contains__(self, element):
        return (element in self.status_map)

    def __getitem__(self, key):
        return self.status_map[key]

    def __setitem__(self, key, value):
        if self.is_full():
            if settings.PROFILING:
                logging.warn('FullJournalException with %d items' % len(self.status_map))
            raise FullJournalException()

        last_changed = value['last_changed'] 
        if last_changed > self.latest:
            self.latest = last_changed
        if last_changed < self.earliest:
            self.earliest = last_changed

        self.status_map[key] = value

    def __delitem__(self, key):
        del self.status_map[key]

    def __iter__(self):
        return iter(self.status_map)

    def keys(self):
        return self.status_map.keys()

    def iterkeys(self):
        return self.status_map.iterkeys()

    def values(self):
        return self.status_map.values()

    def itervalues(self):
        return self.status_map.itervalues()

    def items(self):
        return self.status_map.items()

    def iteritems(self):
        return self.status_map.iteritems()

