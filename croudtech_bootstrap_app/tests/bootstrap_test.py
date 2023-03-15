import os

import click

import croudtech_bootstrap_app.bootstrap

values_path = os.path.join(os.path.dirname(__file__), "test_values")


def test_manager():
    expected_values = {
        "TestEnv1": {
            "TestApp": {
                "APPVALUE1": "foo1",
                "APPSECRET1": "foo1",
            },
            "common": {
                "COMMONVALUE1": "blah1",
                "COMMONSECRET1": "foo1",
            },
        },
        "TestEnv2": {
            "TestApp": {
                "APPVALUE1": "foo2",
                "APPSECRET1": "foo2",
            },
            "common": {
                "COMMONVALUE1": "blah2",
                "COMMONSECRET1": "foo2",
            },
        },
    }
    manager = croudtech_bootstrap_app.bootstrap.BootstrapManager(
        "/appconfig", "eu-west-2", click, values_path, "test"
    )
    for env_name, env in expected_values.items():
        assert env_name in manager.environments.keys()
        for app_name, app in env.items():
            assert app_name in manager.environments[env_name].apps.keys()
            for key, value in app.items():
                assert (
                    key
                    in manager.environments[env_name]
                    .apps[app_name]
                    .get_local_params()
                    .keys()
                )
                assert (
                    manager.environments[env_name]
                    .apps[app_name]
                    .get_local_params()[key]
                    == value
                )
            # assert "APPVALUE1" in manager.environments[env].apps["TestApp"].local_values.keys()
            # assert  manager.environments[env].apps["TestApp"].local_values["APPVALUE1"] == "foo1"
            # assert "APPSECRET1" in manager.environments[env].apps["TestApp"].local_secrets.keys()
            # assert  manager.environments[env].apps["TestApp"].local_secrets["APPSECRET1"] == "foo1"
