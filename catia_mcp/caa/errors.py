class CatiaBridgeTimeoutError(TimeoutError):
    pass


class CatiaBridgePreDeliveryError(RuntimeError):
    modified = False

    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


class CatiaBridgeResponseError(RuntimeError):
    def __init__(self, code, message, detail=None):
        self.code, self.detail = code, detail
        super().__init__(f"{code}: {message}")
