# conftest.py
import importlib.util
import sys
import pathlib
import types

repo_root = pathlib.Path(__file__).resolve().parents[2]
pkg_root = repo_root / "bumiworker"

# Ensure repository root is on sys.path (so top-level 'bumiworker' package is found)
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

# Also add the package directory explicitly to avoid environment-specific path issues
if str(pkg_root) not in sys.path:
    sys.path.insert(0, str(pkg_root))

# Ensure bumiworker package can be imported and create alias for bumiworker.bumiworker.
if "bumiworker" not in sys.modules:
    spec = importlib.util.spec_from_file_location("bumiworker", pkg_root / "__init__.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["bumiworker"] = module
    spec.loader.exec_module(module)  # type: ignore[attr-defined]

sys.modules.setdefault("bumiworker.bumiworker", sys.modules["bumiworker"])

# Provide lightweight stubs for external libs only needed at import time.
# This avoids requiring full environment setup just to collect tests.
if "requests" not in sys.modules:
    sys.modules["requests"] = types.SimpleNamespace()

#
# kombu stubs: Connection, Exchange, and pools.producers
#
if "kombu" not in sys.modules:
    kombu_mod = types.ModuleType("kombu")

    class _DummyConnection:  # noqa: D401
        def __init__(self, *args, **kwargs):
            pass

    class _DummyExchange:
        def __init__(self, *args, **kwargs):
            pass

    kombu_mod.Connection = _DummyConnection
    kombu_mod.Exchange = _DummyExchange
    sys.modules["kombu"] = kombu_mod

if "kombu.pools" not in sys.modules:
    pools_mod = types.ModuleType("kombu.pools")

    class _DummyProducers:
        def __enter__(self): return self
        def __exit__(self, exc_type, exc, tb): return False
        def acquire(self, *args, **kwargs):
            class _P:
                def __enter__(self): return types.SimpleNamespace(ensure=lambda *a, **k: None)
                def __exit__(self, exc_type, exc, tb): return False
            return _P()

    pools_mod.producers = _DummyProducers()
    sys.modules["kombu.pools"] = pools_mod

#
# clickhouse_connect stub
#
if "clickhouse_connect" not in sys.modules:
    sys.modules["clickhouse_connect"] = types.ModuleType("clickhouse_connect")

#
# pymongo stubs
#
if "pymongo" not in sys.modules:
    pymongo_mod = types.ModuleType("pymongo")

    class _DummyMongoClient:
        def __init__(self, *args, **kwargs):
            pass

    class _DummyUpdateOne:
        def __init__(self, *args, **kwargs):
            pass

    pymongo_mod.MongoClient = _DummyMongoClient
    pymongo_mod.UpdateOne = _DummyUpdateOne
    sys.modules["pymongo"] = pymongo_mod

#
# optscale_client stubs
#
pkg = "optscale_client.rest_api_client"
if "optscale_client" not in sys.modules:
    sys.modules["optscale_client"] = types.ModuleType("optscale_client")
if pkg not in sys.modules:
    sys.modules[pkg] = types.ModuleType(pkg)
if pkg + ".client" not in sys.modules:
    client_mod = types.ModuleType(pkg + ".client")
    class _DummyClient:
        def __init__(self, *args, **kwargs):
            pass
    client_mod.Client = _DummyClient
    sys.modules[pkg + ".client"] = client_mod
if pkg + ".client_v2" not in sys.modules:
    client_v2_mod = types.ModuleType(pkg + ".client_v2")
    class _DummyClientV2:
        def __init__(self, *args, **kwargs):
            pass
    client_v2_mod.Client = _DummyClientV2
    sys.modules[pkg + ".client_v2"] = client_v2_mod

#
# tools subpackages stubs
#
if "tools" not in sys.modules:
    tools_mod = types.ModuleType("tools")
    sys.modules["tools"] = tools_mod

if "tools.optscale_time" not in sys.modules:
    time_mod = types.ModuleType("tools.optscale_time")
    from time import time as _time
    from datetime import datetime, timezone
    
    def utcnow_timestamp(): 
        return int(_time())
    
    def utcnow(): 
        return datetime.now(timezone.utc)
    
    def utcfromtimestamp(ts): 
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    
    def startday(ts): 
        if isinstance(ts, datetime):
            return datetime(ts.year, ts.month, ts.day, tzinfo=ts.tzinfo)
        return ts
    
    time_mod.utcnow_timestamp = utcnow_timestamp
    time_mod.utcnow = utcnow
    time_mod.utcfromtimestamp = utcfromtimestamp
    time_mod.startday = startday
    sys.modules["tools.optscale_time"] = time_mod
    # Make it accessible as tools.optscale_time attribute
    sys.modules["tools"].optscale_time = time_mod

if "tools.optscale_data" not in sys.modules:
    data_mod = types.ModuleType("tools.optscale_data")
    sys.modules["tools.optscale_data"] = data_mod
    # Make it accessible as tools.optscale_data attribute
    sys.modules["tools"].optscale_data = data_mod

if "tools.optscale_data.clickhouse" not in sys.modules:
    ch_mod = types.ModuleType("tools.optscale_data.clickhouse")
    class ExternalDataConverter:
        def __init__(self, *args, **kwargs):
            pass
    ch_mod.ExternalDataConverter = ExternalDataConverter
    sys.modules["tools.optscale_data.clickhouse"] = ch_mod
    # Make it accessible as tools.optscale_data.clickhouse attribute
    sys.modules["tools.optscale_data"].clickhouse = ch_mod
