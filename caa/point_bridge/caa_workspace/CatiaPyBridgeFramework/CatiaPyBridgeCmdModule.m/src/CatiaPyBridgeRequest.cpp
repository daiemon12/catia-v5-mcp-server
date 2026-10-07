#include "CatiaPyBridgeRequest.h"

CatiaPyBridgeRequest::CatiaPyBridgeRequest()
    : JobId(""),
      Method(""),
      RequestPath(""),
      ResponsePath(""),
      ParamsJson("{}"),
      ErrorCode(""),
      ErrorMessage(""),
      ErrorDetail("")
{
}

void CatiaPyBridgeRequest::SetError(
    const std::string& code,
    const std::string& message,
    const std::string& detail)
{
    ErrorCode = code;
    ErrorMessage = message;
    ErrorDetail = detail;
}
