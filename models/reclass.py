from odoo import api, fields, models, _
import time
from odoo.exceptions import UserError, Warning
import logging
_logger = logging.getLogger(__name__)
STATES = [('draft', 'Draft'), ('open', 'Open'), ('done','Done')]
import datetime

class VitReclass(models.Model):
    _name = 'vit.reclass'
    _description = 'Reclassification'
    _inherit = ['portal.mixin', 'mail.thread', 'mail.activity.mixin']

    @api.multi
    @api.depends('user_id')
    def _get_department(self):
        for me_id in self :
            employee_id = self.env['hr.employee'].search([
                ('user_id','!=',False),
                ('user_id','=',me_id.user_id.id)
            ], limit=1)
            me_id.department_id = employee_id and employee_id.department_id.id or False

    name = fields.Char("Name", readonly=True)
    date            = fields.Date(string="Date",
                                  default=str(datetime.datetime.now()),
                                  readonly=True, states={'draft': [('readonly', False)]},
                                  required=True, )

    notes           = fields.Text(string="Notes", required=True,
                                  readonly=True, states={'draft': [('readonly', False)]},)

    category_id         = fields.Many2one(comodel_name="account.asset.category",
                                          string="Category", required=True,
                                          readonly=True, states={'draft': [('readonly', False)]},)
    new_category_id = fields.Many2one(comodel_name="account.asset.category",
                                       string="New Category", required=True,
                                       readonly=True, states={'draft': [('readonly', False)]},
                                       track_visibility='onchange')

    asset_ids           = fields.Many2many(comodel_name="account.asset.asset",
                                           string="Assets", required=False,
                                           readonly=True, states={'draft': [('readonly', False)]},
                                           )

    state = fields.Selection(string="State", selection=STATES, required=True, readonly=True,
                             default=STATES[0][0],
                             track_visibility='onchange')
    user_id = fields.Many2one(comodel_name="res.users", string="Responsible", required=True, readonly=True, states={'draft': [('readonly', False)]}, default=lambda self: self.env.user.id)
    department_id = fields.Many2one('hr.department', compute='_get_department')


    @api.model
    def create(self, vals):
        vals['name']    = self.env['ir.sequence'].next_by_code('vit.reclass')
        return super(VitReclass, self).create(vals)

    @api.multi
    def action_open(self):
        self.state = STATES[1][0]

    @api.multi
    def action_approve(self):
      if not self.asset_ids :
        raise Warning("Silahkan input Asset.")
      for ass in self.asset_ids:
        categ = self.new_category_id
        ass.write({
          'category_id': categ.id,
          'method': categ.method,
          'method_progress_factor': categ.method_progress_factor,
          'prorata': categ.prorata,
          'method_number': categ.method_number,
          'method_period': categ.method_period,
          'method_time': categ.method_time,
          'method_end': categ.method_end,
        })
        modify_id = self.env['asset.modify'].create({
          'name': ass.name,
          'method_period': categ.method_period,
          'method_end': categ.method_end,
          'method_number': categ.method_number,
        })
        self = self.with_context(active_id=ass.id)
        modify_id.new_modify(ass)
      self.state = STATES[2][0]

    @api.multi
    def action_cancel(self):
        self.state = STATES[0][0]

    @api.multi
    def unlink(self):
        for me_id in self :
            if me_id.state != 'draft' :
                raise Warning('Tidak bisa menghapus data yang bukan draft !')
        return super(VitReclass, self).unlink()

class AssetModify(models.TransientModel):
    _inherit = 'asset.modify'

    @api.multi
    def new_modify(self, asset):
        old_values = {
            'method_number': asset.method_number,
            'method_period': asset.method_period,
            'method_end': asset.method_end,
        }
        asset_vals = {
            'method_number': self.method_number,
            'method_period': self.method_period,
            'method_end': self.method_end,
        }
        asset.write(asset_vals)
        asset.compute_depreciation_board()
        tracked_fields = self.env['account.asset.asset'].fields_get(['method_number', 'method_period', 'method_end'])
        changes, tracking_value_ids = asset._message_track(tracked_fields, old_values)
        if changes:
            asset.message_post(subject=_('Depreciation board modified'), body=self.name, tracking_value_ids=tracking_value_ids)
        return {'type': 'ir.actions.act_window_close'}
