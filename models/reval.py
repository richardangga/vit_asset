from odoo import api, fields, models, _
import time
from odoo.exceptions import UserError, Warning
import openerp.addons.decimal_precision as dp
import logging
_logger = logging.getLogger(__name__)
STATES = [('draft', 'Draft'), ('open', 'Open'), ('done','Done')]
import datetime
class VitReval(models.Model):
    _name = 'vit.reval'
    _description = 'Revaluation'
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

    name = fields.Char("Name", copy=False)
    date            = fields.Date(string="Date",
                                  default=str(datetime.datetime.now()),
                                  readonly=True, states={'draft': [('readonly', False)]},
                                  required=True, )

    notes           = fields.Text(string="Notes", required=True,
                                  readonly=True, states={'draft': [('readonly', False)]},)

    book_value         = fields.Float(string="Book Value", required=True,
                                digits=dp.get_precision('Unit Price'),
                                readonly=True, states={'draft': [('readonly', False)]},)
    new_book_value         = fields.Float(string="New Book Value", required=True,
                                digits=dp.get_precision('Unit Price'),
                                readonly=True, states={'draft': [('readonly', False)]},
                                track_visibility='onchange')
    asset_id           = fields.Many2one(comodel_name="account.asset.asset",
                                           string="Assets", required=True,
                                           readonly=True, states={'draft': [('readonly', False)]},
                                           )
    company_id = fields.Many2one('res.company', string='Company', related='asset_id.company_id', store=True, readonly=True)
    account_id = fields.Many2one('account.account', string='Revaluation Account', required=True, readonly=True, states={'draft': [('readonly', False)]})
    journal_id = fields.Many2one('account.journal', string='Journal', required=True, readonly=True, states={'draft': [('readonly', False)]})
    state = fields.Selection(string="State", selection=STATES, required=True, readonly=True,
                             default=STATES[0][0])
    user_id = fields.Many2one(comodel_name="res.users", string="Responsible", required=True, readonly=True, states={'draft': [('readonly', False)]}, default=lambda self: self.env.user.id)
    department_id = fields.Many2one('hr.department', compute='_get_department')
    move_id = fields.Many2one('account.move', string='Move Entries', copy=False, readonly=True)

    @api.multi
    def unlink(self):
        for me_id in self :
            if me_id.state != 'draft' :
                raise Warning('Tidak bisa menghapus data yang bukan draft !')
        return super(VitReval, self).unlink()

    @api.model
    def create(self, vals):
        vals['name']    = self.env['ir.sequence'].next_by_code('vit.reval')
        return super(VitReval, self).create(vals)

    @api.multi
    def validity_check(self):
        for me_id in self :
            if me_id.asset_id.value_residual == self.new_book_value :
                raise Warning("New book value sama dengan nilai residual.")
            if not me_id.asset_id.category_id.account_asset_id :
                raise Warning("Asset account category %s belum diisi."%me_id.asset_id.category_id.name)
            if self.book_value != self.asset_id.value_residual :
                self.book_value = self.asset_id.value_residual

    @api.multi
    def action_open(self):
        self.validity_check()
        for me_id in self :
            if me_id.state != 'draft' :
                continue
            me_id.state = STATES[1][0]

    @api.multi
    def revaluation(self):
        self.ensure_one()
        asset = self.asset_id
        depreciated = asset.value - asset.salvage_value - asset.value_residual
        selisih = self.new_book_value - asset.value_residual
        if selisih > 0 :
            debit_account_id = self.account_id
            credit_account_id = asset.category_id.account_asset_id
        else :
            credit_account_id = self.account_id
            debit_account_id = asset.category_id.account_asset_id
        move_line_vals = []
        move_line_vals.append((0,0,{
            'name': self.asset_id.name,
            'ref': self.name,
            'account_id': debit_account_id.id,
            'debit': abs(selisih),
            'credit': 0,
        }))
        move_line_vals.append((0,0,{
            'name': self.asset_id.name,
            'ref': self.name,
            'account_id': credit_account_id.id,
            'debit': 0,
            'credit': abs(selisih),
        }))
        move_id = self.env['account.move'].sudo().create({
            'line_ids': move_line_vals,
            'journal_id': self.journal_id.id,
            'date': self.date,
        })
        move_id.post()
        self.asset_id.write({
            'value': self.new_book_value + depreciated,
        })
        self.move_id = move_id.id

    @api.multi
    def action_approve(self):
        self.validity_check()
        for me_id in self :
            if me_id.state != 'open' :
                continue
            me_id.revaluation()
            me_id.state = STATES[2][0]

    @api.multi
    def action_cancel(self):
        for me_id in self :
            if me_id.state != 'open' :
                continue
            me_id.state = STATES[0][0]

    @api.onchange('asset_id','book_value')
    def asset_change(self):
        if self.asset_id :
            self.book_value = self.asset_id.value_residual
        else :
            self.book_value = False
