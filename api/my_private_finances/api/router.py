from fastapi import APIRouter

from my_private_finances.api.routes import reports
from my_private_finances.api.routes.accounts import router as accounts_router
from my_private_finances.api.routes.annual import router as annual_router
from my_private_finances.api.routes.budgets import router as budgets_router
from my_private_finances.api.routes.categories import router as categories_router
from my_private_finances.api.routes.categorization_rules import (
    router as categorization_rules_router,
)
from my_private_finances.api.routes.csv_profiles import router as csv_profiles_router
from my_private_finances.api.routes.data_management import (
    router as data_management_router,
)
from my_private_finances.api.routes.export import router as export_router
from my_private_finances.api.routes.health import router as health_router
from my_private_finances.api.routes.imports import router as imports_router
from my_private_finances.api.routes.ml import router as ml_router
from my_private_finances.api.routes.net_worth import router as net_worth_router
from my_private_finances.api.routes.recurring_patterns import (
    router as recurring_patterns_router,
)
from my_private_finances.api.routes.transactions import router as transactions_router
from my_private_finances.api.routes.transfers import router as transfers_router
from my_private_finances.api.routes.trends import router as trends_router
from my_private_finances.api.routes.watch_folder import router as watch_folder_router

api_router = APIRouter()
api_router.include_router(accounts_router)
api_router.include_router(budgets_router)
api_router.include_router(categories_router)
api_router.include_router(categorization_rules_router)
api_router.include_router(transactions_router)
api_router.include_router(recurring_patterns_router)
api_router.include_router(reports.router)
api_router.include_router(imports_router)
api_router.include_router(transfers_router)
api_router.include_router(net_worth_router)
api_router.include_router(trends_router)
api_router.include_router(annual_router)
api_router.include_router(csv_profiles_router)
api_router.include_router(export_router)
api_router.include_router(data_management_router)
api_router.include_router(ml_router)
api_router.include_router(watch_folder_router)
api_router.include_router(health_router)
