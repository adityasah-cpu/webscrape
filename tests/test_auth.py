"""
Tests for Google Sign-In: the login gate (before_request hook), and the
/api/auth/* endpoints. google_id_token.verify_oauth2_token (the actual
signature/audience/expiry check) is mocked - these tests exercise our
own wiring around it, not Google's library.
"""
import api as api_module


class TestLoginGate:
    def test_unauthenticated_request_to_protected_endpoint_returns_401(self, anonymous_client):
        res = anonymous_client.get("/api/jobs")
        assert res.status_code == 401
        assert res.get_json()["success"] is False

    def test_authenticated_request_to_protected_endpoint_succeeds(self, client, mocker):
        mocker.patch.object(api_module, "load_jobs_from_db", return_value=[])
        res = client.get("/api/jobs")
        assert res.status_code == 200

    def test_auth_me_is_reachable_without_a_session(self, anonymous_client):
        """auth_me must be exempt from the gate - the frontend calls it on
        page load to decide whether to show the sign-in overlay, which
        would be impossible if it itself required being signed in."""
        res = anonymous_client.get("/api/auth/me")
        assert res.status_code == 200
        assert res.get_json()["authenticated"] is False

    def test_auth_config_is_reachable_without_a_session(self, anonymous_client):
        res = anonymous_client.get("/api/auth/config")
        assert res.status_code == 200

    def test_frontend_route_is_never_gated(self, anonymous_client):
        """/ isn't under /api/, so it's served regardless of session -
        the sign-in overlay itself has to load before anyone can sign in."""
        res = anonymous_client.get("/")
        assert res.status_code == 200


class TestGoogleSignInEndpoint:
    def test_missing_credential_returns_400(self, anonymous_client):
        res = anonymous_client.post("/api/auth/google", json={})
        assert res.status_code == 400

    def test_valid_token_starts_a_session(self, anonymous_client, mocker):
        mocker.patch.object(api_module, "GOOGLE_CLIENT_ID", "test-client-id")
        mocker.patch.object(
            api_module.google_id_token, "verify_oauth2_token",
            return_value={"email": "user@example.com", "name": "Test User", "picture": "https://example.com/pic.jpg"}
        )
        res = anonymous_client.post("/api/auth/google", json={"credential": "fake-but-mocked-token"})
        assert res.status_code == 200
        body = res.get_json()
        assert body["success"] is True
        assert body["user"]["email"] == "user@example.com"

        # The session this client now holds should pass the login gate.
        me = anonymous_client.get("/api/auth/me")
        assert me.get_json()["authenticated"] is True

    def test_invalid_token_returns_401(self, anonymous_client, mocker):
        mocker.patch.object(api_module, "GOOGLE_CLIENT_ID", "test-client-id")
        mocker.patch.object(
            api_module.google_id_token, "verify_oauth2_token",
            side_effect=ValueError("Token used too early")
        )
        res = anonymous_client.post("/api/auth/google", json={"credential": "forged-token"})
        assert res.status_code == 401
        assert res.get_json()["success"] is False

    def test_unconfigured_client_id_returns_500(self, anonymous_client, mocker):
        mocker.patch.object(api_module, "GOOGLE_CLIENT_ID", "")
        res = anonymous_client.post("/api/auth/google", json={"credential": "x"})
        assert res.status_code == 500


class TestLogoutEndpoint:
    def test_logout_clears_the_session(self, client):
        # `client` fixture starts pre-authenticated.
        assert client.get("/api/auth/me").get_json()["authenticated"] is True
        res = client.post("/api/auth/logout")
        assert res.status_code == 200
        assert client.get("/api/auth/me").get_json()["authenticated"] is False
