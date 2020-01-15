from odoo import api, fields, models, _
import time
from odoo.exceptions import UserError, Warning
import logging
from dateutil import relativedelta
_logger = logging.getLogger(__name__)
from datetime import datetime, timedelta
import pdb

ASSET_CONDITION=[('new','New'), ('good', 'Good'), ('broken', 'Broken'), ('heavily_broken', 'Heavily Broken'),]
EXISTENCE=[('exist','Exist'), ('not_exist','Not Exist'), ('sold','Sold'), ('writeoff','Write Off'), ('under_maintenance','Under Maintenace'),]

class asset(models.Model):
    _name = 'account.asset.asset'
    _inherit = 'account.asset.asset'

    @api.multi
    def _compute_count(self):
        for me_id in self :
            me_id.maintenance_count = me_id.maintenance_ids and len(me_id.maintenance_ids) or 0
            me_id.mutation_count = me_id.mutation_ids and len(me_id.mutation_ids) or 0
            me_id.disposal_count = me_id.disposal_ids and len(me_id.disposal_ids) or 0
            me_id.reclass_count = me_id.reclass_ids and len(me_id.reclass_ids) or 0
            me_id.reval_count = me_id.reval_ids and len(me_id.reval_ids) or 0

    @api.multi
    @api.depends('disposal_line_ids')
    def _get_disposal(self):
        for me_id in self :
            me_id.disposal_ids = me_id.disposal_line_ids.mapped('disposal_id')

    @api.multi
    @api.depends('responsible_id')
    def _get_department(self):
        # pdb.set_trace()
        for me_id in self :
            employee_id = self.env['hr.employee'].search([
                ('user_id','!=',False),
                ('user_id','=',me_id.responsible_id.id)
            ], limit=1)
            me_id.department_id = employee_id and employee_id.department_id.id or False

    # details
    asset_ids = fields.One2many(comodel_name="account.asset.asset",
                                inverse_name="asset_id", string="Details", required=False, )

    # parent
    asset_id = fields.Many2one(comodel_name="account.asset.asset",
                               string="Parent Asset", required=False,
                               readonly=True, states={'draft': [('readonly', False)]},
                               ondelete='cascade')

    qty = fields.Integer(string="Quantity",
                         help="Purchase Quantity",
                         required=True, readonly=True, states={'draft': [('readonly', False)]},
                         default=1)


    purchase_order_id = fields.Many2one(comodel_name="purchase.order", string="PO", required=False, )
    shipping_id         = fields.Many2one(comodel_name="stock.picking", string="Receiving", required=False, )
    date_received       = fields.Date(string="Received Date", required=False, )


    manufacturer_id     = fields.Many2one(comodel_name="res.partner",
                                      string="Manufacturer", required=False,
                                      domain=[('category_id','ilike','manufacturer')])

    brand               = fields.Char(string="Brand", required=False, )
    model               = fields.Char(string="Model", required=False, )
    color               = fields.Char(string="Color", required=False, )
    serial_number       = fields.Char(string="Serial Number", required=False, )

    responsible_id = fields.Many2one(comodel_name="res.users", string="Responsible", required=False, readonly=True, states={'draft': [('readonly', False)]})

    #warranty
    warranty_name       = fields.Char("Warranty Number", required=False)
    warranty_description = fields.Text("Description", required=False)
    warranty_date       = fields.Date(string="Warranty Date", required=False, )
    warranty_service_provider_id = fields.Many2one(comodel_name="res.partner",
                                          string="Service Provider", required=False,
                                          domain=[('category_id', 'ilike', 'service provider')])



    #movement history
    last_location_id = fields.Many2one(comodel_name="vit.location", string="Last Location", ondelete='restrict', track_visibility='onchange', required=False, readonly=True, states={'draft': [('readonly', False)]})
    asset_move_ids = fields.One2many(comodel_name="vit.asset_location", inverse_name="asset_id",
                                     string="Asset Location Movement", required=False, )


    condition = fields.Selection(string="Physical Condition",
                                 selection=ASSET_CONDITION, track_visibility='onchange',
                                 required=False, readonly=True, states={'draft': [('readonly', False)]})
    existence = fields.Selection(string="Existence",
                                 selection=EXISTENCE, track_visibility='onchange',
                                 default='exist', readonly=True, states={'draft': [('readonly', False)]})
    account_id = fields.Many2one('account.account','Credit Account', help="Jika CoA ini diisi maka akun credit pada jurnal depresiasi akan menggunakan CoA ini")
    description = fields.Text("Description")
    maintenance_ids = fields.Many2many('vit.maintenance', 'account_asset_asset_vit_maintenance_rel', 'account_asset_asset_id', 'vit_maintenance_id', string='Maintenances')
    maintenance_count = fields.Integer(compute='_compute_count')
    disposal_line_ids = fields.One2many('vit.disposal.line', 'asset_id', string='Disposal Line')
    disposal_ids = fields.Many2many('vit.disposal', 'account_asset_asset_vit_disposal_rel', 'account_asset_asset_id', 'vit_disposal_id', string='Disposal', store=True, compute='_get_disposal')
    disposal_count = fields.Integer(compute='_compute_count')
    mutation_ids = fields.Many2many('vit.transfer', 'account_asset_asset_vit_transfer_rel', 'account_asset_asset_id', 'vit_transfer_id', string='Mutations')
    mutation_count = fields.Integer(compute='_compute_count')
    reclass_ids = fields.Many2many('vit.reclass', 'account_asset_asset_vit_reclass_rel', 'account_asset_asset_id', 'vit_reclass_id', string='Reclass')
    reclass_count = fields.Integer(compute='_compute_count')
    reval_ids = fields.One2many('vit.reval', 'asset_id', string='Revaluation', copy=False)
    reval_count = fields.Integer(compute='_compute_count')
    account_analytic_id = fields.Many2one('account.analytic.account', string='Analytic Account', readonly=True, states={'draft': [('readonly', False)]})
    analytic_tag_ids = fields.Many2many('account.analytic.tag', string='Analytic Tags', readonly=True, states={'draft': [('readonly', False)]})
    state = fields.Selection([('draft', 'Draft'), ('confirm', 'Confirm'), ('open', 'Running'), ('close', 'Close')], 'Status', required=True, copy=False, default='draft',
        help="When an asset is created, the status is 'Draft'.\n"
            "If the asset is confirmed, the status goes in 'Running' and the depreciation lines can be posted in the accounting.\n"
            "You can manually close an asset when the depreciation is over. If the last line of depreciation is posted, the asset automatically goes in that status.")
    value = fields.Float(string='Gross Value', required=True, readonly=True, digits=0, states={'draft': [('readonly', False)]}, oldname='purchase_value', track_visibility='onchange')
    salvage_value = fields.Float(string='Salvage Value', digits=0, readonly=True, states={'draft': [('readonly', False)]},
        help="It is the amount you plan to have that you cannot depreciate.", track_visibility='onchange')
    department_id = fields.Many2one('hr.department', compute='_get_department', store=True)
    image = fields.Binary(string="Image")
    transmisi = fields.Char('Transmisi', readonly=True, states={'draft': [('readonly', False)]})
    no_mesin = fields.Char('No Mesin', readonly=True, states={'draft': [('readonly', False)]})
    no_rangka = fields.Char('No Rangka', readonly=True, states={'draft': [('readonly', False)]})
    silinder = fields.Char('Silinder', readonly=True, states={'draft': [('readonly', False)]})
    tahun_pembuatan = fields.Char('Tahun Pembuatan', readonly=True, states={'draft': [('readonly', False)]})
    city = fields.Char('City', readonly=True, states={'draft': [('readonly', False)]})
    code = fields.Char(string='Reference', size=32, readonly=True)
    status_kepemilikan = fields.Selection(string="Status Kepemilikan",
        selection=[('Sewa','Sewa'),('Beli','Beli')],
        default='Beli', readonly=True, states={'draft': [('readonly', False)]})
    start_date = fields.Date(string='Start Date', readonly=True, states={'draft': [('readonly', False)]})
    end_date = fields.Date(string='End Date', readonly=True, states={'draft': [('readonly', False)]})
    nilai_sewa = fields.Float(string='Nilai Sewa', digits=0, readonly=True, states={'draft': [('readonly', False)]})
    due_date = fields.Date(string='Due Date', readonly=True, states={'draft': [('readonly', False)]})
    lama_sewa = fields.Integer(string='Lama Sewa (bulan)', readonly=True, states={'draft': [('readonly', False)]})
    sewa_lines = fields.One2many('vit.asset.sewa', 'asset_id', string='Sewa', copy=False, readonly=True, states={'draft': [('readonly', False)], 'confirm': [('readonly', False)]})

    @api.model
    def create(self, vals):
        return super(asset, self).create(vals)

    @api.multi
    def create_detail_sewa(self):
        self.ensure_one()
        if self.asset_id :
            if not self.lama_sewa or not self.nilai_sewa :
                return False
            for x in range(self.lama_sewa):
                nilai_sewa = self.nilai_sewa/self.lama_sewa
                if x != 0 :
                    due_date = datetime.strptime(self.due_date, '%Y-%m-%d')
                    due_date = due_date + relativedelta.relativedelta(months=+x)
                else :
                    due_date = self.due_date
                self.env['vit.asset.sewa'].create({
                    'asset_id': self.id,
                    'nilai_sewa': nilai_sewa,
                    'due_date': due_date,
                    'sequence': x+1,
                })

    @api.onchange('status_kepemilikan')
    def kepemilikan_change(self):
        self.start_date = False
        self.end_date = False
        self.nilai_sewa = False

    @api.onchange('start_date','end_date')
    def date_change(self):
        if self.start_date and self.end_date :
            start_date = datetime.strptime(str(self.start_date), '%Y-%m-%d').date()
            end_date = datetime.strptime(str(self.end_date), '%Y-%m-%d').date()
            bulan = (end_date - start_date).days/30
            self.lama_sewa = bulan

    @api.multi
    def write(self, vals):
        return super(asset, self).write(vals)

    @api.multi
    def set_to_draft(self):
        res = super(asset, self).set_to_draft()
        for me_id in self :
            for line in me_id.asset_ids :
                if me_id.state != 'draft' :
                    raise Warning('Tidak bisa menghapus data yang bukan draft !')
                if line.entry_count != 0 :
                    raise Warning("Asset details sudah didepresiasi.")
                line.set_to_draft()
                line.unlink()
            # if me_id.asset_id :
            #     if all(line.state == 'draft' for line in me_id.asset_id.asset_ids):
            #         me_id.asset_id.set_to_draft()
        return res

    @api.multi
    def generate_sequence(self):
        self.ensure_one()
        if self.code :
            return False
        code = self.category_id.complete_code
        if self.asset_id :
            obj_sequence = self.env['ir.sequence']
            sequence_id = obj_sequence.sudo().search([
                ('name','=','Sequence Code'),
                ('code','=','account.asset.asset'),
                ('prefix','=','%s.'%self.category_id.complete_code),
                ('implementation','=','no_gap'),
                ('padding','=',5),
            ], limit=1)
            if not sequence_id :
                sequence_id = obj_sequence.sudo().create({
                    'name': 'Sequence Code',
                    'code': 'account.asset.asset',
                    'prefix': '%s.'%self.category_id.complete_code,
                    'implementation': 'no_gap',
                    'padding': 5,
                })
            code = sequence_id.next_by_id()
        return code

    @api.multi
    def confirm_ga(self):
        for me_id in self :
            if me_id.state != 'draft' :
                continue
            if not self.last_location_id:
                raise UserError("Please enter Asset Location")
            me_id.create_details()
            me_id.create_detail_sewa()
            to_write = {'state': 'confirm'}
            code = self.generate_sequence()
            if code :
                to_write['code'] = code
            me_id.write(to_write)

    @api.multi
    def confirm_ga_multi(self):
        group_id = self.env.ref("vit_asset.group_confirm_asset_ga")
        if self.env.user.id not in group_id.users.ids :
            raise Warning("Anda tidak termasuk grup %s"%group_id.name)
        for me_id in self :
            if me_id.state != 'draft' :
                continue
            me_id.confirm_ga()
            me_id._cr.commit()

    @api.multi
    def name_get(self):
        result = []
        for me_id in self :
            result.append((me_id.id, "%s %s"%(me_id.code, me_id.name)))
        return result

    @api.multi
    def action_close(self, addtional_dict={}):
        self.ensure_one()
        to_write = {
            'state': 'close',
        }
        if addtional_dict :
            to_write.update(addtional_dict)
        self.write(to_write)
        depre_to_remove = self.depreciation_line_ids.filtered(lambda l: not l.move_id or l.move_id.state != 'posted')
        moves_to_remove = depre_to_remove.mapped('move_id')
        if moves_to_remove :
            moves_to_remove.unlink()
        depre_to_remove.unlink()
        if self.asset_id and all(asset.state=='close' for asset in self.asset_id.asset_ids):
            self.asset_id.action_close()

    @api.model
    def compute_generated_entries(self, date, asset_type=None):
        ###tambahan
        company_domain = []
        if 'company_ids' in self._context :
            company_domain = [('company_id', 'in', self._context['company_ids'])]
        ###tambahan###

        # Entries generated : one by grouped category and one by asset from ungrouped category
        created_move_ids = []
        type_domain = []
        if asset_type:
            type_domain = [('type', '=', asset_type)]

        ungrouped_assets = self.env['account.asset.asset'].search(type_domain + company_domain + [('state', '=', 'open'), ('category_id.group_entries', '=', False), ('asset_id','!=',False)])
        created_move_ids += ungrouped_assets._compute_entries(date, group_entries=False)

        for grouped_category in self.env['account.asset.category'].search(type_domain + [('group_entries', '=', True)]):
            assets = self.env['account.asset.asset'].search([('state', '=', 'open'), ('category_id', '=', grouped_category.id)])
            created_move_ids += assets._compute_entries(date, group_entries=True)
        
        ###tambahan
        for me_id in self :
            for line in me_id.depreciation_line_ids :
                for move_line in line.move_id.line_ids :
                    move_line.account_analytic_id = me_id.account_analytic_id.id
                    if me_id.analytic_tag_ids :
                        move_line.write({'analytic_tag_ids': [(6, 0, [analytic_tag_id.id for analytic_tag_id in me_id.analytic_tag_ids])]})
        ###tambahan###
        return created_move_ids

    @api.model
    def name_search(self, name, args=None, operator='ilike', limit=100):
        args = args or []
        if name :
            recs = self.search([
                '|',
                ('name', operator, name),
                ('code', operator, name)
            ] + args, limit=limit)
        else :
            recs = self.search([] + args, limit=limit)
        return recs.name_get()

    @api.multi
    def _cek_qty(self):
        for asset in self:
            if asset.qty <=0:
                return False
            return True

    _constraints = [
        (_cek_qty, 'Quantity must be more than zero!', ['qty'])
    ]

    @api.multi
    def validate(self):
        res = super(asset, self).validate()
        for me_id in self :
            if me_id.asset_ids :
                me_id.asset_ids.validate()
        return res

    @api.multi
    def validate_multi(self):
        group_id = self.env.ref("vit_asset.group_confirm_asset_accounting")
        if self.env.user.id not in group_id.users.ids :
            raise Warning("Anda tidak termasuk grup %s"%group_id.name)
        for me_id in self :
            if me_id.state != 'confirm' :
                continue
            if me_id.asset_id and me_id.asset_id.state != 'open' :
                raise Warning("Confirm harus di parent asset.")
            me_id.validate()
            me_id._cr.commit()

    def create_details(self):
        if not self.asset_id :
            for x in range(0, self.qty):
                data = {
                    'entry_count': self.entry_count,
                    'name': self.name,
                    'code': self.code,
                    'value': self.value / self.qty,
                    'currency_id': self.currency_id.id,
                    'company_id': self.company_id.id,
                    'note': self.note,
                    'category_id': self.category_id.id,
                    'date': self.date,
                    'state': self.state,
                    'active': self.active,
                    'partner_id': self.partner_id.id,
                    'method': self.method,
                    'method_number': self.method_number,
                    'method_period': self.method_period,
                    'method_end': self.method_end,
                    'method_progress_factor': self.method_progress_factor,
                    'value_residual': self.value_residual/self.qty,
                    'method_time': self.method_time,
                    'prorata': self.prorata,
                    'salvage_value': self.salvage_value/self.qty,
                    'type': self.type,
                    'asset_id': self.id,
                    'qty': 1,
                    'invoice_id': self.invoice_id.id if self.invoice_id else False,
                    'purchase_order_id': self.purchase_order_id.id if self.purchase_order_id else False,
                    'shipping_id': self.shipping_id.id if self.shipping_id else False,
                    'date_received': self.date_received,
                    'manufacturer_id': self.manufacturer_id.id if self.manufacturer_id else False,
                    'brand': self.brand,
                    'model': self.model,
                    'color': self.color,
                    'serial_number': self.serial_number,
                    'warranty_name': self.warranty_name,
                    'warranty_description': self.warranty_description,
                    'warranty_date': self.warranty_date,
                    'warranty_service_provider_id': self.warranty_service_provider_id.id if self.warranty_service_provider_id else False ,
                    'last_location_id': self.last_location_id.id,
                    'condition': 'new',
                    'image': self.image,
                    'account_analytic_id': self.account_analytic_id.id,
                    'analytic_tag_ids': [(6, 0, [analytic_tag_id.id for analytic_tag_id in self.analytic_tag_ids])] if self.analytic_tag_ids else False,
                    'status_kepemilikan': self.status_kepemilikan,
                    'start_date': self.start_date,
                    'end_date': self.end_date,
                    'nilai_sewa': self.nilai_sewa,
                    'due_date': self.due_date,
                    'lama_sewa': self.lama_sewa,
                    'description': self.description,
                    'serial_number': self.serial_number,
                    'transmisi': self.transmisi,
                    'no_mesin': self.no_mesin,
                    'no_rangka': self.no_rangka,
                    'silinder': self.silinder,
                    'tahun_pembuatan': self.tahun_pembuatan,
                    'city': self.city,
                }
                detail = self.env['account.asset.asset'].create(data)
                detail.confirm_ga()

    @api.multi
    def compute_depreciation_board(self):
        self.ensure_one()
        result = super(asset, self).compute_depreciation_board()
        for i in self :
            if not i.prorata:
                if int(str(i.date)[8:]) >= 1 and int(str(i.date)[8:]) <= 15 :
                    # akhir bulan di bulan yg sama
                    bulan = 1
                else :
                    # maju ke akhir bulan berikutnya
                    bulan = 2
                # klien : Cut off per tanggal 15, jadi kalau nilai perolehan 1-15 itu disusutkan bulan bersangkutan, kalau tanggal 16-31 disusutkan bulan berikutnya
                for dep in i.depreciation_line_ids :
                    dt = fields.Datetime.from_string(dep.depreciation_date)
                    end_date = str(dt + relativedelta.relativedelta(months=bulan, day=1, days=-1))[:10]
                    dep.update({'depreciation_date': end_date})
        return result

    @api.multi
    def unlink(self):
        for me_id in self :
            if me_id.asset_ids :
                me_id.asset_ids.unlink()
        return super(asset, self).unlink()

