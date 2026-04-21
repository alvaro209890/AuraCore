from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
import re
import shutil
import sqlite3
import threading
from uuid import UUID, uuid4

from app.services.banco_de_dados_local_store import BancoDeDadosLocalStore

USERNAME_PATTERN = re.compile(r"^[a-z0-9_]{3,32}$")


class AccountRegistryError(RuntimeError):
    """Raised when the account registry cannot fulfill a request."""


class UsernameValidationError(AccountRegistryError):
    """Raised when the requested username is invalid."""


class UsernameAlreadyExistsError(AccountRegistryError):
    """Raised when a username is already reserved by another account."""


class EmailAlreadyExistsError(AccountRegistryError):
    """Raised when an email is already linked to another account."""


@dataclass(slots=True)
class AccountRecord:
    firebase_uid: str
    app_user_id: UUID
    username: str
    email: str
    observer_owner_phone: str | None
    user_root_path: str
    db_path: str
    status: str
    created_at: datetime
    updated_at: datetime


class AccountRegistry:
    def __init__(
        self,
        *,
        database_root: str,
        registry_path: str,
        message_retention_max_rows: int,
        first_analysis_queue_limit: int,
    ) -> None:
        self.database_root = Path(database_root).expanduser()
        self.registry_path = Path(registry_path).expanduser()
        self.message_retention_max_rows = message_retention_max_rows
        self.first_analysis_queue_limit = first_analysis_queue_limit
        self._lock = threading.RLock()
        self._ensure_registry_ready()
        self._conn = sqlite3.connect(str(self.registry_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._initialize_schema()

    def normalize_username(self, username: str) -> str:
        normalized = username.strip().lower()
        if not USERNAME_PATTERN.fullmatch(normalized):
            raise UsernameValidationError(
                "O nome de usuario deve usar apenas letras minusculas, numeros ou underscore e ter entre 3 e 32 caracteres."
            )
        return normalized

    def normalize_email(self, email: str) -> str:
        normalized = email.strip().lower()
        if not normalized or "@" not in normalized:
            raise AccountRegistryError("Email invalido para provisionamento da conta.")
        return normalized

    def normalize_contact_phone(self, value: str | None) -> str | None:
        if value is None:
            return None
        digits = "".join(char for char in str(value) if char.isdigit())
        if len(digits) >= 12 and digits.startswith("55"):
            digits = digits[2:]
        if len(digits) > 11:
            digits = digits[-11:]
        if 8 <= len(digits) <= 11:
            return digits
        return None

    def build_phone_variants(self, value: str | None) -> set[str]:
        normalized = self.normalize_contact_phone(value)
        if not normalized:
            return set()

        digits = normalized
        variants = {digits}

        if len(digits) in {10, 11}:
            area_code = digits[:2]
            local_number = digits[2:]

            if len(local_number) == 9 and local_number.startswith("9"):
                base8 = local_number[1:]
            elif len(local_number) == 8:
                base8 = local_number
            else:
                return variants

            variants.update(
                {
                    f"55{area_code}9{base8}",
                    f"55{area_code}{base8}",
                    f"{area_code}9{base8}",
                    f"{area_code}{base8}",
                }
            )
            return variants

        if len(digits) == 9 and digits.startswith("9"):
            variants.add(digits[1:])
        elif len(digits) == 8:
            variants.add(f"9{digits}")

        return {variant for variant in variants if 8 <= len(variant) <= 11}

    def phone_matches(self, left: str | None, right: str | None) -> bool:
        left_variants = self.build_phone_variants(left)
        right_variants = self.build_phone_variants(right)
        if not left_variants or not right_variants:
            return False
        return bool(left_variants.intersection(right_variants))

    def is_username_available(self, username: str) -> tuple[bool, str]:
        normalized = self.normalize_username(username)
        return self.get_account_by_username(normalized) is None, normalized

    def get_account_by_firebase_uid(self, firebase_uid: str) -> AccountRecord | None:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT
                    firebase_uid,
                    app_user_id,
                    username,
                    email,
                    observer_owner_phone,
                    user_root_path,
                    db_path,
                    status,
                    created_at,
                    updated_at
                FROM accounts
                WHERE firebase_uid = ?
                LIMIT 1
                """,
                (firebase_uid.strip(),),
            ).fetchone()
        return self._parse_row(row)

    def get_account_by_app_user_id(self, app_user_id: UUID | str) -> AccountRecord | None:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT
                    firebase_uid,
                    app_user_id,
                    username,
                    email,
                    observer_owner_phone,
                    user_root_path,
                    db_path,
                    status,
                    created_at,
                    updated_at
                FROM accounts
                WHERE app_user_id = ?
                LIMIT 1
                """,
                (str(app_user_id).strip(),),
            ).fetchone()
        return self._parse_row(row)

    def get_account_by_username(self, username: str) -> AccountRecord | None:
        normalized = self.normalize_username(username)
        with self._lock:
            row = self._conn.execute(
                """
                SELECT
                    firebase_uid,
                    app_user_id,
                    username,
                    email,
                    observer_owner_phone,
                    user_root_path,
                    db_path,
                    status,
                    created_at,
                    updated_at
                FROM accounts
                WHERE username_normalized = ?
                LIMIT 1
                """,
                (normalized,),
            ).fetchone()
        return self._parse_row(row)

    def get_account_by_observer_owner_phone(self, phone: str | None) -> AccountRecord | None:
        target_variants = self.build_phone_variants(phone)
        if not target_variants:
            return None

        with self._lock:
            rows = self._conn.execute(
                """
                SELECT
                    firebase_uid,
                    app_user_id,
                    username,
                    email,
                    observer_owner_phone,
                    user_root_path,
                    db_path,
                    status,
                    created_at,
                    updated_at
                FROM accounts
                WHERE status = 'active'
                  AND observer_owner_phone IS NOT NULL
                ORDER BY created_at ASC
                """
            ).fetchall()

        for row in rows:
            if self.phone_matches(str(row["observer_owner_phone"]).strip(), phone):
                return self._parse_row(row)
        return None

    def list_active_accounts(self) -> list[AccountRecord]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT
                    firebase_uid,
                    app_user_id,
                    username,
                    email,
                    observer_owner_phone,
                    user_root_path,
                    db_path,
                    status,
                    created_at,
                    updated_at
                FROM accounts
                WHERE status = 'active'
                ORDER BY created_at ASC
                """
            ).fetchall()
        return [parsed for row in rows if (parsed := self._parse_row(row)) is not None]

    def set_observer_owner_phone(self, *, app_user_id: UUID | str, phone: str | None) -> AccountRecord | None:
        normalized_phone = self.normalize_contact_phone(phone)
        with self._lock:
            account = self.get_account_by_app_user_id(app_user_id)
            if account is None:
                return None

            if account.observer_owner_phone == normalized_phone:
                return account

            if normalized_phone:
                rows = self._conn.execute(
                    """
                    SELECT app_user_id, observer_owner_phone
                    FROM accounts
                    WHERE status = 'active'
                      AND observer_owner_phone IS NOT NULL
                      AND app_user_id != ?
                    """,
                    (str(app_user_id).strip(),),
                ).fetchall()
                for row in rows:
                    existing_phone = str(row["observer_owner_phone"]).strip()
                    if self.phone_matches(existing_phone, normalized_phone):
                        raise AccountRegistryError(
                            "Esse numero do observador ja esta vinculado a outra conta do AuraCore."
                        )

            updated_at = datetime.now(UTC).isoformat()
            self._conn.execute(
                """
                UPDATE accounts
                SET observer_owner_phone = ?, updated_at = ?
                WHERE app_user_id = ?
                """,
                (normalized_phone, updated_at, str(app_user_id).strip()),
            )
            self._conn.commit()

        return self.get_account_by_app_user_id(app_user_id)

    def clear_observer_owner_phone(self, *, app_user_id: UUID | str) -> AccountRecord | None:
        return self.set_observer_owner_phone(app_user_id=app_user_id, phone=None)

    def sync_account_email(self, *, firebase_uid: str, email: str) -> AccountRecord | None:
        normalized_email = self.normalize_email(email)
        current = self.get_account_by_firebase_uid(firebase_uid)
        if current is None:
            return None
        if current.email == normalized_email:
            return current
        with self._lock:
            conflicting = self._conn.execute(
                "SELECT firebase_uid FROM accounts WHERE email_normalized = ? LIMIT 1",
                (normalized_email,),
            ).fetchone()
            if conflicting is not None and str(conflicting["firebase_uid"]).strip() != firebase_uid.strip():
                raise EmailAlreadyExistsError("Esse email ja esta vinculado a outro usuario do AuraCore.")
            updated_at = datetime.now(UTC).isoformat()
            self._conn.execute(
                """
                UPDATE accounts
                SET email = ?, email_normalized = ?, updated_at = ?
                WHERE firebase_uid = ?
                """,
                (normalized_email, normalized_email, updated_at, firebase_uid.strip()),
            )
            self._conn.commit()
        return self.get_account_by_firebase_uid(firebase_uid)

    def provision_account(
        self,
        *,
        firebase_uid: str,
        email: str,
        username: str,
    ) -> AccountRecord:
        normalized_username = self.normalize_username(username)
        normalized_email = self.normalize_email(email)
        existing = self.get_account_by_firebase_uid(firebase_uid)
        if existing is not None:
            if existing.username != normalized_username:
                raise UsernameAlreadyExistsError("Essa conta do Firebase ja esta provisionada com outro nome de usuario.")
            if existing.email != normalized_email:
                synced = self.sync_account_email(firebase_uid=firebase_uid, email=normalized_email)
                return synced or existing
            return existing

        username_owner = self.get_account_by_username(normalized_username)
        if username_owner is not None:
            raise UsernameAlreadyExistsError("Esse nome de usuario ja esta em uso.")

        with self._lock:
            email_owner = self._conn.execute(
                "SELECT firebase_uid FROM accounts WHERE email_normalized = ? LIMIT 1",
                (normalized_email,),
            ).fetchone()
        if email_owner is not None:
            raise EmailAlreadyExistsError("Esse email ja esta em uso.")

        app_user_id = uuid4()
        created_at = datetime.now(UTC)
        user_root = self.database_root / normalized_username
        sqlite_dir = user_root / "sqlite"
        backups_dir = user_root / "backups"
        exports_dir = user_root / "exports"
        db_path = sqlite_dir / "auracore.sqlite3"

        try:
            sqlite_dir.mkdir(parents=True, exist_ok=True)
            backups_dir.mkdir(parents=True, exist_ok=True)
            exports_dir.mkdir(parents=True, exist_ok=True)
            BancoDeDadosLocalStore(
                database_path=str(db_path),
                default_user_id=app_user_id,
                message_retention_max_rows=self.message_retention_max_rows,
                first_analysis_queue_limit=self.first_analysis_queue_limit,
            )
            with self._lock:
                self._conn.execute(
                    """
                    INSERT INTO accounts (
                        firebase_uid,
                        app_user_id,
                        username,
                        username_normalized,
                        email,
                        email_normalized,
                        observer_owner_phone,
                        user_root_path,
                        db_path,
                        status,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
                    """,
                    (
                        firebase_uid.strip(),
                        str(app_user_id),
                        normalized_username,
                        normalized_username,
                        normalized_email,
                        normalized_email,
                        None,
                        str(user_root),
                        str(db_path),
                        created_at.isoformat(),
                        created_at.isoformat(),
                    ),
                )
                self._conn.commit()
        except Exception as exc:
            shutil.rmtree(user_root, ignore_errors=True)
            raise AccountRegistryError(f"Falha ao provisionar a conta local do AuraCore: {exc}") from exc

        created = self.get_account_by_firebase_uid(firebase_uid)
        if created is None:
            raise AccountRegistryError("A conta foi provisionada, mas nao foi encontrada no registro local.")
        return created

    def _ensure_registry_ready(self) -> None:
        self.database_root.mkdir(parents=True, exist_ok=True)
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)

    def _initialize_schema(self) -> None:
        with self._lock:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS accounts (
                    firebase_uid TEXT PRIMARY KEY,
                    app_user_id TEXT NOT NULL UNIQUE,
                    username TEXT NOT NULL,
                    username_normalized TEXT NOT NULL UNIQUE,
                    email TEXT NOT NULL,
                    email_normalized TEXT NOT NULL UNIQUE,
                    observer_owner_phone TEXT,
                    user_root_path TEXT NOT NULL,
                    db_path TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            columns = {
                str(row["name"]).strip()
                for row in self._conn.execute("PRAGMA table_info(accounts)").fetchall()
            }
            if "observer_owner_phone" not in columns:
                self._conn.execute("ALTER TABLE accounts ADD COLUMN observer_owner_phone TEXT")
            self._conn.execute("CREATE INDEX IF NOT EXISTS accounts_status_idx ON accounts (status, created_at ASC)")
            self._conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS accounts_observer_owner_phone_uidx
                ON accounts (observer_owner_phone)
                WHERE observer_owner_phone IS NOT NULL
                """
            )
            self._conn.commit()

    def _parse_row(self, row: sqlite3.Row | None) -> AccountRecord | None:
        if row is None:
            return None
        return AccountRecord(
            firebase_uid=str(row["firebase_uid"]).strip(),
            app_user_id=UUID(str(row["app_user_id"]).strip()),
            username=str(row["username"]).strip(),
            email=str(row["email"]).strip(),
            observer_owner_phone=self.normalize_contact_phone(row["observer_owner_phone"]),
            user_root_path=str(row["user_root_path"]).strip(),
            db_path=str(row["db_path"]).strip(),
            status=str(row["status"]).strip() or "active",
            created_at=datetime.fromisoformat(str(row["created_at"]).replace("Z", "+00:00")),
            updated_at=datetime.fromisoformat(str(row["updated_at"]).replace("Z", "+00:00")),
        )
