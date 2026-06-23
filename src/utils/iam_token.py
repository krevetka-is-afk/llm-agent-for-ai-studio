import time
import jwt
import json

import yandexcloud

from yandex.cloud.iam.v1.iam_token_service_pb2 import (CreateIamTokenRequest)
from yandex.cloud.iam.v1.iam_token_service_pb2_grpc import IamTokenServiceStub


class IAMTokenProvider:
    def __init__(self, key_path: str):
        with open(key_path, 'r') as f:
            self.sa_key = json.loads(f.read())
            for key in ['private_key', 'id', 'service_account_id']:
                if key not in self.sa_key:
                    raise KeyError(f"No field {key} in {key_path}")

        self.sdk = yandexcloud.SDK(service_account_key=self.sa_key)
        self.iam_service = self.sdk.client(IamTokenServiceStub)
        self.prev_token = None
        self.time = 0

    def _create_jwt(self):
        now = int(time.time())
        payload = {
            'aud': 'https://iam.api.cloud.yandex.net/iam/v1/tokens',
            'iss': self.sa_key['service_account_id'],
            'iat': now,
            'exp': now + 3600
        }

        encoded_token = jwt.encode(
            payload,
            self.sa_key['private_key'],
            algorithm='PS256',
            headers={'kid': self.sa_key['id']}
        )

        return encoded_token

    def create_iam_token(self):
        if self.prev_token is not None and int(time.time() - self.time) < 3600:
            return self.prev_token
        jwt = self._create_jwt()

        iam_token = self.iam_service.Create(
            CreateIamTokenRequest(jwt=jwt)
        )

        self.time = time.time()
        self.prev_token = iam_token.iam_token

        return iam_token.iam_token
