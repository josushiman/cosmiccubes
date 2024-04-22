    # @classmethod
    # async def categories_spent(cls,
    #     current_month: bool = None, 
    #     since_date: str = None, 
    #     year: Enum = None, 
    #     months: IntEnum = None,
    #     specific_month: Enum = None
    #     ) -> list[CategorySpent]:
    #     if current_month:
    #         db_queryset = YnabCategories.annotate(
    #             spent=Sum('activity'),
    #             budget=Sum('budgeted')
    #         ).filter(
    #             category_group_name__in=YNAB.CAT_EXPENSE_NAMES
    #         ).group_by('category_group_name').order_by('spent').values('spent','budget',name='category_group_name')
    #     elif since_date and specific_month:
    #         db_queryset = YnabMonthDetailCategories.annotate(
    #             spent=Sum('activity'),
    #             budget=Sum('budgeted')
    #         ).filter(
    #             category_group_name__in=YNAB.CAT_EXPENSE_NAMES,
    #             month_summary_fk__month=since_date
    #         ).group_by('category_group_name').order_by('spent').values('spent','budget',name='category_group_name')    
    #     elif months:
    #         logging.debug(f"Returning category info for the months since: {since_date}.")
    #         db_queryset = YnabMonthDetailCategories.annotate(
    #             spent=Sum('activity'),
    #             budget=Sum('budgeted')
    #         ).filter(
    #             category_group_name__in=YNAB.CAT_EXPENSE_NAMES,
    #             month_summary_fk__month__gte=since_date
    #         ).group_by('category_group_name').order_by('spent').values('spent','budget',name='category_group_name')
    #     elif year:
    #         logging.debug(f"Returning category info for the year since: {year.value}.")
    #         db_queryset = YnabMonthDetailCategories.annotate(
    #             spent=Sum('activity'),
    #             budget=Sum('budgeted')
    #         ).filter(
    #             category_group_name__in=YNAB.CAT_EXPENSE_NAMES,
    #             month_summary_fk__month__year=year.value
    #         ).group_by('category_group_name').order_by('spent').values('spent','budget',name='category_group_name')            

    #     db_result = await db_queryset

    #     logging.debug(f"DB Query: {db_queryset.sql()}")
    #     logging.debug(f"DB Result: {db_result}")

    #     return db_result

#  @classmethod
#     async def transactions_by_month_for_year(cls, year: Enum = None) -> TransactionsByMonthResponse:
#         since_date = await YnabHelpers.get_date_for_transactions(year=year)
#         end_date = await YnabHelpers.get_last_date_from_since_date(since_date=since_date, year=True)
        
#         january = {
#             "month_long": "January",
#             "month_short": "J",
#             "month_year": f"{year.value}-01",
#             "total_spent": 0,
#             "total_earned": 0
#         }
#         february = {
#             "month_long": "February",
#             "month_short": "F",
#             "month_year": f"{year.value}-02",
#             "total_spent": 0,
#             "total_earned": 0
#         }
#         march = {
#             "month_long": "March",
#             "month_short": "M",
#             "month_year": f"{year.value}-03",
#             "total_spent": 0,
#             "total_earned": 0
#         }
#         april = {
#             "month_long": "April",
#             "month_short": "A",
#             "month_year": f"{year.value}-04",
#             "total_spent": 0,
#             "total_earned": 0
#         }
#         may = {
#             "month_long": "May",
#             "month_short": "M",
#             "month_year": f"{year.value}-05",
#             "total_spent": 0,
#             "total_earned": 0
#         }
#         june = {
#             "month_long": "June",
#             "month_short": "J",
#             "month_year": f"{year.value}-06",
#             "total_spent": 0,
#             "total_earned": 0
#         }
#         july = {
#             "month_long": "July",
#             "month_short": "J",
#             "month_year": f"{year.value}-07",
#             "total_spent": 0,
#             "total_earned": 0
#         }
#         august = {
#             "month_long": "August",
#             "month_short": "A",
#             "month_year": f"{year.value}-08",
#             "total_spent": 0,
#             "total_earned": 0
#         }
#         september = {
#             "month_long": "September",
#             "month_short": "S",
#             "month_year": f"{year.value}-09",
#             "total_spent": 0,
#             "total_earned": 0
#         }
#         october = {
#             "month_long": "October",
#             "month_short": "O",
#             "month_year": f"{year.value}-10",
#             "total_spent": 0,
#             "total_earned": 0
#         }
#         november = {
#             "month_long": "November",
#             "month_short": "N",
#             "month_year": f"{year.value}-11",
#             "total_spent": 0,
#             "total_earned": 0
#         }
#         december = {
#             "month_long": "December",
#             "month_short": "D",
#             "month_year": f"{year.value}-12",
#             "total_spent": 0,
#             "total_earned": 0
#         }

