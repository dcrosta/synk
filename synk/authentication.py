#
# unceremoniously lifted and slightly modified  from the
# django-rest-interface project:
#    http://code.google.com/p/django-rest-interface/
#
# modifications were:
#    removed basic auth support
#    removed dependency on (and support for) gettext localization
#    removed `digest_password` method
#
# please see http://code.google.com/p/django-rest-interface/source/browse/trunk/README
# for authors, copyrights, and license terms for this file.
#

import md5, time, random

class HttpDigestAuthentication(object):
    """
    HTTP/1.1 digest authentication (RFC 2617).
    Uses code from the Python Paste Project (MIT Licence).
    """    
    def __init__(self, authfunc, realm='Restricted Access'):
        """
        authfunc:
            A user-defined function which takes a username and
            a realm as its first and second arguments respectively
            and returns the combined md5 hash of username,
            authentication realm and password.
        realm:
            An identifier for the authority that is requesting
            authorization
        """
        self.realm = realm
        self.authfunc = authfunc
        self.nonce    = {} # prevention of replay attacks

    def get_auth_dict(self, auth_string):
        """
        Splits WWW-Authenticate and HTTP_AUTHORIZATION strings
        into a dictionaries, e.g.
        {
            nonce  : "951abe58eddbb49c1ed77a3a5fb5fc2e"',
            opaque : "34de40e4f2e4f4eda2a3952fd2abab16"',
            realm  : "realm1"',
            qop    : "auth"'
        }
        """
        amap = {}
        for itm in auth_string.split(", "):
            (k, v) = [s.strip() for s in itm.split("=", 1)]
            amap[k] = v.replace('"', '')
        return amap

    def get_auth_response(self, http_method, fullpath, username, nonce, realm, qop, cnonce, nc):
        """
        Returns the server-computed digest response key.
        
        http_method:
            The request method, e.g. GET
        username:
            The user to be authenticated
        fullpath:
            The absolute URI to be accessed by the user
        nonce:
            A server-specified data string which should be 
            uniquely generated each time a 401 response is made
        realm:
            A string to be displayed to users so they know which 
            username and password to use
        qop:
            Indicates the "quality of protection" values supported 
            by the server.  The value "auth" indicates authentication.
        cnonce:
            An opaque quoted string value provided by the client 
            and used by both client and server to avoid chosen 
            plaintext attacks, to provide mutual authentication, 
            and to provide some message integrity protection.
        nc:
            Hexadecimal request counter
        """
        ha1 = self.authfunc(realm, username)
        ha2 = md5.md5('%s:%s' % (http_method, fullpath)).hexdigest()
        if qop:
            chk = "%s:%s:%s:%s:%s:%s" % (ha1, nonce, nc, cnonce, qop, ha2)
        else:
            chk = "%s:%s:%s" % (ha1, nonce, ha2)
        computed_response = md5.md5(chk).hexdigest()
        return computed_response
    
    def challenge_headers(self, stale=''):
        """
        Returns the http headers that ask for appropriate
        authorization.
        """
        nonce  = md5.md5(
            "%s:%s" % (time.time(), random.random())).hexdigest()
        opaque = md5.md5(
            "%s:%s" % (time.time(), random.random())).hexdigest()
        self.nonce[nonce] = None
        parts = {'realm': self.realm, 'qop': 'auth',
                 'nonce': nonce, 'opaque': opaque }
        if stale:
            parts['stale'] = 'true'
        head = ", ".join(['%s="%s"' % (k, v) for (k, v) in parts.items()])
        return {'WWW-Authenticate':'Digest %s' % head}
    
    def is_authenticated(self, request):
        """
        Checks whether a request comes from an authorized user.
        """
        # Make sure the request is a valid HttpDigest request
        if not request.META.has_key('HTTP_AUTHORIZATION'):
            return False
        fullpath = request.META['SCRIPT_NAME'] + request.META['PATH_INFO']
        (authmeth, auth) = request.META['HTTP_AUTHORIZATION'].split(" ", 1)
        if authmeth.lower() != 'digest':
            return False
        
        # Extract auth parameters from request
        amap = self.get_auth_dict(auth)
        try:
            username = amap['username']
            authpath = amap['uri']
            nonce    = amap['nonce']
            realm    = amap['realm']
            response = amap['response']
            assert authpath.split("?", 1)[0] in fullpath
            assert realm == self.realm
            qop      = amap.get('qop', '')
            cnonce   = amap.get('cnonce', '')
            nc       = amap.get('nc', '00000000')
            if qop:
                assert 'auth' == qop
                assert nonce and nc
        except:
            return False

        # Compute response key    
        computed_response = self.get_auth_response(request.method, fullpath, username, nonce, realm, qop, cnonce, nc)
        
        # Compare server-side key with key from client
        # Prevent replay attacks
        if not computed_response or computed_response != response:
            if nonce in self.nonce:
                del self.nonce[nonce]
            return False
        pnc = self.nonce.get(nonce,'00000000')
        if nc <= pnc:
            if nonce in self.nonce:
                del self.nonce[nonce]
            return False # stale = True
        self.nonce[nonce] = nc
        return True
    
