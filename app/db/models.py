from tortoise import fields
from tortoise.models import Model

# class BalanceTransfers(models.Model):
#     id = fields.UUIDField(pk=True)
#     # TODO Link this to a YNAB category to be able to see the payments
#     name = fields.CharField(max_length=150)
#     account = fields.ForeignKeyField('models.Accounts', related_name='balancetransfers') # TODO link to Ynab account
#     amount = fields.FloatField(default=0.0)
#     end_date = fields.DateField(null=True)
#     interest_rate = fields.FloatField(default=0.0, null=True)
#     paid_instalments = fields.IntField(default=0, null=True)
#     paid_date = fields.IntField(max=31, min=1, default=1)
#     period = fields.CharField(max_length=150, null=True)
#     start_date = fields.DateField()
#     total_instalments = fields.IntField()

#     def total(self) -> float:
#         return self.amount * self.total_instalments

#     class PydanticMeta:
#         computed = ["total"]
#         unique_together=("name", "account")

# class DirectDebits(models.Model):
#     id = fields.UUIDField(pk=True)
#     name = fields.CharField(max_length=150)
#     paid_date = fields.IntField(max=31, min=1, default=1)
#     start_date = fields.DateField(null=True)
#     end_date = fields.DateField(null=True)
#     account = fields.ForeignKeyField('models.Accounts', related_name='directdebits') # TODO link to Ynab account
#     company = fields.ForeignKeyField('models.Companies', related_name='directdebits') # TODO link to Ynab payee
#     amount = fields.FloatField(default=0.0)
#     period = fields.CharField(max_length=150, null=True)
#     notes = fields.CharField(max_length=250, null=True)
    
#     def annual_cost(self) -> float:
#         if self.period == 'monthly': return self.amount * 12
#         elif self.period == 'weekly': return self.amount * 52
#         return self.amount

#     class PydanticMeta:
#         computed = ["annual_cost"]
#         unique_together=("name", "account")

# class Incomes(models.Model):
#     id = fields.UUIDField(pk=True)
#     # TODO Link this to a YNAB category to be able to see the payments
#     name = fields.CharField(max_length=150)
#     account = fields.ForeignKeyField('models.Accounts', related_name='incomes') # TODO link to Ynab account
#     company = fields.ForeignKeyField('models.Companies', related_name='incomes') # TODO link to Ynab payee
#     amount = fields.FloatField(default=0.0)
#     period = fields.CharField(max_length=150, null=True)
#     paid_date = fields.IntField(max=31, min=1, default=1)
#     notes = fields.CharField(max_length=250)

#     def pre_tax(self) -> float:
#         return self.amount / 12
    
#     def post_tax(self) -> float:
#         return self.amount / 12

#     class PydanticMeta:
#         computed = ["pre_tax", "post_tax"]
#         unique_together=("name", "company")

# class Mortgages(models.Model):
#     id = fields.UUIDField(pk=True)
#     # TODO Link this to a YNAB category to be able to see the payments
#     name = fields.CharField(max_length=150, unique=True)
#     interest_rate = fields.FloatField(default=0.0)
#     paid_date = fields.IntField(max=31, min=1, default=1)
#     start_date = fields.DateField(null=True)
#     end_date = fields.DateField(null=True)
#     account = fields.ForeignKeyField('models.Accounts', related_name='mortgages') # TODO link to Ynab account
#     company = fields.ForeignKeyField('models.Companies', related_name='mortgages') # TODO link to Ynab payee
#     amount = fields.FloatField(default=0.0)
#     period = fields.CharField(max_length=150, null=True)

#     def annual_cost(self) -> float:
#         if self.period == 'monthly': return self.amount * 12
#         elif self.period == 'weekly': return self.amount * 52
#         return self.amount

#     class PydanticMeta:
#         computed = ["annual_cost"]

# class Projects(models.Model):
#     id = fields.UUIDField(pk=True)
#     name = fields.CharField(max_length=150, unique=True)

# class ProjectItemCategories(models.Model):
#     id = fields.UUIDField(pk=True)
#     name = fields.CharField(max_length=150, unique=True)