#         sorted_months = [january, february, march, april, may, june, july, august, september, october, november, december]

#         # From the since date, go through each month and add it to the data
#         since_date_dt = datetime.strptime(since_date, '%Y-%m-%d')

#         class TruncMonth(Function):
#             database_func = CustomFunction("TO_CHAR", ["column_name", "dt_format"])
        
#         db_queryset = YnabTransactions.annotate(
#             month_year=TruncMonth('date', 'YYYY-MM'),
#             income=Sum(RawSQL('CASE WHEN "amount" >= 0 THEN "amount" ELSE 0 END')),
#             expense=Sum(RawSQL('CASE WHEN "amount" < 0 THEN "amount" ELSE 0 END'))
#         ).filter(
#             Q(date__gte=since_date_dt),
#             Q(date__lte=end_date),
#             Q(
#                 category_fk__category_group_name__in=YNAB.CAT_EXPENSE_NAMES,
#                 payee_name='BJSS LIMITED',
#                 join_type='OR'
#             )
#         ).group_by('month_year').values('month_year','income','expense').sql()
#         logging.debug(f"SQL Query: {db_queryset}")
            
#         db_result = await YnabTransactions.annotate(
#             month_year=TruncMonth('date', 'YYYY-MM'),
#             income=Sum(RawSQL('CASE WHEN "amount" >= 0 THEN "amount" ELSE 0 END')),
#             expense=Sum(RawSQL('CASE WHEN "amount" < 0 THEN "amount" ELSE 0 END'))
#         ).filter(
#             Q(date__gte=since_date_dt),
#             Q(date__lte=end_date),
#             Q(
#                 category_fk__category_group_name__in=YNAB.CAT_EXPENSE_NAMES,
#                 payee_name='BJSS LIMITED',
#                 join_type='OR'
#             )
#         ).group_by('month_year').values('month_year','income','expense')

#         month_match = {
#             f'{year.value}-01': january,
#             f'{year.value}-02': february,
#             f'{year.value}-03': march,
#             f'{year.value}-04': april,
#             f'{year.value}-05': may,
#             f'{year.value}-06': june,
#             f'{year.value}-07': july,
#             f'{year.value}-08': august,
#             f'{year.value}-09': september,
#             f'{year.value}-10': october,
#             f'{year.value}-11': november,
#             f'{year.value}-12': december
#         }

#         for month in db_result:
#             month_match[month['month_year']]['total_spent'] = month['expense']
#             month_match[month['month_year']]['total_earned'] = month['income']

#         return TransactionsByMonthResponse(
#             since_date=since_date,
#             data=sorted_months
#         )

#     @classmethod
#     async def transactions_by_months(cls, months: IntEnum = None) -> TransactionsByMonthResponse:
#         since_date = await YnabHelpers.get_date_for_transactions(months=months)
#         now = localtime()
#         # Returns a tuple of year, month. e.g. [(2024, 1), (2023, 12), (2023, 11)]
#         months_to_get = [localtime(mktime((now.tm_year, now.tm_mon - n, 1, 0, 0, 0, 0, 0, 0)))[:2] for n in range(months.value)]
#         # Swap the results round so that the oldest month is the first index.
#         months_to_get.reverse()

