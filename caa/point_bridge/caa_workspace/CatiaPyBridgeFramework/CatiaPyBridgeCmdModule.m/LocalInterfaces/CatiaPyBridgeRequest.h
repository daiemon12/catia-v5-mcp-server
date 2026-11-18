#ifndef CatiaPyBridgeRequest_H
#define CatiaPyBridgeRequest_H

#include "nlohmann_json.h"
#include <string>

class CatiaPyBridgeRequest
{
public:
    std::string JobId;
    std::string Method;
    nlohmann::json Params;

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
