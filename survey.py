#!/usr/bin/env python
# This file is part of the survey_mail module for Tryton.
# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond import backend
from trytond.model import ModelSQL, fields
from trytond.pool import Pool, PoolMeta
from trytond.tools.multivalue import migrate_property
from trytond.modules.company.model import (
    CompanyMultiValueMixin, CompanyValueMixin)
from trytond.pyson import Eval, Not, Bool
from trytond.sendmail import SMTPDataManager, sendmail_transactional
from email import Utils
from email.header import Header
from email.mime.text import MIMEText
import logging

__all__ = ['Configuration', 'Survey', 'ConfigurationSmtp']

logger = logging.getLogger(__name__)

smtp = fields.Many2One('smtp.server', 'SMTP', required=True)

class Configuration(CompanyMultiValueMixin):
    __metaclass__ = PoolMeta
    __name__ = 'survey.configuration'
    smtp = fields.MultiValue(smtp)


class ConfigurationSmtp(ModelSQL, CompanyValueMixin):
    "Survey Configuration SMTP"
    __name__ = 'survey.configuration.smtp'
    smtp = smtp

    @classmethod
    def __register__(cls, module_name):
        TableHandler = backend.get('TableHandler')
        exist = TableHandler.table_exist(cls._table)

        super(ConfigurationSmtp, cls).__register__(module_name)

        if not exist:
            cls._migrate_property([], [], [])

    @classmethod
    def _migrate_property(cls, field_names, value_names, fields):
        field_names.extend(['smtp'])
        value_names.extend(['smtp'])
        fields.append('company')
        migrate_property('survey.configuration', field_names, cls, value_names,
            fields=fields)


class Survey:
    __metaclass__ = PoolMeta
    __name__ = 'survey.survey'
    send_email = fields.Boolean('Send Email',
        help="Survey data will be send by email")
    email_cc = fields.Char('Email CC',
        states={
            'invisible': ~Bool(Eval('send_email')),
        }, depends=['send_email'],
        help="Emails separated by comma")

    @classmethod
    def __setup__(cls):
        super(Survey, cls).__setup__()
        cls._error_messages.update({
            'not_smtp_server': 'Configure a SMTP server in Survey ' \
                'Configuration',
            'not_recipients': 'Configure a recipient in survey or ' \
                'SMTP server',
            'email_title': ("Survey \"%s\""),
            'email_body': ("Data from survey \"%s\"\n\n%s\n\n"
                "Do not reply this mail.")
            })

    @classmethod
    def view_attributes(cls):
        return super(Survey, cls).view_attributes() + [
            ('//page[@id="mail"]', 'states', {
                    'invisible': Not(Bool(Eval('send_email'))),
                    })]

    @classmethod
    def save_data(cls, survey, data):
        '''Get values from a survey
        :param survey: obj
        :param data: dict
        '''
        Config = Pool().get('survey.configuration')

        super(Survey, cls).save_data(survey, data)

        if survey.send_email:
            config = Config(1)
            server = config.smtp
            if not server:
                cls.raise_user_error('not_smtp_server')

            # change name to label field
            fields = {}
            for field in survey.fields_:
                fields[field.name] = field.string
            d = []
            for k, v in data.iteritems():
                d.append('%s: %s' % (fields[k], v))

            title = cls.raise_user_error('email_title',
                (survey.name), raise_exception=False)
            body = cls.raise_user_error('email_body',
                (survey.name, "\n".join(d)),
                raise_exception=False)

            from_ = server.smtp_email
            recipients = []
            if survey.email_cc:
                recipients.append(survey.email_cc)
            if server.smtp_email and not server.smtp_email in recipients:
                recipients.append(server.smtp_email)
            if not recipients:
                cls.raise_user_error('not_recipients')

            msg = MIMEText(body, _charset='utf-8')
            msg['Subject'] = Header(title, 'utf-8')
            msg['From'] = from_
            msg['To'] = ', '.join(recipients)
            msg['Reply-to'] = server.smtp_email
            # msg['Date']     = Utils.formatdate(localtime = 1)
            msg['Message-ID'] = Utils.make_msgid()

            datamanager = SMTPDataManager()
            datamanager._server = server.get_smtp_server()
            sendmail_transactional(from_, recipients, msg, datamanager=datamanager)

        return True
