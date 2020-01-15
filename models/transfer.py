from odoo import api, fields, models, _
import time
from odoo.exceptions import UserError
import json
import logging
from odoo.exceptions import Warning
_logger = logging.getLogger(__name__)
STATES = [('draft', 'Draft'), ('open', 'Open'), ('done','Done') ]
import datetime

class transfer(models.Model):
    _name = "vit.transfer"
    _description = "Asset Transfer"
    _inherit = ['portal.mixin', 'mail.thread', 'mail.activity.mixin']

    @api.depends('company_src_id','company_dest_id')
    @api.multi
    def _is_interco(self):
        for me_id in self :
            me_id.is_interco = me_id.company_src_id != me_id.company_dest_id

    @api.multi
    @api.depends('user_id')
    def _get_employee(self):
        for me_id in self :
            employee_id = self.env['hr.employee'].search([
                ('user_id','!=',False),
                ('user_id','=',me_id.user_id.id)
            ], limit=1)
            me_id.department_id = employee_id and employee_id.department_id.id or False
            me_id.employee_id = employee_id and employee_id.id or False

    name            = fields.Char("Number", readonly=True)
    date            = fields.Date(string="Transfer Date",
                                  default=str(datetime.datetime.now()),
                                  readonly=True, states={'draft': [('readonly', False)]},
                                  required=True, )

    notes           = fields.Text(string="Notes", required=True,
                                  readonly=True, states={'draft': [('readonly', False)]},)

    location_id         = fields.Many2one(comodel_name="vit.location",
                                          string="Source Location", required=True,
                                          readonly=True, states={'draft': [('readonly', False)]},)
    location_dest_id = fields.Many2one(comodel_name="vit.location",
                                       string="Destination Location", required=True,
                                       readonly=True, states={'draft': [('readonly', False)]},)

    asset_line           = fields.One2many(comodel_name="vit.transfer.line", inverse_name='transfer_id',
                                           string="Assets", required=False,
                                           readonly=True, states={'draft': [('readonly', False)]},
                                           )
    company_src_id = fields.Many2one(comodel_name="res.company",
                                       string="Source Company", required=True,
                                       readonly=True, states={'draft': [('readonly', False)]},
                                       default=lambda self: self.env.user.company_id.id,
                                       track_visibility='onchange')
    company_dest_id = fields.Many2one(comodel_name="res.company",
                                       string="Destination Company", required=True,
                                       readonly=True, states={'draft': [('readonly', False)]},
                                       default=lambda self: self.env.user.company_id.id,
                                       track_visibility='onchange')

    state = fields.Selection(string="State", selection=STATES, required=True, readonly=True,
                             default=STATES[0][0])
    is_interco = fields.Boolean(string='Interco', readonly=True, states={'draft': [('readonly', False)]}, compute='_is_interco', store=True)
    user_id = fields.Many2one(comodel_name="res.users", string="Responsible", required=True, readonly=True, states={'draft': [('readonly', False)]})
    department_id = fields.Many2one('hr.department', compute='_get_employee')
    employee_id = fields.Many2one('hr.employee', compute='_get_employee')
    ga_id = fields.Many2one(comodel_name="res.users", string="General Affair", readonly=True, states={'draft': [('readonly', False)]}, default=lambda self: self.env.user.id)
    
    @api.onchange('company_src_id','company_dest_id')
    def interco_change(self):
        if self.location_id and self.location_id.company_id != self.company_src_id :
            self.location_id = False
        if self.location_dest_id and self.location_dest_id.company_id != self.company_dest_id :
            self.location_dest_id = False

    @api.onchange('location_id')
    def location_change(self):
        self.asset_line = False

    @api.model
    def create(self, vals):
        vals['name']    = self.env['ir.sequence'].next_by_code('vit.transfer')
        return super(transfer, self).create(vals)

    @api.multi
    def validity_check(self):
        for me_id in self :
            if not me_id.asset_line :
                raise Warning("Silahkan input detail asset.")
            if me_id.location_id == me_id.location_dest_id :
                raise Warning("Source location dan destination location tidak boleh sama.")

    def custom_report(self):
        hari = {
            0: 'Senin',
            1: 'Selasa',
            2: 'Rabu',
            3: 'Kamis',
            4: 'Jum\'at',
            5: 'Sabtu',
            6: 'Minggu',
        }
        date_time = time.strptime(self.date, '%Y-%m-%d')
        date = '%s-%s-%s'%(self.date[8:10],self.date[5:7],self.date[0:4])
        day_int = date_time.tm_wday
        return {
            'hari': hari[day_int],
            'tanggal': date,
        }

    @api.multi
    def action_open(self):
        self.validity_check()
        self.state = STATES[1][0]
        if not self.is_interco or not sum(line.asset_id.value_residual for line in self.asset_line) :
            self.action_approve()

    @api.multi
    def action_approve(self):
        self.ensure_one()
        self.validity_check()
        if self.is_interco :
            self.create_journal()
        else :
            for ass in self.asset_line:
                ass.asset_id.last_location_id = self.location_dest_id
        self.state = STATES[2][0]

    @api.multi
    def action_cancel(self):
        self.state = STATES[0][0]

    @api.multi
    def create_journal(self):
        for line in self.asset_line :
            asset = line.asset_id
            categ = asset.category_id
            if not self.env.user.company_id.intercompany_payable_id or not self.env.user.company_id.intercompany_receivable_id :
                raise Warning("Silahkan lengkapi data intercompany payable & receivable %s"%(self.env.user.company_id.name))
            if not categ.journal_id :
                raise Warning("Silahkan lengkapi data journal asset category %s"%categ.name)
            if not line.category_id :
                raise Warning("Silahkan lengkapi data category baru untuk asset %s"%line.asset_id.name_get()[0][1])

            new_asset_id = asset.copy({
                'code': False,
                'name': asset.name,
                'category_id': line.category_id.id,
                'value': asset.value_residual,
                'company_id': line.transfer_id.company_dest_id.id,
                'asset_id': False,
                'last_location_id': self.location_dest_id.id,
            })
            new_asset_id.name = asset.name
            new_asset_id.confirm_ga()
            new_asset_id.validate()

            if not line.asset_id.value_residual :
                continue

            #COMPANY SOURCE
            #credit
            move_line_vals = []
            move_line_vals.append((0, 0, {
                'account_id' : categ.account_asset_id.id,
                'name' : '%s %s'%(asset.code,asset.name),
                'debit' : 0,
                'credit': asset.value_residual,
                'date_maturity' : self.date,
                'ref' : self.name,
            }))

            #debit
            move_line_vals.append((0, 0, {
                'account_id' : self.env.user.company_id.intercompany_receivable_id.id,
                'name' : '%s %s'%(asset.code,asset.name),
                'debit' : asset.value_residual,
                'credit': 0,
                'date_maturity' : self.date,
                'ref' : self.name,
            }))

            move_id = self.env['account.move'].create({
                "journal_id": asset.category_id.journal_id.id,
                "ref": self.name,
                "date": self.date,
                "narration": self.notes,
                "line_ids": move_line_vals,
            })
            move_id.post()

            #company destination
            move_line_vals = []
            move_line_vals.append((0, 0, {
                'account_id' : line.category_id.account_asset_id.id,
                'name' : '%s %s'%(asset.code,asset.name),
                'debit' : asset.value_residual,
                'credit': 0,
                'date_maturity' : self.date,
                'ref' : self.name,
            }))

            #debit
            move_line_vals.append((0, 0, {
                'account_id' : self.env.user.company_id.intercompany_payable_id.id,
                'name' : '%s %s'%(asset.code,asset.name),
                'debit' : 0,
                'credit': asset.value_residual,
                'date_maturity' : self.date,
                'ref' : self.name,
            }))

            move_id = self.env['account.move'].create({
                "journal_id": line.category_id.journal_id.id,
                "ref": self.name,
                "date": self.date,
                "narration": self.notes,
                "line_ids": move_line_vals,
            })
            move_id.post()
            asset.action_close({'existence':'not_exist'})

    @api.onchange('company_dest_id')
    def company_des_change(self):
        self.asset_line = False

    @api.multi
    def action_view_entries(self):
        move_ids = self.env['account.move'].search([
            ('ref','=',self.name)
        ])
        action = self.env.ref('account.action_move_journal_line')
        return {
            'name': action.name,
            'help': action.help,
            'type': action.type,
            'view_type': action.view_type,
            'view_mode': action.view_mode,
            'target': action.target,
            'res_model': action.res_model,
            'domain': [('id', 'in', move_ids.ids)],
        }

    @api.multi
    def unlink(self):
        for me_id in self :
            if me_id.state != 'draft' :
                raise Warning('Tidak bisa menghapus data yang bukan draft !')
        return super(transfer, self).unlink()

class VitTransferLine(models.Model):
    _name = "vit.transfer.line"
    _description = "Asset Transfer Line"
    _rec_name = 'asset_id'

    asset_id = fields.Many2one('account.asset.asset', string='Asset', required=True)
    transfer_id = fields.Many2one('vit.transfer', string='Transfer', ondelete='cascade')
    is_interco = fields.Boolean(string='Intercompany', related='transfer_id.is_interco')
    company_dest_id = fields.Many2one(string='Destination Company', related='transfer_id.company_dest_id')
    location_id = fields.Many2one(string='Destination Location', related='transfer_id.location_dest_id')
    category_id = fields.Many2one('account.asset.category', string='Category')
    description = fields.Text(string='Description')

    @api.onchange('asset_id')
    def asset_change(self):
        self.company_dest_id = self.transfer_id.company_dest_id.id
        self.location_id = self.transfer_id.location_id.id
        self.is_interco = self.transfer_id.is_interco
        