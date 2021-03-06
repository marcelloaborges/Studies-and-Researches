from flask import Blueprint

from ml.regression.api import RegressionApi

regression_app = Blueprint('regression_app', __name__)

#VIEWS
regression_views = RegressionApi.as_view('regression')

#ROUTES
regression_app.add_url_rule('/ml/regression', view_func=regression_views, methods=['GET',])