from app.connectors.drivers import s3_driver


def test_test_rejects_missing_required_fields_without_touching_boto3():
    result = s3_driver.test({}, {})

    assert result.ok is False
    assert "required" in result.message.lower()


def test_sync_rejects_missing_required_fields_without_touching_boto3():
    result = s3_driver.sync({}, {})

    assert result.ok is False
    assert result.datasets == []


def test_test_passes_validation_with_correctly_split_config_and_secrets():
    """Reproduces what ConnectorsService.splitFields actually produces once
    accessKeyId is marked secret in the registry: config holds the non-secret
    fields, secrets holds accessKeyId/secretAccessKey. This must get past
    _missing_required — a real boto3 call follows, and since there's no live
    AWS account here a network/credentials failure is expected, so we assert
    on the message NOT being the validation message rather than asserting
    ok is True.
    """
    config = {"bucket": "lyra-analytics-exports", "prefix": "exports/", "region": "us-east-1", "format": "csv"}
    secrets = {"accessKeyId": "AKIAIOSFODNN7EXAMPLE", "secretAccessKey": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"}

    result = s3_driver.test(config, secrets)

    assert result.message != "Bucket name, region, access key ID and secret access key are required."
