try:
    from trytond.modules.account_invoice_ar.tests.test_account_invoice_ar import suite
except ImportError:
    from .test_account_invoice_ar import suite

__all__ = ['suite']