#         january = {
#             "month": 1,
#             "month_long": "January",
#             "month_short": "J",
#             "total_spent": 0,
#             "total_earned": 0
#         }
#         february = {
#             "month": 2,
#             "month_long": "February",
#             "month_short": "F",
#             "total_spent": 0,
#             "total_earned": 0
#         }
#         march = {
#             "month": 3,
#             "month_long": "March",
#             "month_short": "M",
#             "total_spent": 0,
#             "total_earned": 0
#         }
#         april = {
#             "month": 4,
#             "month_long": "April",
#             "month_short": "A",
#             "total_spent": 0,
#             "total_earned": 0
#         }
#         may = {
#             "month": 5,
#             "month_long": "May",
#             "month_short": "M",
#             "total_spent": 0,
#             "total_earned": 0
#         }
#         june = {
#             "month": 6,
#             "month_long": "June",
#             "month_short": "J",
#             "total_spent": 0,
#             "total_earned": 0
#         }
#         july = {
#             "month": 7,
#             "month_long": "July",
#             "month_short": "J",
#             "total_spent": 0,
#             "total_earned": 0
#         }
#         august = {
#             "month": 8,
#             "month_long": "August",
#             "month_short": "A",
#             "total_spent": 0,
#             "total_earned": 0
#         }
#         september = {
#             "month": 9,
#             "month_long": "September",
#             "month_short": "S",
#             "total_spent": 0,
#             "total_earned": 0
#         }
#         october = {
#             "month": 10,
#             "month_long": "October",
#             "month_short": "O",
#             "total_spent": 0,
#             "total_earned": 0
#         }
#         november = {
#             "month": 11,
#             "month_long": "November",
#             "month_short": "N",
#             "total_spent": 0,
#             "total_earned": 0
#         }
#         december = {
#             "month": 12,
#             "month_long": "December",
#             "month_short": "D",
#             "total_spent": 0,
#             "total_earned": 0
#         }

#         month_list = []
#         month_match = {
#             '1': january,
#             '2': february,
#             '3': march,
#             '4': april,
#             '5': may,
#             '6': june,
#             '7': july,
#             '8': august,
#             '9': september,
#             '10': october,
#             '11': november,
#             '12': december
#         }

#         # add the months in order of oldest, the latest to the result_json
#         for index, (year, month) in enumerate(months_to_get):
#             add_month = month_match[str(month)]
#             add_month['year'] = str(year)
#             if month < 10:
#                 add_month['month_year'] = f"{year}-0{month}"
#             else:
#                 add_month['month_year'] = f"{year}-{month}"
#             month_list.insert(index, add_month)

#         # From the since date, go through each month and add it to the data
#         since_date_dt = datetime.strptime(since_date, '%Y-%m-%d')
#         end_date = datetime.now()

#         class TruncMonth(Function):
#             database_func = CustomFunction("TO_CHAR", ["column_name", "dt_format"])

#         db_queryset = YnabTransactions.annotate(
#             month_year=TruncMonth('date', 'YYYY-MM'),
#             income=Sum(RawSQL('CASE WHEN "amount" >= 0 THEN "amount" ELSE 0 END')),
#             expense=Sum(RawSQL('CASE WHEN "amount" < 0 THEN "amount" ELSE 0 END'))
#         ).filter(
#             Q(date__gte=since_date_dt),
#             Q(date__lte=end_date),
#             Q(
#                 category_fk__category_group_name__in=YNAB.CAT_EXPENSE_NAMES,
#                 payee_name='BJSS LIMITED',
#                 join_type='OR'
#             )
#         ).group_by('month_year').values('month_year','income','expense').sql()
#         logging.debug(f"SQL Query: {db_queryset}")

#         db_result = await YnabTransactions.annotate(
#             month_year=TruncMonth('date', 'YYYY-MM'),
#             income=Sum(RawSQL('CASE WHEN "amount" >= 0 THEN "amount" ELSE 0 END')),
#             expense=Sum(RawSQL('CASE WHEN "amount" < 0 THEN "amount" ELSE 0 END'))
#         ).filter(
#             Q(date__gte=since_date_dt),
#             Q(date__lte=end_date),
#             Q(
#                 category_fk__category_group_name__in=YNAB.CAT_EXPENSE_NAMES,
#                 payee_name='BJSS LIMITED',
#                 join_type='OR'
#             )
#         ).group_by('month_year').values('month_year','income','expense')

#         for month in db_result:
#             for filtered_list in month_list:
#                 if filtered_list['month_year'] == month['month_year']:
#                     filtered_list['total_spent'] = month['expense']
#                     filtered_list['total_earned'] = month['income']

#         return TransactionsByMonthResponse(
#             since_date=since_date,
#             data=month_list
#         )
