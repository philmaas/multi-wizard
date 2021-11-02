
from views import index

import os
PROJECT_ROOT = os.path.abspath(os.curdir)

def setup_routes(app):
	app.router.add_get('/', index)

def setup_static_routes(app):
	app.router.add_static('/static/', path=PROJECT_ROOT + '/static', name='static')
