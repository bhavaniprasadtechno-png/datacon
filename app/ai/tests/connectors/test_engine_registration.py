from app.connectors import service as connectors_service


def test_service_dispatches_to_s3_driver_not_unknown_engine():
    result = connectors_service.test_connection("s3", {}, {})

    assert "unknown engine" not in result.message.lower()
    assert "required" in result.message.lower()


def test_service_dispatches_to_azure_driver_not_unknown_engine():
    result = connectors_service.test_connection("azure", {}, {})

    assert "unknown engine" not in result.message.lower()
    assert "required" in result.message.lower()


def test_service_dispatches_to_gcs_driver_not_unknown_engine():
    result = connectors_service.test_connection("gcs", {}, {})

    assert "unknown engine" not in result.message.lower()
    assert "required" in result.message.lower()