# class ProjectItems(models.Model):
#     id = fields.UUIDField(pk=True)
#     # TODO link paid items from Ynab to this. Will need to be via transactions.
#     name = fields.CharField(max_length=150)
#     company = fields.ForeignKeyField('models.Companies', related_name='projectitems')
#     project_name = fields.ForeignKeyField('models.Projects', related_name='projectitems')
#     category = fields.ForeignKeyField('models.ProjectItemCategories', related_name='projectitems')
#     quantity = fields.IntField(default=1, null=True)
#     amount = fields.FloatField(default=0.0)
#     link = fields.CharField(max_length=250, null=True)

#     def total(self) -> float:
#         return self.amount * self.quantity

#     class PydanticMeta:
#         computed = ["total"]
#         unique_together=("name", "company", "category")

class YnabServerKnowledge(Model):
    id = fields.UUIDField(pk=True)
    budget_id = fields.UUIDField()
    route = fields.CharField(max_length=250, unique=True)
    server_knowledge = fields.IntField()
    last_updated = fields.DatetimeField(auto_now=True)

    class PydanticMeta:
        unique_together=("budget_id", "route")

class YnabAccounts(Model):
    id = fields.UUIDField(pk=True)
    name = fields.CharField(max_length=150, unique=True)
    type = fields.CharField(max_length=150, null=True)
    on_budget = fields.BooleanField(null=True)
    closed = fields.BooleanField(null=True)
    note = fields.CharField(max_length=150, null=True)
    balance = fields.IntField(default=0, null=True)
    cleared_balance = fields.IntField(default=0, null=True)
    uncleared_balance = fields.IntField(default=0, null=True)
    transfer_payee_id = fields.UUIDField(null=True)
    direct_import_linked = fields.BooleanField(null=True)
    direct_import_in_error = fields.BooleanField(null=True)
    last_reconciled_at = fields.DatetimeField(null=True)
    debt_original_balance = fields.IntField(null=True)
    debt_interest_rates = fields.JSONField(null=True)
    debt_minimum_payments = fields.JSONField(null=True)
    debt_escrow_amounts = fields.JSONField(null=True)
    deleted = fields.BooleanField(null=True)

class YnabCategories(Model):
    id = fields.UUIDField(pk=True)
    category_group_id = fields.UUIDField(null=True)
    category_group_name = fields.CharField(max_length=150, null=True)
    name = fields.CharField(max_length=150, null=True)
    hidden = fields.BooleanField(null=True)
    original_category_group_id = fields.UUIDField(null=True)
    note = fields.CharField(max_length=150, null=True)
    budgeted = fields.IntField(default=0, null=True)
    activity = fields.IntField(default=0, null=True)
    balance = fields.IntField(default=0, null=True)
    goal_type = fields.CharField(max_length=150, null=True)
    goal_day = fields.IntField(default=0, null=True)
    goal_cadence = fields.IntField(default=0, null=True)
    goal_cadence_frequency = fields.IntField(default=0, null=True)
    goal_creation_month = fields.DateField(null=True)
    goal_target = fields.IntField(default=0, null=True)
    goal_target_month = fields.DateField(null=True)
    goal_percentage_complete = fields.IntField(default=0, null=True)
    goal_months_to_budget = fields.IntField(default=0, null=True)
    goal_under_funded = fields.IntField(default=0, null=True)
    goal_overall_funded = fields.IntField(default=0, null=True)
    goal_overall_left = fields.IntField(default=0, null=True)
    deleted = fields.BooleanField(null=True)

    class PydanticMeta:
        unique_together=("category_group_name", "name")

class YnabMonthSummaries(Model):
    id = fields.UUIDField(pk=True)
    month = fields.DatetimeField(null=True, unique=True)
    note = fields.CharField(max_length=150, null=True)
    income = fields.IntField(default=0, null=True)
    budgeted = fields.IntField(default=0, null=True)
    activity = fields.IntField(default=0, null=True)
    to_be_budgeted = fields.IntField(default=0, null=True)
    age_of_money = fields.IntField(default=0, null=True)
    deleted = fields.BooleanField(null=True)

    class PydanticMeta:
        unique_together=("month", "deleted")

