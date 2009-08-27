import md5
import time
import types
import unittest
import urllib

import httplib2
import simplejson

def register(username='user', password='password', host='localhost', port='8000'):
    h = httplib2.Http()
    url = 'http://%s:%s/register' % (host, port)
    data = urllib.urlencode({'username': username, 'password': password})
    headers, response = h.request(url, method='POST', body=data)
    if headers['status'] != '302':
        # 302 means we redirected after post, and successfully registered
        raise Exception('could not register user\n\n%s' % headers)

def Item(id, status, last_changed_diff):
    # last_changed_diff is an offset from time.time()
    return {'id': md5.new(str(id)).hexdigest(),
            'status': status,
            'last_changed': int(time.time() + last_changed_diff)}

class SynkRig(object):

    def __init__(self, items, last_run=0, host='localhost', port='8000', username='user', password='password'):
        self.items = items
        self.last_run = last_run
        self.url = 'http://%s:%s/status' % (host, port)
        self.conn = httplib2.Http()

        self.conn.add_credentials(username, password)

        # make items a dict
        if type(self.items) in (types.ListType, types.TupleType):
            items = {}
            for item in self.items:
                items[item['id']] = item
            self.items = items

    def get(self):
        """
        update the local items store from the server
        """
        headers, response = self.conn.request(self.url, method='GET')
        if not headers['status'] == '200':
            raise Exception('Error during GET\n%s\n\n%s' % (headers, response))
        self.last_run = time.time()
        json = simplejson.loads(response)

        additions = 0
        updates = 0

        for item in json:
            if not item['id'] in self.items:
                self.items[item['id']] = item
                additions += 1
                continue
            existing_item = self.items[item['id']]
            if item['last_changed'] > existing_item['last_changed']:
                self.items[item['id']] = item
                updates += 1

        return additions, updates

    def post(self):
        json = simplejson.dumps(self.items.values())
        headers, response = self.conn.request(self.url, method='POST', body=json)

        if headers['status'] != '200':
            raise Exception('Error during POST\n%s\n\n%s' % (headers, response))

    def delete(self):
        json = simplejson.dumps(self.items.keys())
        headers, response = self.conn.request(self.url, method='DELETE', body=json)

        if headers['status'] != '200':
            raise Exception('Error during DELETE\n%s\n\n%s' % (headers, response))

class TestBasicCase(unittest.TestCase):

    def test_gets_downloads(self):
        register('user1')
        a = SynkRig([
                    Item(1, 1, -3600),
                    Item(2, 1, -3400),
                    Item(3, 0, -3300),
        ], username='user1')
        a.post()

        b = SynkRig([
                    Item(1, 1, -3800),
                    Item(2, 1, -3600),
                    Item(3, 0, -3600),
                    Item(4, 0, -1000),
        ], username='user1')
        b.post()

        self.assertEqual((0, 3), b.get())

        self.assertEqual((1, 0), a.get())

        self.assertEqual((0, 0), a.get())
        self.assertEqual((0, 0), b.get())

        b.delete()


if __name__ == '__main__':
    unittest.main()
