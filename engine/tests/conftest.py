import os

# The API tests in test_api.py are written against the six contract fixtures. Force fixture mode before the app
# is imported so they do not depend on whether data/warehouse exists on the machine running them.
os.environ.setdefault("ENGINE_DATA_MODE", "fixtures")
