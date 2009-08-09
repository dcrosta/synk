from google.appengine.ext import db

from django import newforms as forms

__all__ = ['UserForm']

letters = set([l for l in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz01234567890_.'])


class UserForm(forms.Form):
    username = forms.CharField(min_length=3, max_length=255)
    password = forms.CharField(min_length=6, widget=forms.PasswordInput)

    def clean_username(self):
        username = self.clean_data['username']
        for letter in username:
            if letter not in letters:
                raise forms.ValidationError('Your username may only contain letters, numbers, underscore (_) and dot (.) characters')

        # make sure the username is not already
        # taken
        existing_users = db.GqlQuery('select __key__ from User where username = :1 limit 1', username)
        if existing_users.count() != 0:
            raise forms.ValidationError('That username is already in use')

        return username

class LoginForm(forms.Form):
    username = forms.CharField(min_length=3, max_length=255)
    password = forms.CharField(min_length=6, max_length=255, widget=forms.PasswordInput)

    def clean_password(self):
        username = self.clean_data['username']
        password = self.clean_data['password']

        # make sure the username is not already
        # taken
        user_rows = db.GqlQuery('select __key__ from User where username = :1 limit 1', username)
        if existing_users.count() != 0:
            raise forms.ValidationError('Invalid username or password')

        user = user_rows.get()
        if not user.authenticate(password):
            raise forms.ValidationError('Invalid username or password')

        return password

