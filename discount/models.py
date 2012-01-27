# -*- coding: utf-8 -*-
from datetime import datetime

from django.db import models
from django.db.models import Q, F
from django.utils.translation import ugettext_lazy as _

from polymorphic.manager import PolymorphicManager
from polymorphic.polymorphic_model import PolymorphicModel

from shop.models.cartmodel import Cart
from shop.models.productmodel import Product
from shop.cart.cart_modifiers_base import BaseCartModifier

from shop.order_signals import completed as completed_signal
from django.db.models.signals import post_save as signals_postsave
from shop.util.cart import get_or_create_cart


def on_order_completed(sender, **kwargs):
    #if we have no-code discount, just increment its counter
    #for nonunique code discount, also do increment
    #and if there was unique code discount involved, increment it's counter and remove the code was used
    cart = get_or_create_cart(sender.request)
    try:
        discount_code = cart.cartdiscountcode_set.all()
        discount_str = discount_code[0].code
    except IndexError:
        pass
    else:
        try:
            unique_discount_code = UniqueDiscountCode.objects.get(code=discount_str)
        except:
            discount = DiscountBase.objects.get(code=discount_str)
        else:
            discount = unique_discount_code.discount
            unique_discount_code.delete()
        discount.num_uses += 1
        discount.save()
    DiscountBase.objects.active().filter(code='', 
                                                is_unique_code_discount=False)\
                        .update(num_uses=F('num_uses')+1)
completed_signal.connect(on_order_completed)


class DiscountBaseManager(PolymorphicManager):

    def active(self, at_datetime=None, code=''):
        if not at_datetime:
            at_datetime = datetime.now
        qs = self.filter(Q(is_active=True) & 
                Q(valid_from__lte=at_datetime) & 
                (Q(valid_until__isnull=True) | Q(valid_until__gt=at_datetime)))
        if code == '':
            qs = qs.filter(Q(code='') & Q(is_unique_code_discount=False))
        else:
            qs = qs.filter(Q(code='') | Q(code=code))
            to_exclude = [discount.id for discount in qs.filter(code='') if discount.has_unique_code() and not discount.test_unique_code(code)]
            qs = qs.exclude(id__in=to_exclude)
        return qs
        # discountbase should have a method to test itself against unique code
        # and then the algorythm is as follows:
        # fetch all discounts as above (they will be active by date and have or
        # doesn't have given code as nonunique code). these which have 
        # no nonunique code may have our given code as unique. we now should check it.
        # to do that take all discounts with no nonunique code and test them with their method
        #
        # our task here is not to include some instances, but to exclude some of them.
        # particulary we need to exclde instances which were declared as unique code instances
        # but their code doesn't mach our given code


class DiscountBase(PolymorphicModel, BaseCartModifier):
    """
    """
#    name = models.CharField(_('Name'), max_length=100)
    title = models.CharField(_('Title'), max_length=100)
    code = models.CharField(_('Code'), max_length=30,
            blank=True, null=False, 
            help_text=_('Is discount valid only with included code'))
    is_unique_code_discount = models.BooleanField(_('Use unique codes'),
            default=False,
            help_text=_('Unique codes can be used only once and their number is limited'))

    valid_from = models.DateTimeField(_('Valid from'), default=datetime.now)
    valid_until = models.DateTimeField(_('Valid until'), blank=True, null=True)
    is_active = models.BooleanField(_('Is active'), default=True)

    num_uses = models.IntegerField(_('Number of times already used'),
            default=0)

    objects = DiscountBaseManager()
    product_filters = []

    def __init__(self, *args, **kwargs):
        self._eligible_products_cache = {}
        return super(DiscountBase, self).__init__(*args, **kwargs)

    class Meta:
        verbose_name = _('Discount')
        verbose_name_plural = _('Discounts')
        ordering = []

    def __unicode__(self):
        return u'%s' % self.get_title()

    def get_title(self):
        return self.title
    
    def has_unique_code(self):
        return self.is_unique_code_discount
    
    def test_unique_code(self, code):
        try:
            uniquecodes = self.uniquediscountcode_set.all()
            uniquecode = uniquecodes[0]
        except IndexError:
            return False
        else:
            if uniquecode.code == code:
                return True
            else:
                return False

    def unique_codes_count(self):
        if self.has_unique_code():
            return len(self.uniquediscountcode_set.all())

    @classmethod
    def register_product_filter(cls, filt):
        """
        Register filters that affects which products this discount class
        may apply to.
        """
        cls.product_filters.append(filt)

    def eligible_products(self, in_products=None):
        """
        Returns queryset of products this discounts may apply to.
        """
        cache_key = tuple(in_products) if in_products else None
        try:
            qs = self._eligible_products_cache[cache_key]
        except KeyError:
            qs = Product.objects.all()
            for filt in self.__class__.product_filters:
                if callable(filt):
                    qs = filt(self, qs)
                elif type(filt) is dict:
                    qs = qs.filter(**filt)
                else:
                    qs = qs.filter(filt)
            if in_products:
                qs = qs.filter(id__in=[p.id for p in in_products])
            self._eligible_products_cache[cache_key] = qs
        return qs

    def is_eligible_product(self, product, cart):
        """
        Returns if given product in cart should be discounted.
        """
        products = set([cart_item.product for cart_item in cart.items.all()])
        eligible_products_in_cart = self.eligible_products(products)
        return product in eligible_products_in_cart


