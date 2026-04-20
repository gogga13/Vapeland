import os
import sys

project_home = "/home2/vapeland/vapeland"
if project_home not in sys.path:
    sys.path.insert(0, project_home)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "app.settings")

from app.wsgi import application