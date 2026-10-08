#include "CatiaPyBridgeRunOnceCommand.h"
#include "CatiaPyBridgeCore.h"
#include "CatiaPyBridgeFileBridge.h"
#include "CatiaPyBridgeLogger.h"

#include "CATCreateExternalObject.h"

#include <ctime>

CATCreateClass(CatiaPyBridgeRunOnceCommand);

CatiaPyBridgeRunOnceCommand::CatiaPyBridgeRunOnceCommand()
    : CATCommand(NULL, "CatiaPyBridgeRunOnceCommand"),
      _executed(0)
{
    RequestStatusChange(CATCommandMsgRequestSharedMode);
}

CatiaPyBridgeRunOnceCommand::~CatiaPyBridgeRunOnceCommand()
{
}

CATStatusChangeRC CatiaPyBridgeRunOnceCommand::Activate(
    CATCommand*,
    CATNotification*)
{
    if (!_executed)
    {
        _executed = 1;
        ExecuteBridgeJob();
    }

    RequestDelayedDestruction();
    return CATStatusChangeRCCompleted;
}

CATStatusChangeRC CatiaPyBridgeRunOnceCommand::Desactivate(
    CATCommand*,
    CATNotification*)
{
    RequestDelayedDestruction();
    return CATStatusChangeRCCompleted;
}

CATStatusChangeRC CatiaPyBridgeRunOnceCommand::Cancel(
    CATCommand*,
    CATNotification*)
{
    RequestDelayedDestruction();
    return CATStatusChangeRCCompleted;
}

HRESULT CatiaPyBridgeRunOnceCommand::ExecuteBridgeJob(
    const std::string& iJobPath,
    const std::string& iTransport,
    unsigned __int64 iQueueSequence)
{
    CatiaPyBridgeLogger::Info("CatiaPyBridge_RunOnce start");

    const clock_t started = clock();
    CatiaPyBridgeFileBridge fileBridge;
    CatiaPyBridgeRequest request;
    CatiaPyBridgeResponse response;
    response.Transport = iTransport;
    response.QueueSequence = iQueueSequence;

    HRESULT hr = fileBridge.EnsureDirectories();
    if (FAILED(hr))
    {
        CatiaPyBridgeLogger::Error("EnsureDirectories failed");
        return hr;
    }

    try
    {
        hr = iJobPath.empty()
            ? fileBridge.ReadCurrentJob(request)
            : fileBridge.ReadJobFile(iJobPath, request);
        response.JobId = request.JobId.empty() ? "unknown" : request.JobId;
        response.ResponsePath = request.ResponsePath;
        response.Method = "unknown";

        if (FAILED(hr))
        {
            response.SetError(request.ErrorCode, request.ErrorMessage, request.ErrorDetail);
            response.ElapsedMs = static_cast<long>((clock() - started) * 1000 / CLOCKS_PER_SEC);
            if (!response.ResponsePath.empty())
                fileBridge.WriteResponse(response);
            CatiaPyBridgeLogger::Error("ReadCurrentJob failed code=" + request.ErrorCode);
            return hr;
        }

        hr = fileBridge.ReadRequest(request);
        response.JobId = request.JobId;
        response.Method = request.Method.empty() ? "unknown" : request.Method;
        response.ResponsePath = request.ResponsePath;

        if (FAILED(hr))
        {
            response.SetError(request.ErrorCode, request.ErrorMessage, request.ErrorDetail);
            response.ElapsedMs = static_cast<long>((clock() - started) * 1000 / CLOCKS_PER_SEC);
            fileBridge.WriteResponse(response);
            CatiaPyBridgeLogger::Error("ReadRequest failed code=" + request.ErrorCode);
            return hr;
        }

        hr = CatiaPyBridgeCore::Execute(request, response);
        if (FAILED(hr) && response.Ok)
        {
            response.SetError("CAA_EXCEPTION", "CatiaPyBridgeCore returned a failed HRESULT");
        }

        response.ElapsedMs = static_cast<long>((clock() - started) * 1000 / CLOCKS_PER_SEC);

        const HRESULT writeHr = fileBridge.WriteResponse(response);
        if (FAILED(writeHr))
        {
            CatiaPyBridgeLogger::Error("WRITE_RESPONSE_FAILED");
            return writeHr;
        }

        fileBridge.WriteDoneMarker(response);
        CatiaPyBridgeLogger::Info(std::string("CatiaPyBridge_RunOnce end ok=") + (response.Ok ? "true" : "false"));
        return hr;
    }
    catch (...)
    {
        response.JobId = request.JobId.empty() ? "unknown" : request.JobId;
        response.Method = request.Method.empty() ? "unknown" : request.Method;
        response.ResponsePath = request.ResponsePath;
        response.SetError("CAA_EXCEPTION", "Unhandled CAA exception in CatiaPyBridge_RunOnce");
        response.ElapsedMs = static_cast<long>((clock() - started) * 1000 / CLOCKS_PER_SEC);
        if (!response.ResponsePath.empty())
            fileBridge.WriteResponse(response);
        CatiaPyBridgeLogger::Error("CAA_EXCEPTION unhandled");
        return E_FAIL;
    }
}

