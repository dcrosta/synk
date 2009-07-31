import sha
import random

from google.appengine.ext import db

__all__ = ['User', 'Group', 'Status']

letters = [l for l in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz01234567890']

def make_salt(length=32):
    salt = []
    for i in range(length):
        salt.append(random.choice(letters))
    return ''.join(salt)

class User(db.Model):
    username = db.StringProperty()
    password_hash = db.StringProperty()
    password_salt = db.StringProperty()

    def set_password(self, password):
        self.password_salt = make_salt()
        salted_password = self.password_salt + password
        self.password_hash = sha.new(salted_password).hexdigest()

    def authenticate(self, password):
        salted_password = self.password_salt + password
        return self.password_hash == sha.new(salted_password).hexdigest()

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

    def put(self):
        chars = set([l for l in self.id])
        if len(chars - Group.VALID_ID_CHARS) > 0:
            raise Exception('invalid group id')
        db.Model.put(self)

    @staticmethod
    def for_user(user):
        groups = db.GqlQuery('select * from Group where user = :1', user)
        return groups


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

