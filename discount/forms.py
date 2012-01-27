# -*- coding: utf-8 -*-
from django import forms 
from django.utils.translation import ugettext_lazy as _


class GenerateCodeForm(forms.Form):
	number_of_codes = forms.IntegerField(label=_(u"Количество кодов"), min_value=2, initial=20)
