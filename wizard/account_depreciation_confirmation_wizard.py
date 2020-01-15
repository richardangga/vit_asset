from odoo import fields, api, models, _
from odoo.exceptions import Warning

class AccountDepreciationConfirmationWizard(models.TransientModel):
    _inherit = 'asset.depreciation.confirmation.wizard'

    company_ids = fields.Many2many('res.company', string='Company')

    @api.multi
    def asset_compute(self):
        self.ensure_one()
        if self.company_ids :
            context = {}
            for key, value in self._context.items():
                context[key] = value
            if self.company_ids :
                context['company_ids'] = self.company_ids.ids
            self = self.with_context(context)
        return super(AccountDepreciationConfirmationWizard, self).asset_compute()
