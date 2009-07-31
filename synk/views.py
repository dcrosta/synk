import simplejson

from django.http import HttpResponse
from django.http import HttpResponseForbidden
from django.http import HttpResponseRedirect
from django.http import QueryDict
from django.core.urlresolvers import reverse

from google.appengine.ext.webapp import template

from synk.models import *
from synk.forms import UserForm

from synk.middleware import requires_digest_auth
from synk.middleware import allow_method


def render(request, template_filename, **kwargs):
    template_filename = 'synk/templates/' + template_filename
    return HttpResponse(template.render(template_filename, kwargs))

def msg(message, error=False):
    return simplejson.dumps({'error': error, 'message': message})

def err(message):
    return msg(message, True)

def authenticate_user(realm, username):
    u = User.by_username(username)
    if u is None:
        return ''
    return u.password_hash

def get_user(username):
    u = User.by_username(username)
    return u


def index(request):
    return render(request, 'hello.html')

def register(request):
    form = UserForm()

    if request.method == 'POST':
        form = UserForm(request.POST)
        if form.is_valid():
            u = User()
            u.username = request.POST['username']
            u.set_password(request.POST['password'])
            u.put()

            return HttpResponseRedirect('/')
    
    return render(request, 'register.html',
            form=form,
            form_action=reverse('synk.views.register'),
            submit_button='Register',
            )

def login(request):
    form = LoginForm()
    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            request.session['username'] = request.POST['username']
            request.session.save()
            return HttpResponseRedirect(reverse('synk.views.user_home', args=[request.POST['username']]))

    return render(request, 'login.html',
            form=form,
            form_action=reverse('synk.views.login'),
            submit_button='Login',
            )

@allow_method('GET')
@requires_digest_auth(realm=User.realm, auth_callback=authenticate_user, user_callback=get_user)
def group_index(request):
    user = request.user

    groups = [x for x in Group.for_user(user)]

    if not groups:
        g = Group()
        g.name = 'Daring Fireball'
        g.user = user
        g.put()

        g = Group()
        g.name = 'Coding Horror'
        g.user = user
        g.put()

        g = Group()
        g.name = 'Joel on Software'
        g.user = user
        g.put()

        groups = [g for g in Group.for_user(user)]

    json = simplejson.dumps([g.to_dict() for g in groups])

    return HttpResponse(json, 'text/json')

@allow_method('GET', 'PUT', 'POST', 'DELETE', 'HEAD')
@requires_digest_auth(realm=User.realm, auth_callback=authenticate_user, user_callback=get_user)
def group(request, group_id):
    user = request.user
    group = Group.by_id(user, group_id)

    if request.method in ('GET', 'HEAD'):
        if group is None:
            return HttpResponse(err('A group with id "%s" does not exist.' % group_id), 'text/json')
        json = simplejson.dumps(group.to_dict())
        return HttpResponse(json, 'text/json')

    elif request.method == 'PUT':
        PUT = QueryDict(request.raw_post_data)
        if 'name' not in PUT:
            return HttpResponse(err('Need "name" parameter'), 'text/json')

        name = PUT['name']
        group = Group.by_id(user, Group.id_for_name(name))
        if group is not None:
            return HttpResponse(err('A group with name "%s" already exists' % name), 'text/json')

        group = Group()
        group.user = user
        group.name = name
        group.put()

        return HttpResponse(msg('OK'), 'text/json')

    elif request.method == 'POST':
        if 'name' in request.POST:
            group.name = request.POST['name']

        group.put()
        return HttpResponse(msg('OK'), 'text/json')

    elif request.method == 'DELETE':
        group.delete()
        return HttpResponse(msg('OK'), 'text/json')

