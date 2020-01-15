from odoo import api, fields, models, _
import time
from odoo.exceptions import UserError
import logging
_logger = logging.getLogger(__name__)

class invoice_line(models.Model):
    _name = 'account.invoice.line'
    _inherit = 'account.invoice.line'

    @api.one
    def asset_create(self):
        asset=False
        if self.asset_category_id:
            po = self.env['purchase.order'].search([('name','=',self.invoice_id.origin)])
            vals = {
                'name': self.name,
                'code': False,
                'category_id': self.asset_category_id.id,
                'value': self.price_subtotal_signed,
                'partner_id': self.invoice_id.partner_id.id,
                'company_id': self.invoice_id.company_id.id,
                'currency_id': self.invoice_id.company_currency_id.id,
                'date': self.invoice_id.date_invoice,
                'invoice_id': self.invoice_id.id,
                'qty': self.quantity,
                'purchase_order_id': po[0].id if po else False,
                'shipping_id': po[:1].picking_ids[:1].id if po else False,
                'account_analytic_id': self.account_analytic_id.id,
                'analytic_tag_ids': [(6, 0, [analytic_tag_id.id for analytic_tag_id in self.analytic_tag_ids])] if self.analytic_tag_ids else False,
            }
            changed_vals = self.env['account.asset.asset'].onchange_category_id_values(vals['category_id'])
            vals.update(changed_vals['value'])
            asset = self.env['account.asset.asset'].create(vals)
            # if self.asset_category_id.open_asset:
            #     asset.validate()
        return asset
