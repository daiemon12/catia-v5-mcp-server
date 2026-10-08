class CatiaBridgeTimeoutError(TimeoutError):
    pass


class CatiaBridgeResponseError(RuntimeError):
    def __init__(self, code, message, detail=None):
        self.code, self.detail = code, detail
        super().__init__(f"{code}: {message}")
