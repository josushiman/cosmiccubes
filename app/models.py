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
    name = fields.CharField(max_length=150, unique=True)
    account = fields.ForeignKeyField('models.Accounts', related_name='balancetransfers')
    interest_rate = fields.FloatField()
    total_instalments = fields.IntField()
    paid_instalments = fields.IntField(default=0)
    date_taken = fields.DateField()
    start_date = fields.DateField()
    end_date = fields.DateField()
    amount = fields.FloatField()
    period = fields.CharField(max_length=150)

    def total(self) -> float:
        return self.amount * self.total_instalments

    class PydanticMeta:
        computed = ["total"]

class Budgets(models.Model):
    id = fields.UUIDField(pk=True)
    name = fields.CharField(max_length=150, unique=True)
    account = fields.ForeignKeyField('models.Accounts', related_name='budgets')
    transactions = fields.IntField(default=0)
    current_amount = fields.FloatField(default=0.0)
    target_amount = fields.FloatField()
    start_date = fields.DateField()
    end_date = fields.DateField()

    def available_amount(self) -> float:
        return self.target_amount - self.current_amount

    class PydanticMeta:
        computed = ["available_amount"]

class DirectDebits(models.Model):
    id = fields.UUIDField(pk=True)
    name = fields.CharField(max_length=150, unique=True)
    date_taken = fields.DateField()
    renewal_date = fields.DateField()
    start_date = fields.DateField()
    end_date = fields.DateField()
    account = fields.ForeignKeyField('models.Accounts', related_name='directdebits')
    company = fields.ForeignKeyField('models.Companies', related_name='directdebits')
    amount = fields.FloatField()
    notes = fields.CharField(max_length=250)

class Mortgages(models.Model):
    id = fields.UUIDField(pk=True)
    name = fields.CharField(max_length=150, unique=True)
    interest_rate = fields.FloatField()
    date_taken = fields.DateField()
    start_date = fields.DateField()
    end_date = fields.DateField()
    account = fields.ForeignKeyField('models.Accounts', related_name='mortgages')
    company = fields.ForeignKeyField('models.Companies', related_name='mortgages')
    amount = fields.FloatField()
    period = fields.CharField(max_length=150)

class Projects(models.Model):
    id = fields.UUIDField(pk=True)
    name = fields.CharField(max_length=150, unique=True)

class ProjectItemCategories(models.Model):
    id = fields.UUIDField(pk=True)
    name = fields.CharField(max_length=150, unique=True)

class ProjectItems(models.Model):
    id = fields.UUIDField(pk=True)
    name = fields.CharField(max_length=150, unique=True)
    company = fields.ForeignKeyField('models.Companies', related_name='projectitems')
    project_name = fields.ForeignKeyField('models.Projects', related_name='projectitems')
    category = fields.ForeignKeyField('models.ProjectItemCategories', related_name='projectitems')
    quantity = fields.IntField(default=1)
    amount = fields.FloatField()
    link = fields.CharField(max_length=250)

    def total(self) -> float:
        return self.amount * self.quantity

    class PydanticMeta:
        computed = ["total"]
