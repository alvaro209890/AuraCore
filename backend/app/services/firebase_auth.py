from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.config import Settings

try:
    import firebase_admin
    from firebase_admin import auth as firebase_admin_auth
    from firebase_admin import credentials as firebase_credentials
except ImportError:  # pragma: no cover - depends on runtime install
    firebase_admin = None
    firebase_admin_auth = None
    firebase_credentials = None

try:
    from google.auth.transport.requests import Request as GoogleAuthRequest
    from google.oauth2 import id_token as google_id_token
except ImportError:  # pragma: no cover - depends on runtime install
    GoogleAuthRequest = None
    google_id_token = None


class FirebaseAuthError(RuntimeError):
    """Raised when Firebase authentication cannot verify a bearer token."""


@dataclass(slots=True)
class VerifiedFirebaseUser:
    uid: str
    email: str
    email_verified: bool
    name: str | None = None


class FirebaseAuthService:
    def __init__(self, *, settings: Settings) -> None:
        self.settings = settings
        self._initialized = False
        self._verification_mode: str | None = None

    def verify_bearer_token(self, token: str) -> VerifiedFirebaseUser:
        normalized_token = token.strip()
        if not normalized_token:
            raise FirebaseAuthError("Token do Firebase ausente.")
        self._ensure_initialized()
        claims: dict[str, Any] | None = None
        try:
            if self._verification_mode == "admin":
                assert firebase_admin_auth is not None
                claims = firebase_admin_auth.verify_id_token(normalized_token)
            elif self._verification_mode == "google":
                if GoogleAuthRequest is None or google_id_token is None:
                    raise FirebaseAuthError(
                        "google-auth nao esta disponivel no backend. Instale as dependencias do backend para validar o token do Firebase."
                    )
                claims = google_id_token.verify_firebase_token(
                    normalized_token,
                    GoogleAuthRequest(),
                    self.settings.firebase_project_id,
                )
        except FirebaseAuthError:
            raise
        except Exception as exc:  # pragma: no cover - relies on firebase/google internals
            raise FirebaseAuthError("Token do Firebase invalido ou expirado.") from exc

        if not claims:
            raise FirebaseAuthError("Nao foi possivel validar o token do Firebase.")

        email = str(claims.get("email") or "").strip().lower()
        if not email:
            raise FirebaseAuthError("A conta autenticada do Firebase nao possui email.")
        uid = str(claims.get("uid") or claims.get("user_id") or "").strip()
        if not uid:
            raise FirebaseAuthError("A conta autenticada do Firebase nao possui uid valido.")

        return VerifiedFirebaseUser(
            uid=uid,
            email=email,
            email_verified=bool(claims.get("email_verified")),
            name=str(claims.get("name")).strip() if claims.get("name") else None,
        )

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        if firebase_admin is None or firebase_admin_auth is None or firebase_credentials is None:
            if GoogleAuthRequest is not None and google_id_token is not None:
                self._verification_mode = "google"
                self._initialized = True
                return
            raise FirebaseAuthError(
                "firebase-admin nao esta instalado no backend. Instale as dependencias do backend antes de usar a autenticacao."
            )

        options: dict[str, Any] = {"projectId": self.settings.firebase_project_id}
        service_account_path = (self.settings.firebase_service_account_path or "").strip()

        if service_account_path:
            credential_path = Path(service_account_path).expanduser()
            if not credential_path.is_file():
                raise FirebaseAuthError(
                    f"Arquivo da service account do Firebase nao encontrado: {credential_path}"
                )
            try:
                app = firebase_admin.get_app()
            except ValueError:
                credential = firebase_credentials.Certificate(str(credential_path))
                firebase_admin.initialize_app(credential=credential, options=options)
            self._verification_mode = "admin"
            self._initialized = True
            return

        # No service account configured — prefer google-auth public-key
        # verification which works without any local GCP credentials.
        if GoogleAuthRequest is not None and google_id_token is not None:
            self._verification_mode = "google"
            self._initialized = True
            return

        # Last resort: try firebase-admin with default credentials (ADC).
        try:
            try:
                firebase_admin.get_app()
            except ValueError:
                firebase_admin.initialize_app(options=options)
            self._verification_mode = "admin"
        except Exception as exc:
            raise FirebaseAuthError(
                f"Nao foi possivel inicializar o Firebase Admin sem service account: {exc}"
            ) from exc
        self._initialized = True
