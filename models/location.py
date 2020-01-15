from odoo import api, fields, models, _
import time
from odoo.exceptions import UserError
import logging
_logger = logging.getLogger(__name__)

class location(models.Model):
    _name = 'vit.location'
    _inherit = ['portal.mixin', 'mail.thread', 'mail.activity.mixin']

    name = fields.Char("Name", required=True, track_visibility='onchange')
    location_id = fields.Many2one(comodel_name="vit.location", string="Parent Location", required=False, track_visibility='onchange')
    company_id = fields.Many2one('res.company', 'Company', required=True, default=lambda self: self.env['res.company']._company_default_get(), track_visibility='onchange')
