import md5
import random
import pickle

from google.appengine.ext import db

__all__ = ['User', 'Group', 'Status', 'FullStatusError']

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
        groups = db.GqlQuery('select * from Group where user = :1', user)
        return groups

    @staticmethod
    def for_user_prefix(user, prefix):
        try:
            group = db.GqlQuery('select * from Group where prefix = :1 and user = :2', prefix, user)[0]
            return group
        except IndexError:
            return None

    @staticmethod
    def for_user_prefixes(user, prefixes):
        groups = db.GqlQuery('select * from Group where prefix in :1 and user = :2', prefixes, user)
        return groups

    def get_statuses(self):
        statuses = db.GqlQuery('select * from Status where group = :1 order by fill_factor desc', self)
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

    # pickled python dictionary mapping item id
    # to status key
    status_map_pickle = db.TextProperty()
    status_map = None
    
    max_size = 10000
    fill_factor = db.FloatProperty()

    def init_status_map(self):
        if self.status_map is None:
            if self.status_map_pickle:
                self.status_map = pickle.loads(self.status_map_pickle)
            else:
                self.status_map = {}

    def has_item(self, id):
        self.init_status_map()
        return id in self.status_map

    def get_item(self, id):
        self.init_status_map()
        return self.status_map[id]

    def set_item(self, id, value):
        self.init_status_map()
        if not self.has_item(id) and len(self.status_map) >= self.max_size:
            raise FullStatusError('Status is full')
        self.status_map[id] = value

    def del_item(self, id):
        self.init_status_map()
        del self.status_map[id]

    def put(self):
        self.status_map_pickle = pickle.dumps(self.status_map)
        self.fill_factor = float(len(self.status_map_pickle)) / float(self.max_size)
        db.Model.put(self)

class FullStatusError(Exception):
    """Raised when the status is at its max_size already"""
    pass
