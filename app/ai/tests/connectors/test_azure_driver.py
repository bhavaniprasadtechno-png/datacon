from app.connectors.drivers import azure_driver


def test_test_rejects_missing_required_fields_without_touching_sdk():
    result = azure_driver.test({}, {})

    assert result.ok is False
    assert "required" in result.message.lower()


def test_sync_rejects_missing_required_fields_without_touching_sdk():
    result = azure_driver.sync({}, {})

    assert result.ok is False
    assert result.datasets == []
