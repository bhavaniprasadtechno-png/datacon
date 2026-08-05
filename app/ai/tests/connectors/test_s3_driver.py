from app.connectors.drivers import s3_driver


def test_test_rejects_missing_required_fields_without_touching_boto3():
    result = s3_driver.test({}, {})

    assert result.ok is False
    assert "required" in result.message.lower()


def test_sync_rejects_missing_required_fields_without_touching_boto3():
    result = s3_driver.sync({}, {})

    assert result.ok is False
    assert result.datasets == []
