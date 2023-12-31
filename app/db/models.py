from tortoise import fields, models

class AccountTypes(models.Model):
    id = fields.UUIDField(pk=True)
    name = fields.CharField(max_length=150, unique=True)

class Accounts(models.Model):
    id = fields.UUIDField(pk=True)
    name = fields.CharField(max_length=150, unique=True)
    type = fields.ForeignKeyField('models.AccountTypes', related_name='accounts')

class CompanyCategories(models.Model):
    id = fields.UUIDField(pk=True)
    name = fields.CharField(max_length=150, unique=True)

class Companies(models.Model):
    id = fields.UUIDField(pk=True)
    name = fields.CharField(max_length=150, unique=True)
    category = fields.ForeignKeyField('models.CompanyCategories', related_name='companies')

class BalanceTransfers(models.Model):
    id = fields.UUIDField(pk=True)
    name = fields.CharField(max_length=150)
    account = fields.ForeignKeyField('models.Accounts', related_name='balancetransfers')
    amount = fields.FloatField(default=0.0)
    end_date = fields.DateField(null=True)
    interest_rate = fields.FloatField(default=0.0, null=True)
    paid_instalments = fields.IntField(default=0, null=True)
    paid_date = fields.IntField(max=31, min=1, default=1)
    period = fields.CharField(max_length=150, null=True)
    start_date = fields.DateField()
    total_instalments = fields.IntField()

    def total(self) -> float:
        return self.amount * self.total_instalments

    class PydanticMeta:
        computed = ["total"]
        unique_together=("name", "account")

class Budgets(models.Model):
    id = fields.UUIDField(pk=True)
    name = fields.CharField(max_length=150)
    account = fields.ForeignKeyField('models.Accounts', related_name='budgets')
    transactions = fields.IntField(default=0, null=True)
    current_amount = fields.FloatField(default=0.0, null=True)
    target_amount = fields.FloatField(default=0.0)
    start_date = fields.DateField(null=True)
    end_date = fields.DateField(null=True)

    def available_amount(self) -> float:
        return self.target_amount - self.current_amount

    class PydanticMeta:
        computed = ["available_amount"]
        unique_together=("name", "account")

class DirectDebits(models.Model):
    id = fields.UUIDField(pk=True)
    name = fields.CharField(max_length=150)
    paid_date = fields.IntField(max=31, min=1, default=1)
    start_date = fields.DateField(null=True)
    end_date = fields.DateField(null=True)
    account = fields.ForeignKeyField('models.Accounts', related_name='directdebits')
    company = fields.ForeignKeyField('models.Companies', related_name='directdebits')
    amount = fields.FloatField(default=0.0)
    period = fields.CharField(max_length=150, null=True)
    notes = fields.CharField(max_length=250, null=True)
    
    def annual_cost(self) -> float:
        if self.period == 'monthly': return self.amount * 12
        elif self.period == 'weekly': return self.amount * 52
        return self.amount

    class PydanticMeta:
        computed = ["annual_cost"]
        unique_together=("name", "account")

class Incomes(models.Model):
    id = fields.UUIDField(pk=True)
    name = fields.CharField(max_length=150)
    account = fields.ForeignKeyField('models.Accounts', related_name='incomes')
    company = fields.ForeignKeyField('models.Companies', related_name='incomes')
    amount = fields.FloatField(default=0.0)
    period = fields.CharField(max_length=150, null=True)
    paid_date = fields.IntField(max=31, min=1, default=1)
    notes = fields.CharField(max_length=250)

    def pre_tax(self) -> float:
        return self.amount / 12
    
    def post_tax(self) -> float:
        return self.amount / 12

    class PydanticMeta:
        computed = ["pre_tax", "post_tax"]
        unique_together=("name", "company")

class Mortgages(models.Model):
    id = fields.UUIDField(pk=True)
    name = fields.CharField(max_length=150, unique=True)
    interest_rate = fields.FloatField(default=0.0)
    paid_date = fields.IntField(max=31, min=1, default=1)
    start_date = fields.DateField(null=True)
    end_date = fields.DateField(null=True)
    account = fields.ForeignKeyField('models.Accounts', related_name='mortgages')
    company = fields.ForeignKeyField('models.Companies', related_name='mortgages')
    amount = fields.FloatField(default=0.0)
    period = fields.CharField(max_length=150, null=True)

    def annual_cost(self) -> float:
        if self.period == 'monthly': return self.amount * 12
        elif self.period == 'weekly': return self.amount * 52
        return self.amount

    class PydanticMeta:
        computed = ["annual_cost"]

class Projects(models.Model):
    id = fields.UUIDField(pk=True)
    name = fields.CharField(max_length=150, unique=True)

class ProjectItemCategories(models.Model):
    id = fields.UUIDField(pk=True)
    name = fields.CharField(max_length=150, unique=True)

class ProjectItems(models.Model):
    id = fields.UUIDField(pk=True)
    name = fields.CharField(max_length=150)
    company = fields.ForeignKeyField('models.Companies', related_name='projectitems')
    project_name = fields.ForeignKeyField('models.Projects', related_name='projectitems')
    category = fields.ForeignKeyField('models.ProjectItemCategories', related_name='projectitems')
    quantity = fields.IntField(default=1, null=True)
    amount = fields.FloatField(default=0.0)
    link = fields.CharField(max_length=250, null=True)

    def total(self) -> float:
        return self.amount * self.quantity

    class PydanticMeta:
        computed = ["total"]
        unique_together=("name", "company", "category")

class YnabServerKnowledge(models.Model):
    id = fields.UUIDField(pk=True)
    budget_id = fields.UUIDField()
    route = fields.CharField(max_length=250, unique=True)
    server_knowledge = fields.IntField()

    class PydanticMeta:
        unique_together=("budget_id", "route")

class YnabTransactions(models.Model):
    id = fields.UUIDField(pk=True)
    date = fields.DateField()
    amount = fields.FloatField(default=0.0)
    memo = fields.CharField(max_length=150, null=True)
    cleared = fields.CharField(max_length=150)
    approved = fields.BooleanField(null=True)
    flag_color = fields.CharField(max_length=150, null=True)
    account_id = fields.UUIDField()
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
