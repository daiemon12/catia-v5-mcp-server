#include "CatiaPyBridgeResponse.h"

CatiaPyBridgeResponse::CatiaPyBridgeResponse()
    : JobId("unknown"),
      Method("unknown"),
      ResponsePath(""),
      Ok(0),
      ResultJson("{}"),
      ErrorCode(""),
      ErrorMessage(""),
      ErrorDetail(""),
      ElapsedMs(0),
      Transport("runonce_file"),
      QueueSequence(0)
{
}

void CatiaPyBridgeResponse::SetSuccess(const std::string& resultJson)
{
    Ok = 1;
    ResultJson = resultJson.empty() ? "{}" : resultJson;
    ErrorCode = "";
    ErrorMessage = "";
    ErrorDetail = "";
}

void CatiaPyBridgeResponse::SetError(
    const std::string& code,
    const std::string& message,
    const std::string& detail)
{
    Ok = 0;
    ResultJson = "{}";
    ErrorCode = code;
    ErrorMessage = message;
    ErrorDetail = detail;
}