def on_post_save(sender, instance, **kwargs):
    if isinstance(instance, DiscountBase):
        if instance.has_unique_code():
            instance.code = ''
            instance.save()
        else:
            discount_codes = instance.uniquediscountcode_set.all()
            discount_codes.delete()
#signals_postsave.connect(on_post_save)


class CartDiscountCode(models.Model):
    cart = models.ForeignKey(Cart, editable=False)
    code = models.CharField(_('Discount code'), max_length=30)

    class Meta:
        verbose_name = _('Cart discount code')
        verbose_name_plural = _('Cart discount codes')


class PercentDiscount(DiscountBase):
    """
    Apply ``amount`` percent discount to whole cart.
    """
    amount = models.DecimalField(_('Amount'), max_digits=5, decimal_places=2)

    def get_extra_cart_price_field(self, cart):
        amount = (self.amount/100) * cart.subtotal_price
        return (self.get_title(), amount,)

    class Meta:
        verbose_name = _('Cart percent discount')
        verbose_name_plural = _('Cart percent discounts')

class AbsoluteDiscount(DiscountBase):
    """
    Apply value of ``amount`` to whole cart.
    """
    amount = models.DecimalField(_('Amount'), max_digits=5, decimal_places=2)

    def get_extra_cart_price_field(self, cart):
        return (self.get_title(), self.amount,)

    class Meta:
        verbose_name = _('Cart absolute discount')
        verbose_name_plural = _('Cart absolute discounts')


class UniqueDiscountCode(models.Model):
    cart = models.ForeignKey(Cart, null=True, blank=True)
    discount = models.ForeignKey(DiscountBase)
    code = models.CharField(_('Discount code'), max_length=255)

    def get_code(self):
        return self.code

    def __unicode__(self):
        return self.get_code()

    class Meta:
        verbose_name = _('Unique discount code')
        verbose_name_plural = _('Unique discount codes')


class CartItemPercentDiscount(DiscountBase):
    """
    Apply ``amount`` percent discount to eligible_products in Cart.
    """
    amount = models.DecimalField(_('Amount'), max_digits=5, decimal_places=2)

    def get_extra_cart_item_price_field(self, cart_item):
        if self.is_eligible_product(cart_item.product, cart_item.cart):
            return (self.get_title(),
                    self.calculate_discount(cart_item.line_subtotal))

    def calculate_discount(self, price):
        return (self.amount/100) * price
    class Meta:
        verbose_name = _('Cart item percent discount')
        verbose_name_plural = _('Cart item percent discounts')


class CartItemAbsoluteDiscount(DiscountBase):
    """
    Apply ``amount`` discount to eligible_products in Cart.
    """
    amount = models.DecimalField(_('Amount'), max_digits=5, decimal_places=2)

    def get_extra_cart_item_price_field(self, cart_item):
        if self.is_eligible_product(cart_item.product, cart_item.cart):
            return (self.get_title(),
                    self.calculate_discount(cart_item.line_subtotal))

    def calculate_discount(self, price):
        return self.amount

    class Meta:
        verbose_name = _('Cart item absolute discount')
        verbose_name_plural = _('Cart item absolute discounts')


class BulkDiscount(DiscountBase):
    """
    Apply ``amount`` % of discount if there are at least ``num_items`` of
    product in cart.
    """
    amount = models.DecimalField(_('Amount'), max_digits=5, decimal_places=2)
    num_items = models.IntegerField(_('Minimum number of items'))

    def process_cart_item(self, cart_item):
        if (cart_item.quantity >= self.num_items and
            self.is_eligible_product(cart_item.product, cart_item.cart)):
            amount = (self.amount/100) * cart_item.line_subtotal
            to_append = (self.get_title(), amount)
            cart_item.extra_price_fields.append(to_append)

    class Meta:
        verbose_name = _('Bulk discount')
        verbose_name_plural = _('Bulk discounts')
