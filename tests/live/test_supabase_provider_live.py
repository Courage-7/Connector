from __future__ import annotations

import pytest

from connector_service.tools.live_supabase import (
    LiveConfig,
    load_live_environment,
    run_live_integration,
)


@pytest.mark.live
def test_real_supabase_service_path() -> None:
    load_live_environment()

    result = run_live_integration(LiveConfig.from_environment())

    assert result["status"] == "ok"
    assert "real_data_api_read" in result["checks"]
