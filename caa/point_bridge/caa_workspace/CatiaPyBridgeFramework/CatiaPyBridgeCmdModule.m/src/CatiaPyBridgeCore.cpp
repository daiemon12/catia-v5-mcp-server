#include "CatiaPyBridgeCore.h"
#include "CatiaPyBridgePointDemo.h"
HRESULT CatiaPyBridgeCore::Execute(const CatiaPyBridgeRequest& request, CatiaPyBridgeResponse& response)
{
    response.JobId = request.JobId;
    response.Method = request.Method;
    response.ResponsePath = request.ResponsePath;
    if (request.Method == "catia_caa_demo_create_point")
        return CatiaPyBridgePointDemo::CreatePoint(request, response);
    response.SetError("CAA_UNKNOWN_METHOD", "This DLL implements only catia_caa_demo_create_point",
        "{\"failure_stage\":\"dispatch\",\"modified\":false,\"automatic_retry_allowed\":false}");
    return S_OK;
}
