from odoo import api, fields, models, _
import time
from odoo.exceptions import UserError, Warning
import logging
_logger = logging.getLogger(__name__)
import odoo.addons.decimal_precision as dp
import datetime

STATES = [('draft', 'Draft'), ('open', 'Open'), ('done','Done') ]
TYPES = [('writeoff','Write Off'),('sale','Sale')]

class disposal(models.Model):
    _name = "vit.disposal"
    _rec_name = 'name'
    _description = 'asset disposal'
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

    name                = fields.Char("Number", readonly=True)
    date                = fields.Date(string="Date", required=True,
                                      readonly=True, states={'draft': [('readonly', False)]},
                                      default=str(datetime.datetime.now()) )
    state               = fields.Selection(string="State", selection=STATES, required=True,
                                           readonly=True, default=STATES[0][0],
                                           track_visibility='onchange')
    disposal_type       = fields.Selection(string="Disposal Type",
                                           readonly=True, states={'draft': [('readonly', False)]},
                                           selection=TYPES, required=True,
                                           track_visibility='onchange')
    disposal_line           = fields.One2many(comodel_name="vit.disposal.line", inverse_name='disposal_id',
                                           string="Disposal Line", required=True,
                                           readonly=True, states={'draft': [('readonly', False)]},
                                           )

    disposal_journal_id = fields.Many2one(comodel_name="account.journal",
                                          readonly=True, states={'draft': [('readonly', False)]},
                                          string="Disposal Journal", required=False, )
    disposal_move_id    = fields.Many2one(comodel_name="account.move", string="Disposal Entry", readonly=True, 
                                           copy=False,)

    #sale
    disposal_customer_id    = fields.Many2one(comodel_name="res.partner",
                                              readonly=True, states={'draft': [('readonly', False)]},
                                              string="Customer", required=False, )
    disposal_invoice_id     = fields.Many2one(comodel_name="account.invoice", string="Disposal Invoice", readonly=True, 
                                               copy=False,)
    amount                  = fields.Float(string="Sale Amount",  required=False,
                                           readonly=True, states={'draft': [('readonly', False)]},)
    payment_account_id = fields.Many2one(comodel_name="account.account",
                                          readonly=True, states={'draft': [('readonly', False)]},
                                          string="Payment Account", )

    notes = fields.Text(string="Notes", required=True, readonly=True, states={'draft': [('readonly', False)]},)
    user_id = fields.Many2one(comodel_name="res.users", string="Responsible", required=True, readonly=True, states={'draft': [('readonly', False)]}, default=lambda self: self.env.user.id)
    department_id = fields.Many2one('hr.department', compute='_get_department', store=True)

    @api.model
    def create(self, vals):
        vals['name']    = self.env['ir.sequence'].next_by_code('vit.disposal')
        return super(disposal, self).create(vals)

    @api.onchange('disposal_type')
    def type_change(self):
      if self.disposal_type != 'sale' :
        self.payment_account_id = False
        self.disposal_line.write({'amount':0})

    @api.multi
    def validity_check(self):
      for me_id in self :
        if me_id.disposal_type == 'sale' :
          if not self.payment_account_id :
            if not self.disposal_journal_id :
              raise Warning("Silahkan input disposal journal.")
            elif not self.disposal_account_id :
              raise Warning("Silahkan input disposal account.")
            elif not self.disposal_customer_id.property_account_receivable_id :
              raise Warning("Silahkan lengkapi Account Receivable untuk customer %s."%self.disposal_customer_id.name)
        for line in me_id.disposal_line :
          if line.disposal_id.disposal_type == 'sale' and not line.amount :
            raise Warning("Sale amount tidak boleh 0.")
          if line.asset_id.existence in ('sold','writeoff'):
            raise Warning("Asset %s sudah didispos sebelumnya."%(line.asset_id.name_get()[0][1]))
          category_id = line.asset_id.category_id
          if not category_id.asset_disposal_loss_id or not category_id.asset_disposal_profit_id :
            raise Warning("Silahkan lengkapi data account disposal untuk Asset Type %s"%category_id.name)
          if not category_id.account_asset_id or not category_id.account_depreciation_id :
            raise Warning("Silahkan lengkapi Account di master Asset Type %s"%category_id.name)

    @api.multi
    def unlink(self):
        for me_id in self :
            if me_id.state != 'draft' :
                raise Warning('Tidak bisa menghapus data yang bukan draft !')
        return super(disposal, self).unlink()

    #todo
    # @api.multi
    # def create_invoice(self):
    #   self.ensure_one()
    #   if self.disposal_type != 'sale' :
    #     return
    #   inv_line_vals = []
    #   inv_line_vals.append((0,0,{
    #     'name': 'Disposal %s'%(self.name),
    #     'account_id': self.disposal_account_id.id,
    #     'quanity': 1,
    #     'price_unit': 0,
    #   }))
    #   invoice_id = self.env['account.invoice'].create({
    #     'partner_id': self.disposal_customer_id.id,
    #     'journal_id': self.disposal_journal_id.id,
    #     'account_id': self.disposal_customer_id.property_account_receivable_id.id,
    #     'type': 'out_invoice',
    #     'origin': self.name,
    #     'invoice_line_ids': inv_line_vals,
    #     'comment': self.notes,
    #   })
    #   self.write({'disposal_invoice_id':invoice_id.id})

    @api.multi
    def create_write_off_journal(self):
      self.ensure_one()
      if self.disposal_type != 'writeoff' :
        return
      move_line_vals = []
      for line in self.disposal_line :
        asset = line.asset_id
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
          "journal_id": self.disposal_journal_id.id,
          "ref": self.name,
          "date": self.date,
          "narration": self.notes,
          "line_ids": move_line_vals,
      })
      move_id.post()
      self.write({'disposal_move_id':move_id.id})

    @api.multi
    def create_sale_journal(self):
      self.ensure_one()
      if self.disposal_type != 'sale' :
        return
      move_line_vals = []
      for line in self.disposal_line :
        asset = line.asset_id
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
          'account_id' : self.payment_account_id.id,
          'partner_id': self.disposal_customer_id.id,
          'name' : '%s %s'%(asset.code,asset.name),
          'debit' : line.amount,
          'credit': 0,
          'date_maturity' : self.date,
          'ref' : self.name,
        }))
        if asset.value - asset.value_residual :
          move_line_vals.append((0, 0, {
            'account_id' : categ.account_depreciation_id.id,
            'name' : '%s %s'%(asset.code,asset.name),
            'debit' : asset.value - asset.value_residual,
            'credit': 0,
            'date_maturity' : self.date,
            'ref' : self.name,
          }))

        #debit or credit
        if asset.value_residual > line.amount : #rugi
          move_line_vals.append((0, 0, {
            'account_id' : categ.asset_disposal_loss_id.id,
            'name' : '%s %s'%(asset.code,asset.name),
            'debit' : asset.value_residual - line.amount,
            'credit': 0,
            'date_maturity' : self.date,
            'ref' : self.name,
          }))
        elif asset.value_residual < line.amount : #untung
          move_line_vals.append((0, 0, {
            'account_id' : categ.asset_disposal_profit_id.id,
            'name' : '%s %s'%(asset.code,asset.name),
            'debit' : 0,
            'credit': line.amount - asset.value_residual,
            'date_maturity' : self.date,
            'ref' : self.name,
          }))

      move_id = self.env['account.move'].create({
          "journal_id": self.disposal_journal_id.id,
          "ref": self.name,
          "date": self.date,
          "narration": self.notes,
          "line_ids": move_line_vals,
      })
      move_id.post()
      self.write({'disposal_move_id':move_id.id})

    @api.multi
    def action_open(self):
      self.validity_check()
      self.write({'state':STATES[1][0]})

    @api.multi
    def action_approve(self):
      self.validity_check()
      for me_id in self :
        if me_id.state != 'open' :
          continue
        if me_id.disposal_type == 'sale' :
          existence = 'sold'
          me_id.create_sale_journal()
        else :
          existence = 'writeoff'
          me_id.create_write_off_journal()
        for line in me_id.disposal_line :
          line.asset_id.action_close({'existence':existence})
      self.write({'state':STATES[2][0]})

    @api.multi
    def action_cancel(self):
        self.state = STATES[0][0]

class VitDisposalLine(models.Model):
    _name = "vit.disposal.line"
    _description = "Disposal Line"

    asset_id = fields.Many2one('account.asset.asset', string='Asset', ondelete='restrict', required=True)
    value_residual = fields.Float(string='Residual Value', digits=dp.get_precision('Unit Price'), related='asset_id.value_residual')
    disposal_id = fields.Many2one('vit.disposal', string='Disposal', ondelete='cascade')
    amount = fields.Float(string='Sale Amount', digits=dp.get_precision('Unit Price'))

    @api.onchange('amount')
    def amount_change(self):
      if self.disposal_id.disposal_type != 'sale' :
        self.amount = 0