class YnabMonthDetailCategories(Model):
    id = fields.UUIDField(pk=True)
    category_group_id = fields.UUIDField(null=True)
    category_group_name = fields.CharField(max_length=150, null=True)
    name = fields.CharField(max_length=150, null=True)
    hidden = fields.BooleanField(null=True)
    original_category_group_id = fields.UUIDField(null=True)
    note = fields.CharField(max_length=150, null=True)
    budgeted = fields.IntField(default=0, null=True)
    activity = fields.IntField(default=0, null=True)
    balance = fields.IntField(default=0, null=True)
    goal_type = fields.CharField(max_length=150, null=True)
    goal_day = fields.IntField(default=0, null=True)
    goal_cadence = fields.IntField(default=0, null=True)
    goal_cadence_frequency = fields.IntField(default=0, null=True)
    goal_creation_month = fields.DateField(null=True)
    goal_target = fields.IntField(default=0, null=True)
    goal_target_month = fields.DateField(null=True)
    goal_percentage_complete = fields.IntField(default=0, null=True)
    goal_months_to_budget = fields.IntField(default=0, null=True)
    goal_under_funded = fields.IntField(default=0, null=True)
    goal_overall_funded = fields.IntField(default=0, null=True)
    goal_overall_left = fields.IntField(default=0, null=True)
    deleted = fields.BooleanField(null=True)
    month_summary_fk = fields.ForeignKeyField('models.YnabMonthSummaries', related_name='summaries', null=True)

    class PydanticMeta:
        unique_together=("month_summary_fk_id", "category_group_name", "name")

class YnabPayees(Model):
    id = fields.UUIDField(pk=True)
    name = fields.CharField(max_length=150, null=True)
    transfer_account_id = fields.UUIDField(null=True)
    deleted = fields.BooleanField(null=True)

    class PydanticMeta:
        unique_together=("name", "deleted")

class YnabTransactions(Model):
    id = fields.UUIDField(pk=True)
    date = fields.DatetimeField()
    amount = fields.FloatField(default=0.0)
    memo = fields.CharField(max_length=150, null=True)
    cleared = fields.CharField(max_length=150)
    approved = fields.BooleanField(null=True)
    flag_color = fields.CharField(max_length=150, null=True)
    flag_name = fields.CharField(max_length=150, null=True)
    account_id = fields.UUIDField(null=True)
    account_name = fields.CharField(max_length=150)
    payee_id = fields.UUIDField(null=True)
    payee_name = fields.CharField(max_length=150, null=True)
    category_id = fields.UUIDField(null=True)
    category_name = fields.CharField(max_length=150, null=True)
    transfer_account_id = fields.UUIDField(null=True)
    transfer_transaction_id = fields.UUIDField(null=True)
    matched_transaction_id = fields.UUIDField(null=True)
    import_id = fields.CharField(max_length=150, null=True)
    import_payee_name = fields.CharField(max_length=150, null=True)
    import_payee_name_original = fields.CharField(max_length=150, null=True)
    debt_transaction_type = fields.CharField(max_length=150, null=True)
    deleted = fields.BooleanField(null=True)
    category_fk = fields.ForeignKeyField('models.YnabCategories', related_name='transactions', null=True)

    class PydanticMeta:
        unique_together=("date", "amount", "account_id", "payee_id", "category_id")

class Budgets(Model):
    id = fields.UUIDField(pk=True)
    category = fields.ForeignKeyField('models.YnabCategories', related_name='budget')
    amount = fields.FloatField(default=0.0)

class Savings(Model):
    id = fields.UUIDField(pk=True)
    date = fields.DatetimeField()
    name = fields.CharField(max_length=150)
    amount = fields.FloatField(default=0.0, null=True)
    target = fields.FloatField(default=0.0)

    class PydanticMeta:
        unique_together=("date", "name")