from synk.models import User
from synk.forms import UserForm

from django.http import HttpResponse
from django.http import HttpResponseRedirect
from django.core.urlresolvers import reverse

from google.appengine.ext.webapp import template

# utilities
def render(request, template_filename, **kwargs):
    template_filename = 'synk/templates/' + template_filename
    return HttpResponse(template.render(template_filename, kwargs))


# view methods
def index(request):
    return render(request, 'index.html')

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
            form_action=reverse('synk.web.register'),
            submit_button='Register',
            )

def dev(request):
    return render(request, 'dev.html')

