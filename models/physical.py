from odoo import api, fields, models, _
import time
from odoo.exceptions import UserError, Warning
import logging
_logger = logging.getLogger(__name__)
from odoo.addons import decimal_precision as dp
import datetime

ASSET_CONDITION = [('new','New'), ('good', 'Good'), ('broken', 'Broken'), ('heavily_broken', 'Heavily Broken'),]
STATES = [('draft', 'Draft'), ('open', 'Open'), ('done','Done')]

class VitPhysical(models.Model):
    _name = "vit.physical"
    _description = "Physical Check"
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

    name = fields.Char('Name', readonly=True, default='/')
    date = fields.Date(string="Date", required=True,
                       readonly=True, states={'draft': [('readonly', False)]},
                       default=str(datetime.datetime.now()))
    state = fields.Selection(string="State", selection=STATES, readonly=True, default=STATES[0][0])
    physical_lines = fields.One2many(comodel_name='vit.physical.line', inverse_name='physical_id', readonly=True, states={'draft': [('readonly', False)], 'open': [('readonly', False)]},)
    last_location_id = fields.Many2one(comodel_name="vit.location", string="Location", required=False, readonly=True, states={'draft': [('readonly', False)]},)
    user_id = fields.Many2one(comodel_name="res.users", string="Responsible", required=True, readonly=True, states={'draft': [('readonly', False)]}, default=lambda self: self.env.user.id)
    notes           = fields.Text(string="Notes", required=True, readonly=True, states={'draft': [('readonly', False)]},)
    company_id = fields.Many2one('res.company', 'Company', required=True, default=lambda self: self.env['res.company']._company_default_get(), readonly=True, states={'draft': [('readonly', False)]})
    journal_id = fields.Many2one(comodel_name="account.journal",
        readonly=True, states={'draft': [('readonly', False)], 'open': [('readonly', False)]},
        string="Journal", required=False, track_visibility='onchange')
    department_id = fields.Many2one('hr.department', compute='_get_department')

    @api.multi
    def validity_check(self):
        self.ensure_one()
        if not self.physical_lines :
            raise Warning("Detil aset kosong.")

    @api.model
    def create(self, vals):
        vals['name']    = self.env['ir.sequence'].next_by_code('vit.physical')
        return super(VitPhysical, self).create(vals)

    @api.multi
    def compute_asset(self):
        self.ensure_one()
        domain = [
            ('existence','in',['exist','under_maintenance']),
            ('asset_id','!=',False),
            ('state','=','open'),
        ]
        if self.last_location_id :
            domain.append(('last_location_id','=',self.last_location_id.id))
        asset_ids = self.env['account.asset.asset'].search(domain)
        for asset_id in asset_ids :
            self.physical_lines.create({
                'physical_id': self.id,
                'asset_id': asset_id.id,
                'condition': asset_id.condition,
                'last_location_id': asset_id.last_location_id.id,
                'real_last_location_id': asset_id.last_location_id.id,
                'qty': 1,
                'real_qty': 1,
            })

    @api.multi
    def create_write_off_journal(self, asset):
        self.ensure_one()
        if not self.journal_id :
            raise Warning("Silahkan input jurnal.")
        move_line_vals = []
        categ = asset.category_id
        #credit
        move_line_vals.append((0, 0, {
            'account_id' : categ.account_asset_id.id,
            'name' : '%s %s'%(asset.code,asset.name),
            'debit' : 0,
            'credit': asset.value,
            'date_maturity' : self.date,
            'ref' : self.name,
        }))

        #debit
        move_line_vals.append((0, 0, {
            'account_id' : categ.account_depreciation_id.id,
            'name' : '%s %s'%(asset.code,asset.name),
            'debit' : asset.value - asset.value_residual,
            'credit': 0,
            'date_maturity' : self.date,
            'ref' : self.name,
        }))
        if asset.value_residual > 0 :
            move_line_vals.append((0, 0, {
                'account_id' : categ.asset_disposal_loss_id.id,
                'name' : '%s %s'%(asset.code,asset.name),
                'debit' : asset.value_residual,
                'credit': 0,
                'date_maturity' : self.date,
                'ref' : self.name,
              }))

        move_id = self.env['account.move'].create({
            "journal_id": self.journal_id.id,
            "ref": self.name,
            "date": self.date,
            "narration": self.notes,
            "line_ids": move_line_vals,
        })
        move_id.post()

    @api.multi
    def update_assets(self):
        self.ensure_one()
        for line in self.physical_lines :
            if not line.real_qty :
                self.create_write_off_journal(line.asset_id)
                line.asset_id.action_close({'existence':'not_exist'})
            to_write = {}
            if line.condition != line.asset_id.condition :
                to_write['condition'] = line.condition
            if line.real_last_location_id != line.asset_id.last_location_id :
                to_write['last_location_id'] = line.real_last_location_id.id
            if to_write :
                line.asset_id.write(to_write)

    @api.multi
    def action_open(self):
        self.compute_asset()
        self.state = STATES[1][0]

    @api.multi
    def action_approve(self):
        self.validity_check()
        self.update_assets()
        self.state = STATES[2][0]

    @api.multi
    def action_cancel(self):
        self.physical_lines.unlink()
        self.state = STATES[0][0]

    @api.multi
    def unlink(self):
        for me_id in self :
            if me_id.state != 'draft' :
                raise Warning('Tidak bisa menghapus data yang bukan draft !')
        return super(VitPhysical, self).unlink()

class VitPhysicalLine(models.Model):
    _name = "vit.physical.line"
    _description = "Physical Check Line"
    _rec_name = 'asset_id'

    physical_id = fields.Many2one(comodel_name='vit.physical', string='Physical Check', ondelete='cascade')
    asset_id = fields.Many2one(comodel_name='account.asset.asset', string='Asset', required=True, readonly=True)
    condition = fields.Selection(string="Physical Condition",
        selection=ASSET_CONDITION,
        required=False, )
    last_location_id = fields.Many2one(comodel_name="vit.location", string="Location", required=False, readonly=True)
    real_last_location_id = fields.Many2one(comodel_name="vit.location", string="Real Location", required=False)
    qty = fields.Float(string='Qty', digits=dp.get_precision('Product Unit of Measure'), readonly=True)
    real_qty = fields.Float(string='Real Qty', digits=dp.get_precision('Product Unit of Measure'), required=True)

    @api.onchange('real_qty')
    def qty_change(self):
        if self.real_qty > 1 :
            self.real_qty = 1
