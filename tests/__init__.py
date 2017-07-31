try:
    from trytond.modules.account_invoice_ar.tests.tests import suite
except ImportError:
    from .tests import suite

__all__ = ['suite']
