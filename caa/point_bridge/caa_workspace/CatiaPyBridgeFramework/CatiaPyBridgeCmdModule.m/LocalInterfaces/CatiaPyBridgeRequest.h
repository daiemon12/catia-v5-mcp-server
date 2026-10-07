#ifndef CatiaPyBridgeRequest_H
#define CatiaPyBridgeRequest_H

#include <string>

class CatiaPyBridgeRequest
{
public:
    std::string JobId;
    std::string Method;
    std::string RequestPath;
    std::string ResponsePath;
    std::string ParamsJson;

    std::string ErrorCode;
    std::string ErrorMessage;
    std::string ErrorDetail;

    CatiaPyBridgeRequest();

    void SetError(
        const std::string& code,
        const std::string& message,
        const std::string& detail = "");
};

#endif
