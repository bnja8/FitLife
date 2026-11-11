from django.conf import settings
from transbank.common.integration_api_keys import IntegrationApiKeys
from transbank.common.integration_commerce_codes import IntegrationCommerceCodes
from transbank.webpay.webpay_plus.transaction import Transaction


def webpay_transaction():
    if settings.WEBPAY_ENVIRONMENT == 'test':
        transaction = Transaction.build_for_integration(
            IntegrationCommerceCodes.WEBPAY_PLUS,
            IntegrationApiKeys.WEBPAY,
        )
    elif settings.WEBPAY_ENVIRONMENT == 'production':
        if not settings.WEBPAY_COMMERCE_CODE or not settings.WEBPAY_API_KEY:
            raise RuntimeError('Faltan las credenciales de producción de Webpay.')
        transaction = Transaction.build_for_production(
            settings.WEBPAY_COMMERCE_CODE,
            settings.WEBPAY_API_KEY,
        )
    else:
        raise RuntimeError('WEBPAY_ENVIRONMENT debe ser test o production.')
    transaction.options.timeout = 15
    return transaction
