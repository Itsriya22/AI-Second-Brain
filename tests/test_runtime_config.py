"""Tests for local and hosted runtime configuration lookup."""

import os
import unittest
from unittest.mock import patch

from streamlit.errors import StreamlitSecretNotFoundError

from app import _is_read_only
from lib.llm import groq_client
from lib.runtime_config import get_runtime_setting


class RuntimeConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        patcher = patch("lib.runtime_config.load_dotenv")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_environment_value_takes_precedence_over_streamlit_secret(self) -> None:
        with (
            patch.dict(os.environ, {"SECONDSELF_TEST_SETTING": " from env "}),
            patch("lib.runtime_config._streamlit_secrets") as secret_source,
        ):
            self.assertEqual(get_runtime_setting("SECONDSELF_TEST_SETTING"), "from env")

        secret_source.assert_not_called()

    def test_blank_environment_value_falls_back_to_streamlit_secret(self) -> None:
        with (
            patch.dict(os.environ, {"SECONDSELF_TEST_SETTING": "  "}),
            patch("lib.runtime_config._streamlit_secrets", return_value={"SECONDSELF_TEST_SETTING": " from cloud "}),
        ):
            self.assertEqual(get_runtime_setting("SECONDSELF_TEST_SETTING"), "from cloud")

    def test_secret_lookup_supports_boolean_values(self) -> None:
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("lib.runtime_config._streamlit_secrets", return_value={"SECONSELF_READONLY": True}),
        ):
            self.assertIs(get_runtime_setting("SECONSELF_READONLY"), True)

    def test_read_only_flag_uses_streamlit_secret(self) -> None:
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("lib.runtime_config._streamlit_secrets", return_value={"SECONSELF_READONLY": "yes"}),
        ):
            self.assertTrue(_is_read_only())

    def test_missing_streamlit_secrets_returns_none(self) -> None:
        with (
            patch.dict(os.environ, {}, clear=True),
            patch(
                "lib.runtime_config._streamlit_secrets",
                side_effect=StreamlitSecretNotFoundError("No secrets configured"),
            ),
        ):
            self.assertIsNone(get_runtime_setting("GROQ_API_KEY"))

    def test_unsupported_secret_type_is_reported(self) -> None:
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("lib.runtime_config._streamlit_secrets", return_value={"GROQ_API_KEY": ["invalid"]}),
            self.assertRaisesRegex(ValueError, "must be a string or boolean"),
        ):
            get_runtime_setting("GROQ_API_KEY")

    def test_groq_client_uses_streamlit_secret_and_never_logs_it(self) -> None:
        key = "cloud-test-key-do-not-log"
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("lib.runtime_config._streamlit_secrets", return_value={"GROQ_API_KEY": key}),
            patch("lib.llm.Groq", autospec=True) as groq_constructor,
            self.assertNoLogs("lib.llm", level="INFO"),
        ):
            groq_client()

        groq_constructor.assert_called_once_with(api_key=key)

    def test_groq_client_uses_existing_environment_key(self) -> None:
        key = "environment-test-key"
        with (
            patch.dict(os.environ, {"GROQ_API_KEY": key}),
            patch("lib.runtime_config._streamlit_secrets") as secret_source,
            patch("lib.llm.Groq", autospec=True) as groq_constructor,
        ):
            groq_client()

        groq_constructor.assert_called_once_with(api_key=key)
        secret_source.assert_not_called()

    def test_groq_client_reports_missing_key_without_revealing_values(self) -> None:
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("lib.runtime_config._streamlit_secrets", return_value={}),
            self.assertRaisesRegex(ValueError, "GROQ_API_KEY is required"),
        ):
            groq_client()


if __name__ == "__main__":
    unittest.main()
