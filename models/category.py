from odoo import api, fields, models, _
import time
from odoo.exceptions import UserError, ValidationError
import logging
_logger = logging.getLogger(__name__)
from odoo.osv import expression

class category(models.Model):
    _name = 'account.asset.category'
    _inherit = 'account.asset.category'
    _parent_name = "parent_id"
    _parent_store = True
    _order = 'complete_name'
    _rec_name = 'complete_name'


    code = fields.Char("Code", required=True)
    asset_disposal_loss_id = fields.Many2one(comodel_name="account.account",
                                          string="Loss Disposal Account", required=False, )
    asset_disposal_profit_id = fields.Many2one(comodel_name="account.account",
                                          string="Profit Disposal Account", required=False, )
    parent_id = fields.Many2one('account.asset.category', 'Parent Category', ondelete='cascade')
    child_id = fields.One2many('account.asset.category', 'parent_id', 'Child Categories')
    parent_path = fields.Char(index=True)
    # parent_left = fields.Integer('Left Parent')
    # parent_right = fields.Integer('Right Parent')
    complete_name = fields.Char("Full Category Name", compute='_compute_complete_name', store=True)
    complete_code = fields.Char("Full Code", compute='_compute_complete_code', store=True)
    hierarchy_type = fields.Selection([('normal','Normal'),('view','View')], string='Hierarchy Type', required=True, default='normal')
    account_asset_id = fields.Many2one('account.account', string='Asset Account', required=False, domain=[('internal_type','=','other'), ('deprecated', '=', False)], help="Account used to record the purchase of the asset at its original price.")
    account_depreciation_id = fields.Many2one('account.account', string='Depreciation Entries: Asset Account', required=False, domain=[('internal_type','=','other'), ('deprecated', '=', False)], help="Account used in the depreciation entries, to decrease the asset value.")
    account_depreciation_expense_id = fields.Many2one('account.account', string='Depreciation Entries: Expense Account', required=False, domain=[('internal_type','=','other'), ('deprecated', '=', False)], oldname='account_income_recognition_id', help="Account used in the periodical entries, to record a part of the asset as expense.")
    journal_id = fields.Many2one('account.journal', string='Journal', required=False)

    @api.constrains('parent_id')
    def _check_category_recursion(self):
        if not self._check_recursion():
            raise ValidationError(_('Error ! You cannot create recursive categories.'))
        return True

    @api.one
    @api.depends('name', 'parent_id.complete_name')
    def _compute_complete_name(self):
        if self.parent_id.complete_name:
            self.complete_name = '%s / %s' % (self.parent_id.complete_name, self.name)
        else:
            self.complete_name = self.name

    @api.one
    @api.depends('code', 'parent_id.complete_code')
    def _compute_complete_code(self):
        if self.parent_id.complete_code:
            self.complete_code = '%s.%s' % (self.parent_id.complete_code, self.code)
        else:
            self.complete_code = self.code

    @api.multi
    def name_get(self):
        result = []
        for me_id in self :
            result.append((me_id.id, me_id.complete_name))
        return result

    @api.model
    def name_search(self, name, args=None, operator='ilike', limit=100):
        args = args or []
        if name :
            recs = self.search([
                '|','|',
                ('name', operator, name),
                ('complete_name', operator, name),
                ('complete_code', operator, name)
            ] + args, limit=limit)
        else :
            recs = self.search([] + args, limit=limit)
        return recs.name_get()
