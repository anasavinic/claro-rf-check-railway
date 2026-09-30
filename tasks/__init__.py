from invoke import Collection

from . import cache, database, django, docker, lint, test

namespace = Collection(docker, django, database, cache, lint, test)
# Keep the historical `inv db.*` names alongside `inv database.*`.
namespace.add_collection(database, name="db")
