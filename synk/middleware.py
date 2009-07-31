from django.http import HttpResponse
from django.http import HttpResponseNotAllowed

from authentication import HttpDigestAuthentication

def requires_digest_auth(realm, auth_callback, user_callback):
    """
    realm is the realm with which the user's digest password
    was saved. this should basically never change.

    auth_callback is called with two arugments: the and the
    authentication realm and the username, and which should
    return the md5 hash of the "<username>:<realm>:<password>"
    with appropriate substitutions

    user_callback is called only if the authentication process
    was successful, and is given the username as the only
    argument. it should return the user object.
    """
    def inner(view_func):
        setattr(view_func, 'requires_digest_auth', True)
        setattr(view_func, 'auth_callback', auth_callback)
        setattr(view_func, 'user_callback', user_callback)
        setattr(view_func, 'realm', realm)
        return view_func
    return inner

class DigestMiddleware(object):
    """
    Implement HTTP Digest authentication if requested by
    the view function (it will be wrapped by a decorator
    that indicates that authentication is necessary and
    which provides a callback (any callable) which gets
    the User object for a given username.
    """

    def process_view(self, request, view_func, view_args, view_kwargs):
        if getattr(view_func, 'requires_digest_auth', False):
            realm = getattr(view_func, 'realm', None)

            auth_callback = getattr(view_func, 'auth_callback', None)
            if auth_callback is None or realm is None:
                raise Exception('error!')

            user_callback = getattr(view_func, 'user_callback', None)
            if user_callback is None or realm is None:
                raise Exception('error!')

            authenticator = HttpDigestAuthentication(auth_callback, realm)
            if not authenticator.is_authenticated(request):
                response = HttpResponse('Authorization Required')
                challenge_headers = authenticator.challenge_headers()                 
                for k,v in challenge_headers.items():                                       
                    response[k] = v
                response.status_code = 401                                                  
                return response       

            # otherwise we authenticated
            method, auth = request.META['HTTP_AUTHORIZATION'].split(" ", 1)
            auth_dict = authenticator.get_auth_dict(auth)
            username = auth_dict['username']
            user = user_callback(username)
            setattr(request, 'user', user)

        # don't intercept
        return None

def allow_method(*methods):
    """
    decorator to indicate which methods are allowed to call
    a web service function. methods not allowed will get
    an HttpResponseNotAllowed (405) status.
    """
    def inner(view_func):
        setattr(view_func, 'has_allowed_methods', True)
        setattr(view_func, 'allowed_methods', methods)
        return view_func
    return inner

class AllowedMethodsMiddleware(object):
    """
    Middleware to enforce the @allow_method decorator constraint
    """

    def process_view(self, request, view_func, view_args, view_kwargs):
        if getattr(view_func, 'has_allowed_methods', False):
            allowed_methods = getattr(view_func, 'allowed_methods')
            if request.method not in allowed_methods:
                return HttpResponseNotAllowed(allowed_methods)

        return None
