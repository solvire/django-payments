from __future__ import unicode_literals
from decimal import Decimal

import stripe

from .forms import ModalPaymentForm, PaymentForm
from .. import RedirectNeeded, PaymentError
from ..core import BasicProvider


class StripeProvider(BasicProvider):

    form_class = ModalPaymentForm

    def __init__(self, public_key, secret_key, image='', name='', **kwargs):
        stripe.api_key = secret_key
        self.secret_key = secret_key
        self.public_key = public_key
        self.image = image
        self.name = name
        super(StripeProvider, self).__init__(**kwargs)

    def get_form(self, payment, data=None):
        if payment.status == 'waiting':
            payment.change_status('input')
        form = self.form_class(
            data=data, payment=payment, provider=self)

        if form.is_valid():
            form.save()
            raise RedirectNeeded(payment.get_success_url())
        return form

    def capture(self, payment, amount=None):
        amount = int((amount or payment.total) * 100)
        charge = stripe.Charge.retrieve(payment.transaction_id)
        try:
            charge.capture(amount=amount)
        except stripe.InvalidRequestError as e:
            payment.change_status('refunded')
            raise PaymentError('Payment already refunded')
        payment.attrs.capture = stripe.util.json.dumps(charge)
        return Decimal(amount) / 100

    def release(self, payment):
        charge = stripe.Charge.retrieve(payment.transaction_id)
        charge.refund()
        payment.attrs.release = stripe.util.json.dumps(charge)

    def refund(self, payment, amount=None):
        amount = int((amount or payment.total) * 100)
        charge = stripe.Charge.retrieve(payment.transaction_id)
        charge.refund(amount=amount)
        payment.attrs.refund = stripe.util.json.dumps(charge)
        return Decimal(amount) / 100


class StripeCheckoutProvider(BasicProvider):
    """
    A provider based on Stripe Checkout flow.
    @see https://stripe.com/docs/checkout

    This is a charge only utility.
    Data is collected on checkout and captured later.
    @see https://stripe.com/docs/charges
    """

    def __init__(self, secret_key, **kwargs):
        stripe.api_key = secret_key
        self.secret_key = secret_key
        super(StripeCheckoutProvider, self).__init__(**kwargs)

    def capture(self, payment, amount=None):
        amount = int((amount or payment.total) * 100)
        token = payment.remote_token
        try:
            charge = stripe.Charge.create(
                amount=amount,
                currency=payment.currency,
                description=payment.description,
                source=token,)
        except stripe.InvalidRequestError as err:
            raise PaymentError('Payment capture failed ' + str(err.message))
        payment.attrs.capture = stripe.util.json.dumps(charge)
        return Decimal(amount) / 100

    def release(self, payment):
        raise PaymentError('Stripe Checkout does not need to release.')

    def refund(self, payment, amount=None):
        raise PaymentError('Stripe Checkout does not allow refunds.')

class StripeCardProvider(StripeProvider):

    form_class = PaymentForm
