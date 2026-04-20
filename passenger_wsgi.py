import os
import site
import sys

project_home = "/home2/vapeland/vapeland"
if project_home not in sys.path:
    sys.path.insert(0, project_home)

python_version = f"{sys.version_info.major}.{sys.version_info.minor}"
virtualenv_home = os.path.join(os.path.dirname(project_home), "virtualenv", os.path.basename(project_home), python_version)
site_packages_candidates = [
    os.path.join(virtualenv_home, "lib", f"python{python_version}", "site-packages"),
    os.path.join(virtualenv_home, "lib64", f"python{python_version}", "site-packages"),
]

for site_packages in site_packages_candidates:
    if os.path.isdir(site_packages):
        site.addsitedir(site_packages)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "app.settings")

from app.wsgi import application