class asset_location(models.Model):
    _name = 'vit.asset_location'

    asset_id = fields.Many2one(comodel_name="account.asset.asset", string="Asset", required=False, )
    location_id = fields.Many2one(comodel_name="vit.location", string="Location", required=False, )
    name = fields.Char(string="Notes", required=False, )
    date = fields.Date(string="Move Date", required=False, )

class AccountAssetDepreciationLine(models.Model):
    _inherit = 'account.asset.depreciation.line'

    @api.multi
    def create_move(self, post_move=True):
        result = super(AccountAssetDepreciationLine, self).create_move()
        move = self.env['account.move.line']
        for mv in self :
            if mv.asset_id.account_id :
                move_id = mv.move_id.id
                lines = move.search([('move_id','=',move_id),('debit','=',0)])
                if lines :
                    for line in lines :
                        line.update({'account_id' : mv.asset_id.account_id.id})
            for move_line in mv.move_id.line_ids :
                move_line.analytic_account_id = mv.asset_id.account_analytic_id.id
                if mv.asset_id.analytic_tag_ids :
                    move_line.write({'analytic_tag_ids': [(6, 0, [analytic_tag_id.id for analytic_tag_id in mv.asset_id.analytic_tag_ids])]})
        return result

class VitAssetSewa(models.Model):
    _name = "vit.asset.sewa"
    _description = "Asset Sewa"
    _rec_name = 'asset_id'

    asset_id = fields.Many2one(comodel_name="account.asset.asset", string="Asset", ondelete='cascade')
    nilai_sewa = fields.Float(string='Nominal', digits=0)
    due_date = fields.Date(string='Due Date')
    sequence = fields.Integer(string='Pembayaran ke')
