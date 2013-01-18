#!/usr/bin/env python3
# -*- encoding: utf-8 -*-

from models import Quote
from django import forms
from django.shortcuts import render
from django.db.models import Q
from django.http import Http404, HttpResponseRedirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.sites.models import RequestSite, Site
from registration.backends import default
from registration import signals
from registration.models import RegistrationProfile
from voting.models import Vote
import re
import itertools

NUMBER_PER_PAGE = 30


class SearchForm(forms.Form):
    q = forms.CharField()

    def clean_q(self):
        q = self.cleaned_data['q']
        if len(q.split()) > 30:
            raise forms.ValidationError("Trop de mots.")
        if len(q) > 300:
            raise forms.ValidationError("Trop de lettres.")
        return q


class AddQuoteForm(forms.Form):
    author = forms.CharField(label="Auteur")
    context = forms.CharField(label="Contexte", required=False)
    content = forms.CharField(widget=forms.Textarea(attrs={
      'style': 'width: 500px; heigth: 200px;'}), label="")


class UserRegistrationForm(forms.Form):
    username = forms.CharField(max_length=8, label='Login EPITA')
    password1 = forms.CharField(widget=forms.PasswordInput(),
            label="Mot de passe")
    password2 = forms.CharField(widget=forms.PasswordInput(),
            label="Vérification du mot de passe")

    def clean_password2(self):
        if self.data['password1'] != self.data['password2']:
            raise forms.ValidationError(
                    'Les mots de passe ne correspondent pas.')
        return self.data['password1']

    def clean_username(self):
        if not re.match('^[a-zA-Z0-9_]{0,8}$', self.data['username']):
            raise forms.ValidationError("Ce login n'est pas valide.")
        if User.objects.filter(username=self.data['username']).exists():
            raise forms.ValidationError('Ce login est déjà enregistré.')
        return self.data['username']


class Backend(default.DefaultBackend):
    def register(self, request, **kwargs):
        username, password = kwargs['username'], kwargs['password1']
        email = username + '@epita.fr'
        if Site._meta.installed:
            site = Site.objects.get_current()
        else:
            site = RequestSite(request)
        new_user = RegistrationProfile.objects.create_inactive_user(username,
                email, password, site)
        signals.user_registered.send(sender=self.__class__,
                                     user=new_user,
                                     request=request)
        return new_user


def template_processor(request):
    return {
        'quotes_search_form': SearchForm(),
    }


def get_quotes(only_visible=True, order='-date'):
    quotes = Quote.objects.order_by(order).filter(accepted=True)
    if only_visible:
        quotes = quotes.filter(visible=True)
    return quotes


def split_quotes(quotes, page=0, number=NUMBER_PER_PAGE):
    return quotes[page * number: (page + 1) * number]


def pagination_infos(quotes, page):
    r = {}
    r['max_page'] = len(quotes) / NUMBER_PER_PAGE
    if page < 0 or page > r['max_page']:
        raise Http404()
    r['next_page'] = None if page >= r['max_page'] else page + 1
    r['prev_page'] = None if page <= 0 else page - 1
    print r
    return r


def last_quotes(request, page=0):
    if 'p' in request.GET:
        return HttpResponseRedirect('/last/{0}'.format(request.GET['p']))
    page = int(page)
    all_quotes = get_quotes()
    r = pagination_infos(all_quotes, page)
    quotes = split_quotes(all_quotes, page=page)
    print r.update({'quotes': quotes, 'page': page})
    return render(request, 'last.html', dict(
        {'name_page': 'Dernières citations', 'quotes': quotes, 'page': page},
        **r))


def top_quotes(request):
    quotes = [x for x, y in Vote.objects.get_top(Quote, limit=50)]
    return render(request, 'simple.html', dict(
        {'name_page': 'Meilleures citations', 'quotes': quotes}))


def flop_quotes(request):
    q = Vote.objects.get_top(Quote, limit=50, reversed=True)
    quotes = [x for x, y in q]
    return render(request, 'simple.html', dict(
        {'name_page': 'Pires citations', 'quotes': quotes}))


def random_quotes(request):
    quotes = split_quotes(get_quotes(order='?'))
    return render(request, 'simple.html', {'name_page':
        'Citations aléatoires', 'quotes': quotes})


def search_quotes(request):
    def quotes_split(s):
        l = map((lambda x: x.strip()), s.split('"'))
        l = [[e] if i % 2 else e.split() for i, e in enumerate(l)]
        return filter(bool, itertools.chain(*l))

    f = SearchForm(request.GET)
    if not f.is_valid():
        raise Http404()
    q = f.cleaned_data['q']
    terms = map(lambda s: r'(^|[^\w]){0}([^\w]|$)'.format(s), quotes_split(q))
    if not terms:
        raise Http404()
    f = Q()
    for w in terms:
        f |= (Q(content__iregex=w)
                | Q(context__iregex=w)
                | Q(author__iregex=w))
    quotes = get_quotes()
    quotes = quotes.filter(f)
    if not quotes:
        raise Http404()
    return render(request, 'simple.html', {'name_page':
        u'Recherche : {0}'.format(request.GET['q']), 'quotes': quotes})


@login_required
def add_quote(request):
    print type(request.user)
    if request.method == 'POST':
        form = AddQuoteForm(request.POST)
        if form.is_valid():
            cd = form.cleaned_data
            quote = Quote(author=cd['author'], context=cd['context'],
                    content=cd['content'], user=request.user)
            quote.save()
            return HttpResponseRedirect('/add_confirm')
    else:
        form = AddQuoteForm()
    return render(request, 'add.html', {'name_page':
        u'Ajouter une citation', 'add_form': form})


@login_required
def add_confirm(request):
    return render(request, 'add_confirm.html', {'name_page':
            'Ajouter une citation'})
