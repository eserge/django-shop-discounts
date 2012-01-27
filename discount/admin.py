# -*- coding: utf-8 -*-
from django.contrib import admin

from discount.models import PercentDiscount, AbsoluteDiscount, \
        CartItemPercentDiscount, CartItemAbsoluteDiscount, \
        CartDiscountCode, UniqueDiscountCode
from django.conf.urls.defaults import patterns, include, url
from django.utils.functional import update_wrapper
from django.http import Http404, HttpResponse, HttpResponseRedirect
from django.views.generic.simple import direct_to_template
from django.shortcuts import render_to_response
from django.shortcuts import redirect
from django.forms import ModelForm
from django import forms
import random, string
from forms import GenerateCodeForm


class DiscountForm(ModelForm):
    number_of_codes = forms.IntegerField(required=False)
    
    def __init__(self,  *args, **kwargs):
        super(DiscountForm, self).__init__(*args, **kwargs)
        self.fields['number_of_codes'].widget.attrs = {'readonly':'readonly', 'disabled':'disabled'}
        if kwargs.has_key('instance'):
            instance = kwargs['instance']
            if instance.has_unique_code():
                self.initial['number_of_codes'] = instance.unique_codes_count()


class PercentDiscountForm(DiscountForm):
    class Meta:
        model = PercentDiscount


class AbsoluteDiscountForm(DiscountForm):
    class Meta:
        model = AbsoluteDiscount
    

class DiscountAdmin(admin.ModelAdmin):
    def __init__(self, *args, **kwargs):
        return super(DiscountAdmin, self).__init__(*args, **kwargs)

    def generate_view(self, request, object_id, extra_context=None):
        def generate_codestrings(number_of_codes):
            vowels = "aeiouy"
            consonants = "".join([a for a in string.ascii_lowercase if a not in vowels])
            schemes = ["vcvcdd", "cvcvdd", "vcddvc", "ddvcdd"]
            words = []
            for i in range(number_of_codes):
                scheme = schemes[random.randint(0,len(schemes)-1)]
                repeat = True
                while repeat:
                    word = ""
                    for letter in scheme:
                        if letter == "v":
                            word = word + vowels[random.randint(0,len(vowels)-1)]
                        elif letter == "c":
                            word = word + consonants[random.randint(0,len(consonants)-1)]
                        elif letter == "d":
                            word = word + string.digits[random.randint(0,len(string.digits)-1)]
                    repeat = word in words
                words.append(word)
            return words
        if request.method == "POST":
            form = GenerateCodeForm(request.POST, request.FILES)
            if form.is_valid():
                number_of_codes = form.cleaned_data['number_of_codes']
                object = self.model.objects.get(pk=object_id)
                codes = []
                for code_string in generate_codestrings(number_of_codes):
                    code = UniqueDiscountCode(code=code_string, discount=object)
                    code.save()
                    codes.append(code)
                return redirect('../view_codes/')
#                return direct_to_template(request, template="discount/admin_generate_codes.html", 
#                                        extra_context={"codes":codes, "discount":object})
        else:
            form = GenerateCodeForm()
        return render_to_response(request, template="discount/admin_generate_codes_form.html", 
                                extra_context={"form":form})
    
    def view_codes(self, request, object_id, extra_context=None):
        object = self.model.objects.get(pk=object_id)
        codes = object.uniquediscountcode_set.all()
        return direct_to_template(request, template="discount/view_codes.html", 
                                extra_context={"codes":codes, "discount":object})
    
    def get_urls(self):
        urlpatterns = super(DiscountAdmin, self).get_urls()
        urlpatterns = patterns('',
            url(r'^(.+)/generate_codes/$',
                self.admin_site.admin_view(self.generate_view),
                name='discount_percentdiscount_generate_codes'),
            url(r'^(.+)/view_codes/$',
                self.admin_site.admin_view(self.view_codes),
                name='discount_percentdiscount_view_codes'),
        ) + urlpatterns
        return urlpatterns

    def save_model(self, request, obj, form, change):
        if obj.has_unique_code():
            obj.code = ''
        else:
            discount_codes = obj.uniquediscountcode_set.all()
            if len(discount_codes):
                discount_codes.delete()
        super(DiscountAdmin, self).save_model(request, obj, form, change)


class PercentDiscountAdmin(DiscountAdmin):
    form = PercentDiscountForm


class AbsoluteDiscountAdmin(DiscountAdmin):
    form = AbsoluteDiscountForm


class CartItemPercentDiscountAdmin(admin.ModelAdmin):
    pass


class CartItemAbsoluteDiscountAdmin(admin.ModelAdmin):
    pass


class UniqueDiscountCodeAdmin(admin.ModelAdmin):
    list_display =('code', 'discount')
    list_filter = ['discount']

admin.site.register(PercentDiscount, PercentDiscountAdmin)
admin.site.register(AbsoluteDiscount, AbsoluteDiscountAdmin)
admin.site.register(CartItemAbsoluteDiscount, CartItemAbsoluteDiscountAdmin)
admin.site.register(UniqueDiscountCode, UniqueDiscountCodeAdmin)
