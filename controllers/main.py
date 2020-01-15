import logging

from odoo import  http
from odoo.http import request

logger = logging.getLogger(__name__)

class BaseWebsite(http.Controller):

    @http.route('/myweb/index', type='http', auth="public", website=True)
    def index(self, **kw):
        values = {
            'content' : 'content',
        }
        return request.render('module.template', values)
