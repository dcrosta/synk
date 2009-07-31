import sha
from datetime import datetime

from django.http import HttpResponse
from django.http import HttpResponseForbidden
from django.http import HttpResponseRedirect
from django.core.urlresolvers import reverse

from google.appengine.ext.webapp import template

from synk.models import *
from synk.forms import UserForm

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

def group_index(request):
    try:
        user = get_user(request)
    except UnauthorizedError:
        return HttpResponseForbidden()

    groups = [x for x in Group.for_user(user)]

    return HttpResponse(repr(groups))

def render(request, template_filename, **kwargs):
    template_filename = 'synk/templates/' + template_filename
    return HttpResponse(template.render(template_filename, kwargs))

class UnauthorizedError(Exception):
    """User did not supply valid credentials."""
    pass

def get_user(request):
    try:
        username = request.REQUEST['username']
        nonce = request.REQUEST['nonce']
        nonced_password_hash = request.REQUEST['nonced_password_hash']
    except KeyError:
        raise UnauthorizedError('Wrong username or password')

    user = User.by_username(username)
    if user is None:
        raise UnauthorizedError('Wrong username or password')

    saved_nonced_hash = sha.new(nonce+user.password_hash).hexdigest()

    if saved_nonced_hash != nonced_password_hash:
        raise UnauthorizedError('Wrong username or password')

    return user
