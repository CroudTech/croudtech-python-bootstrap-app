import json
from unittest import mock

import botocore.exceptions
import click
import pytest

from croudtech_bootstrap_app.bootstrap import BootstrapManager
from croudtech_bootstrap_app.tests.bootstrap_test import values_path


def manager():
    return BootstrapManager("/appconfig", "eu-west-2", click, values_path, "test")


def test_put_config_does_not_delete_secrets_by_default():
    m = manager()
    with mock.patch.object(m, "cleanup_ssm_parameters"), mock.patch.object(
        m, "cleanup_secrets"
    ) as cleanup, mock.patch(
        "croudtech_bootstrap_app.bootstrap.BootstrapApp.upload_to_s3", create=True
    ), mock.patch(
        "croudtech_bootstrap_app.bootstrap.BootstrapApp.push_parameters", create=True
    ), mock.patch(
        "croudtech_bootstrap_app.bootstrap.BootstrapApp.push_secrets", create=True
    ):
        m.put_config()
    cleanup.assert_not_called()


def test_put_config_delete_first_opts_in_to_cleanup():
    m = manager()
    with mock.patch.object(m, "cleanup_ssm_parameters"), mock.patch.object(
        m, "cleanup_secrets"
    ) as cleanup, mock.patch(
        "croudtech_bootstrap_app.bootstrap.BootstrapApp.upload_to_s3", create=True
    ), mock.patch(
        "croudtech_bootstrap_app.bootstrap.BootstrapApp.push_parameters", create=True
    ), mock.patch(
        "croudtech_bootstrap_app.bootstrap.BootstrapApp.push_secrets", create=True
    ):
        m.put_config(delete_first=True)
    cleanup.assert_called_once()


def _app():
    return manager().environments["TestEnv1"].apps["TestApp"]


def _client_with_existing(existing):
    client = mock.MagicMock()

    class Exists(Exception):
        pass

    client.exceptions.ResourceExistsException = Exists
    client.create_secret.side_effect = Exists()
    client.get_secret_value.return_value = {"SecretString": existing}
    return client


def test_json_secret_is_merged_preserving_unknown_keys():
    app = _app()
    client = _client_with_existing(json.dumps({"refresh_token": "r", "a": "old"}))
    app.environment.manager._secrets_client = client
    app.create_secret("n", json.dumps({"a": "new"}), [], True)
    sent = json.loads(client.update_secret.call_args.kwargs["SecretString"])
    assert sent == {"refresh_token": "r", "a": "new"}


def test_plain_secret_is_overwritten():
    app = _app()
    client = _client_with_existing("oldvalue")
    app.environment.manager._secrets_client = client
    app.create_secret("n", "newvalue", [], True)
    assert client.update_secret.call_args.kwargs["SecretString"] == "newvalue"


def test_get_secret_error_does_not_overwrite_blob():
    app = _app()
    client = _client_with_existing("{}")
    client.get_secret_value.side_effect = botocore.exceptions.ClientError(
        {"Error": {"Code": "ThrottlingException"}}, "GetSecretValue"
    )
    app.environment.manager._secrets_client = client
    with pytest.raises(botocore.exceptions.ClientError):
        app.create_secret("n", json.dumps({"a": "new"}), [], True)
    client.update_secret.assert_not_called()


def test_non_object_json_existing_is_overwritten():
    app = _app()
    client = _client_with_existing("[1, 2]")
    app.environment.manager._secrets_client = client
    app.create_secret("n", json.dumps({"a": "new"}), [], True)
    assert json.loads(client.update_secret.call_args.kwargs["SecretString"]) == {"a": "new"}
