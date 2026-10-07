#ifndef CatiaPyBridgeResponse_H
#define CatiaPyBridgeResponse_H

#include <string>

class CatiaPyBridgeResponse
{
public:
    std::string JobId;
    std::string Method;
    std::string ResponsePath;
    int Ok;
    std::string ResultJson;
    std::string ErrorCode;
    std::string ErrorMessage;
    std::string ErrorDetail;
    long ElapsedMs;
    std::string Transport;
    unsigned __int64 QueueSequence;

    CatiaPyBridgeResponse();

    void SetSuccess(const std::string& resultJson);
    void SetError(
        const std::string& code,
        const std::string& message,
        const std::string& detail = "");
};

#endif
