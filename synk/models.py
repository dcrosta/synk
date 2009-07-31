import md5
import random

from google.appengine.ext import db

__all__ = ['User', 'Group', 'Status']

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
    VALID_ID_CHARS = set([l for l in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'])

    user = db.ReferenceProperty(User)

    # unique identifier of this Group,
    # usually a hash or GUID
    id = db.StringProperty()
    name = db.StringProperty()

    def put(self):
        if self.id is None:
            self.id = Group.id_for_name(self.name)
        db.Model.put(self)

    @staticmethod
    def id_for_name(name):
        return md5.new(name).hexdigest()

    @staticmethod
    def for_user(user):
        groups = db.GqlQuery('select * from Group where user = :1', user)
        return groups

    @staticmethod
    def by_id(user, group_id):
        try:
            group = db.GqlQuery('select * from Group where id = :1 and user = :2', group_id, user)[0]
            return group
        except IndexError:
            return None

    def to_dict(self):
        return {'id': self.id, 'name': self.name}



class Status(db.Model):
    group = db.ReferenceProperty(Group)

    # pickled python dictionary mapping status
    # keys to status names
    _status_key = db.TextProperty()

    # pickled python dictionary mapping item id
    # to status key
    _status_map = db.TextProperty()

    def get_status_map(self):
        status_map = {}
        for id, status in self._status_map.iteritems():
            status = self._status_key.get(status, '_UNKNOWN_')
            status_map[id] = status
        return status_map

    def set_status_map(self, status_map):
        # `status_map` is a dictionary mapping
        # item ids (usually hashes or some sort
        # of GUID) to status strings
        status_id = 1
        status_key = {}
        status_map = {}
        for id, status in status_map.iteritems():
            if status in status_key:
                status = status_key[status]
            else:
                status_key[status] = status_id
                status = status_id
                status_id += 1
            status_map[id] = status
        self._status_key = status_key
        self._status_map = status_map

