import md5
import random
import simplejson
import logging
import time

from django.conf import settings

from google.appengine.ext import db

__all__ = ['User', 'Group', 'Status', 'FullStatusError']

def serialize(obj):
    start = time.time()
    out = simplejson.dumps(obj, separators=[',', ':'])
    logging.debug('serializing time: %f', time.time() - start)
    return out

def deserialize(obj):
    start = time.time()
    out = simplejson.loads(obj)
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

    @staticmethod
    def by_username(username):
        try:
            user = db.GqlQuery('select * from User where username = :1 limit 1', username)[0]
            return user
        except IndexError:
            return None

class Group(db.Model):
    user = db.ReferenceProperty(User)

    # the first two characters of the key of
    # each item in the status_map (see Status)
    prefix = db.StringProperty()

    # total per-user capacity is 16 ** PREFIX_LEN * 11000 * 1000
    # ... so about 176M (with theoretical full capacity and no
    # key collisions... not sure if this is realistic)
    #
    # for users with smaller collections (probably most users)
    # setting this too high causes lots of datastore overhead
    # because we're forced to do a lot of looping in the
    # /status handler. leave it at 1 for now unless it
    # becomes apparent that this is limiting
    PREFIX_LEN = 1

    @staticmethod
    def for_user(user):
        start = time.time()
        groups = db.GqlQuery('select * from Group where user = :1', user)
        end = time.time()
        logging.debug("Group.for_user: %f", end - start)
        return groups

    @staticmethod
    def for_user_prefixes(user, prefixes):
        start = time.time()
        groups = db.GqlQuery('select * from Group where user = :1', user)
        groups = [group for group in groups if group.prefix in set(prefixes)]
        end = time.time()
        logging.debug("Group.for_user_prefixes: %f", end - start)
        return groups

    def get_statuses(self):
        start = time.time()
        statuses = db.GqlQuery('select * from Status where group = :1 order by fill_factor desc', self)
        end = time.time()
        logging.debug("Group.get_statuses: %f", end - start)
        return [s for s in statuses]

class Status(db.Model):
    STATUS_UNREAD = 0
    STATUS_READ = 1
    
    STATUS_MAP = {}
    STATUS_MAP['unread'] = STATUS_UNREAD
    STATUS_MAP['read'] = STATUS_READ

    INVERSE_STATUS_MAP = dict([(value, key) for key, value in STATUS_MAP.iteritems()])
    STATUS_VALUES = set(STATUS_MAP.values())

    group = db.ReferenceProperty(Group)

    # serialized python dictionary mapping item id
    # to status key
    status_map_serialized = db.TextProperty()
    status_map = None
    
    # max_size is based on max_len of 900000 bytes
    # with a constant per-entry size of 79 bytes
    # (this is true when serializing as JSON)
    max_size = 11000
    max_len = 900000
    fill_factor = db.FloatProperty()

    def init_status_map(self):
        if self.status_map is None and self.status_map_serialized:
            self.status_map = deserialize(self.status_map_serialized)
            logging.debug("%d items, %d bytes, %f fill factor", len(self.status_map), len(self.status_map_serialized), self.fill_factor)
        elif self.status_map is None:
            self.status_map = {}

    def has_item(self, id):
        self.init_status_map()
        return id in self.status_map

    def get_item(self, id):
        self.init_status_map()
        try:
            return self.status_map[id]
        except KeyError:
            return None

    def is_full(self):
        return settings.PROFILING and len(serialize(self.status_map)) >= self.max_len \
            or len(self.status_map) >= self.max_size

    def set_item(self, id, value):
        self.init_status_map()
        if not self.has_item(id) and self.is_full():
            logging.warn("raising FullStatusError with %d items", len(self.status_map))
            raise FullStatusError('Status is full')
        self.status_map[id] = value

    def del_item(self, id):
        self.init_status_map()
        del self.status_map[id]

    def put(self):
        self.status_map_serialized = serialize(self.status_map)
        self.fill_factor = float(len(self.status_map_serialized)) / float(self.max_len)
        db.Model.put(self)
        if settings.PROFILING:
            logging.debug("%d items, %d bytes, %f fill factor", len(self.status_map), len(self.status_map_serialized), self.fill_factor)

class FullStatusError(Exception):
    """Raised when the status is at its max_size already"""
    pass
