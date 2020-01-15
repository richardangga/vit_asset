from odoo import api, fields, models, _
import time
from odoo.exceptions import UserError, Warning
import logging
import datetime
_logger = logging.getLogger(__name__)
STATES = [('draft', 'Draft'), ('open', 'Open'), ('done','Done') ]
TYPES = [('corrective','Corrective'),('preventive','Preventive')]

class maintenance(models.Model):
    _name = 'vit.maintenance'
    _rec_name = 'name'
    _description = 'Asset Maintenance'
    _inherit = ['portal.mixin', 'mail.thread', 'mail.activity.mixin']

    @api.multi
    @api.depends('responsible_id')
    def _get_department(self):
        for me_id in self :
            employee_id = self.env['hr.employee'].search([
                ('user_id','!=',False),
                ('user_id','=',me_id.responsible_id.id)
            ], limit=1)
            me_id.department_id = employee_id and employee_id.department_id.id or False

    @api.depends('line_ids.subtotal')
    def _get_total(self):
        for me_id in self :
            me_id.total = sum(line.subtotal for line in me_id.line_ids)

    name                = fields.Char("Number", readonly=True)
    date                = fields.Date(string="Date", required=True,
                                      readonly=True, states={'draft': [('readonly', False)]},
                                      default=str(datetime.datetime.now()))
    required_date       = fields.Date(string="Required Date", required=False,
                                      readonly=True, states={'draft': [('readonly', False)]},
                                      default=str(datetime.datetime.now()) )
    state               = fields.Selection(string="State", selection=STATES, required=True,
                                           readonly=True, default=STATES[0][0])

    maintenance_type       = fields.Selection(string="Maintenance Type",
                                           readonly=True, states={'draft': [('readonly', False)]},
                                           selection=TYPES, required=True, )
    asset_ids           = fields.Many2many(comodel_name="account.asset.asset",
                                           string="Assets", required=False,
                                           readonly=True, states={'draft': [('readonly', False)]},
                                           )
    notes = fields.Text(string="Notes", required=True, readonly=True, states={'draft': [('readonly', False)]},)


    responsible_id  = fields.Many2one(comodel_name="res.users", string="Responsible", required=False, readonly=True, states={'draft': [('readonly', False)]})
    requested_id    = fields.Many2one(comodel_name="res.users", string="Requested by", required=False, readonly=True, states={'draft': [('readonly', False)]})

    partner_id      = fields.Many2one(comodel_name="res.partner", string="Maintenance Supplier", required=False, readonly=True, states={'draft': [('readonly', False)]})


    line_ids        = fields.One2many(comodel_name="vit.maintenance_line", inverse_name="maintenance_id",
                               string="Parts", required=False, readonly=True, states={'draft': [('readonly', False)]})


    total           = fields.Float(string="Total Parts", compute='_get_total', store=True)
    department_id = fields.Many2one('hr.department', compute='_get_department')

    @api.multi
    def button_dummy(self):
        return True


    @api.model
    def create(self, vals):
        vals['name']    = self.env['ir.sequence'].next_by_code('vit.maintenance')
        return super(maintenance, self).create(vals)

    @api.multi
    def action_open(self):
        self.state = STATES[1][0]

    @api.multi
    def action_done(self):
        if self.state != 'open' :
            return False
        for asset in self.asset_ids :
            asset.last_maintenance_id = self.id
            next_maintenance_id = self.search([
                ('state','=','draft'),
                ('maintenance_type','=','preventive'),
                ('asset_ids','in',asset.id),
            ], order='date asc', limit=1)
            asset.next_maintenance_id = next_maintenance_id and next_maintenance_id.id or False
        self.state = STATES[2][0]

    @api.multi
    def action_cancel(self):
        self.state = STATES[0][0]

    @api.multi
    def unlink(self):
        for me_id in self :
            if me_id.state != 'draft' :
                raise Warning('Tidak bisa menghapus data yang bukan draft !')
        return super(maintenance, self).unlink()

class maintenance_line(models.Model):
    _name = 'vit.maintenance_line'

    @api.multi
    @api.depends('qty','unit_price')
    def get_subtotal(self):
        for me_id in self :
            me_id.subtotal = me_id.qty*me_id.unit_price

    maintenance_id  = fields.Many2one(comodel_name="vit.maintenance",
                                     string="Maintenance", required=False, )

    product_id      = fields.Many2one(comodel_name="product.product",
                                     string="Product/ Service", required=True, )

    qty             = fields.Float(string="Quantity",  required=True, )
    unit_price      = fields.Float(string="Unit Price",  required=True, )
    subtotal        = fields.Float(string="Subtotal",  compute='get_subtotal', store=True)
