from tortoise import fields
from tortoise.models import Model
from datetime import datetime, timezone
import logging

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

class LoansAndRenewalsPeriods(Model):
    id = fields.UUIDField(pk=True)
    name = fields.CharField(max_length=150) 

class LoansAndRenewalsTypes(Model):
    id = fields.UUIDField(pk=True)
    name = fields.CharField(max_length=150) 

class LoansAndRenewals(Model):
    id = fields.UUIDField(pk=True)
    name = fields.CharField(max_length=150)
    start_date = fields.DatetimeField()
    end_date = fields.DatetimeField(null=True)
    payment_date = fields.IntField(null=True)
    payment_amount = fields.FloatField(default=0.0, null=True)
    starting_balance = fields.FloatField(default=0.0, null=True)
    notes = fields.CharField(max_length=255, null=True)
    period = fields.ForeignKeyField('models.LoansAndRenewalsPeriods', related_name=False, null=True)
    type = fields.ForeignKeyField('models.LoansAndRenewalsTypes', related_name='type', null=True)
    account = fields.ForeignKeyField('models.YnabAccounts', related_name='account', null=True)
    category = fields.ForeignKeyField('models.YnabCategories', related_name='category', null=True)

    def period_name(self) -> str:
        return self.period if self.period else None

    def remaining_balance(self) -> float:
        if self.starting_balance is None: return None

        # Take todays date as the end date to calculate what the remaining balance will be.
        end_date = datetime.now(timezone.utc)
        
        # Calculate the number of occurrences // 'yearly', 'weekly', 'monthly'
        if self.period_name == "monthly":
            occurrences = (end_date.year - self.start_date.year) * 12 + (end_date.month - self.start_date.month)
        else:
            occurrences = 1
        logging.debug(f"Number of occurences for {self.name}: {occurrences}")
        
        # If the number of occurences is 0, check if todays date is past the payment_date.
        # If it is, increase the occurences by 1.
        # This accounts for when you are in the same month as the start_date.
        if self.period_name == "monthly" and occurrences == 0:
            logging.debug("Occurence is set to 0, checking if todays date has passed the initial payment.")
            occurrences = 1 if self.payment_date <= end_date.day else 0

        remaining_balance = self.starting_balance - (self.payment_amount * occurrences)
        
        if remaining_balance <= 0: return None
        return remaining_balance
    
    def status(self) -> str:
        try:
            return "Outstanding" if self.remaining_balance > 0 else "Paid"
        except TypeError:
            return "Ongoing"

    class PydanticMeta:
        computed = ["period_name", "remaining_balance", "status"]
        unique_together=("end_date", "start_date", "name")

class Savings(Model):
    id = fields.UUIDField(pk=True)
    date = fields.DatetimeField()
    name = fields.CharField(max_length=150)
    amount = fields.FloatField(default=0.0, null=True)
    target = fields.FloatField(default=0.0)

    class PydanticMeta:
        unique_together=("date", "name")
