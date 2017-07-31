import unittest
import trytond.tests.test_tryton
from trytond.tests.test_tryton import ModuleTestCase


class TestCase(ModuleTestCase):
    'Test module'
    module = 'account_invoice_ar'


def suite():
    suite = trytond.tests.test_tryton.suite()
    suite.addTests(unittest.TestLoader().loadTestsFromTestCase(
            TestCase))
    return suite
