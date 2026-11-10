import json
import os
import threading

import firebase_admin
from firebase_admin import credentials, firestore

import backend.core.config  # noqa: F401  (.env 로딩 보장)
from backend.core.exceptions import ExternalServiceError


_init_lock = threading.Lock()  # 동시 요청에서 initialize_app 중복 호출 방지


def initialize_firebase():
    if firebase_admin._apps:
        return
    with _init_lock:
        if firebase_admin._apps:
            return
        _initialize_app()


def _initialize_app():

    service_account_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")
    service_account_path = os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH")

    if service_account_json:
        service_account_info = json.loads(service_account_json)
        cred = credentials.Certificate(service_account_info)

    elif service_account_path:
        if not os.path.exists(service_account_path):
            raise ExternalServiceError(
                f"Firebase 서비스 계정 파일을 찾을 수 없습니다: "
                f"{service_account_path}"
            )

        cred = credentials.Certificate(service_account_path)

    else:
        raise ExternalServiceError(
            "Firebase 인증 정보가 설정되지 않았습니다. "
            "FIREBASE_SERVICE_ACCOUNT_PATH 또는 "
            "FIREBASE_SERVICE_ACCOUNT_JSON을 설정하세요."
        )

    firebase_admin.initialize_app(cred)


def get_firestore_client():
    initialize_firebase()
    return firestore.client()